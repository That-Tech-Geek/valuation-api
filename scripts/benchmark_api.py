#!/usr/bin/env python3
"""Measure real HTTP latency and server RSS for a 1,000-company snapshot."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


def request(url: str) -> tuple[float, bytes]:
    start = time.perf_counter()
    with urlopen(url, timeout=10) as response:
        payload = response.read()
    return (time.perf_counter() - start) * 1000.0, payload


def rss_mib(pid: int) -> float | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--single-iterations", type=int, default=100)
    parser.add_argument("--batch-iterations", type=int, default=30)
    parser.add_argument("--max-single-p95-ms", type=float, default=5.0)
    parser.add_argument("--max-batch-p95-ms", type=float, default=200.0)
    parser.add_argument("--max-rss-mib", type=float, default=250.0)
    parser.add_argument("--max-startup-ms", type=float, default=2000.0)
    args = parser.parse_args()

    binary = args.binary.resolve()
    data = args.data.resolve()
    proc = subprocess.Popen([str(binary), "--data", str(data)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    samples: list[float] = []
    stop = threading.Event()

    def sample_memory() -> None:
        while not stop.is_set():
            current = rss_mib(proc.pid)
            if current is not None:
                samples.append(current)
            stop.wait(0.003)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    base = "http://127.0.0.1:8080"
    started = time.perf_counter()
    try:
        deadline = started + 15.0
        while True:
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
                raise RuntimeError(f"API exited before health check: {stderr}")
            try:
                _, health = request(base + "/health")
                break
            except (URLError, TimeoutError, OSError):
                if time.perf_counter() >= deadline:
                    raise RuntimeError("API health check timed out")
                time.sleep(0.025)
        startup_ms = (time.perf_counter() - started) * 1000.0
        health_doc = json.loads(health)
        if health_doc.get("rows") != args.rows:
            raise RuntimeError(f"expected {args.rows} loaded rows, got {health_doc.get('rows')}")

        single_url = base + "/value/FIX00000.X"
        batch_url = base + "/value/batch?fmt=json"
        for _ in range(10):
            request(single_url)
        for _ in range(3):
            _, body = request(batch_url)
            if len(json.loads(body).get("results", [])) != args.rows:
                raise RuntimeError("batch endpoint did not return the complete company universe")

        single_times = [request(single_url)[0] for _ in range(args.single_iterations)]
        batch_times = []
        for _ in range(args.batch_iterations):
            elapsed, body = request(batch_url)
            if len(json.loads(body).get("results", [])) != args.rows:
                raise RuntimeError("batch response row count changed during benchmark")
            batch_times.append(elapsed)

        stop.set()
        sampler.join(timeout=1)
        peak_rss = max(samples, default=math.inf)
        result = {
            "rows": args.rows,
            "startup_ms": round(startup_ms, 3),
            "single_p50_ms": round(statistics.median(single_times), 3),
            "single_p95_ms": round(percentile(single_times, 0.95), 3),
            "batch_p50_ms": round(statistics.median(batch_times), 3),
            "batch_p95_ms": round(percentile(batch_times, 0.95), 3),
            "peak_rss_mib": round(peak_rss, 3),
            "limits": {
                "startup_ms": args.max_startup_ms,
                "single_p95_ms": args.max_single_p95_ms,
                "batch_p95_ms": args.max_batch_p95_ms,
                "peak_rss_mib": args.max_rss_mib,
            },
        }
        print(json.dumps(result, indent=2))
        failures = []
        if startup_ms > args.max_startup_ms:
            failures.append(f"startup {startup_ms:.2f}ms > {args.max_startup_ms:.2f}ms")
        if result["single_p95_ms"] > args.max_single_p95_ms:
            failures.append(f"single p95 {result['single_p95_ms']:.2f}ms > {args.max_single_p95_ms:.2f}ms")
        if result["batch_p95_ms"] > args.max_batch_p95_ms:
            failures.append(f"batch p95 {result['batch_p95_ms']:.2f}ms > {args.max_batch_p95_ms:.2f}ms")
        if peak_rss > args.max_rss_mib:
            failures.append(f"peak RSS {peak_rss:.2f}MiB > {args.max_rss_mib:.2f}MiB")
        if failures:
            raise SystemExit("BENCHMARK GATE FAILED: " + "; ".join(failures))
    finally:
        stop.set()
        sampler.join(timeout=1)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    main()
