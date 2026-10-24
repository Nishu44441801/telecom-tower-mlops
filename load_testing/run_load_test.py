"""
Project: Telecom Tower Failure Prediction Service
Group: Group 3 (Nishant & Bitu)
Course: Elective II: Machine Learning Operations (MLOps)
Faculty: Dr. Santosh Kumar

Script: run_load_test.py
Purpose: Pure Python multi-threaded load test suite for Task 6 & 8.
Uses HTTP keep-alive connection pooling via requests.Session to simulate
persistent SCADA and NOC client connections accurately.
"""

import time
import random
import json
import threading
import requests
from requests.adapters import HTTPAdapter
import numpy as np
import pandas as pd
from typing import List, Dict, Any

BASE_URL = "http://127.0.0.1:8000"
PAYLOADS_DF = pd.read_csv("load_test_requests.csv")
SAMPLE_RECORDS = PAYLOADS_DF.where(pd.notnull(PAYLOADS_DF), None).to_dict(orient="records")


def create_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=1)
    session.mount("http://", adapter)
    return session


def send_request(session: requests.Session) -> Dict[str, Any]:
    roll = random.random()
    t_start = time.perf_counter()
    status = 0
    is_err = False

    try:
        if roll < 0.85:
            # Single prediction
            record = random.choice(SAMPLE_RECORDS)
            resp = session.post(f"{BASE_URL}/predict", json=record, timeout=4.0)
            status = resp.status_code
            is_err = (status >= 400)
        elif roll < 0.95:
            # Batch cluster prediction (5-10 towers)
            batch = random.sample(SAMPLE_RECORDS, random.randint(5, 10))
            resp = session.post(f"{BASE_URL}/predict/batch", json={"towers": batch}, timeout=6.0)
            status = resp.status_code
            is_err = (status >= 400)
        else:
            # Health check ping
            resp = session.get(f"{BASE_URL}/health", timeout=3.0)
            status = resp.status_code
            is_err = (status >= 400)
    except Exception:
        status = 0
        is_err = True

    duration_ms = (time.perf_counter() - t_start) * 1000.0
    return {"status": status, "is_error": is_err, "latency_ms": duration_ms}


def worker_thread(stop_event: threading.Event, results_list: List[Dict[str, Any]], think_time: float):
    session = create_session()
    while not stop_event.is_set():
        res = send_request(session)
        results_list.append(res)
        if think_time > 0:
            time.sleep(think_time)
    session.close()


def execute_scenario(name: str, concurrency: int, duration_secs: int, think_time: float = 0.05) -> Dict[str, Any]:
    print(f"\n[>>>] Launching {name} | Concurrency: {concurrency} workers | Duration: {duration_secs}s...")
    stop_event = threading.Event()
    results = []
    threads = []

    t_run_start = time.perf_counter()
    for _ in range(concurrency):
        t = threading.Thread(target=worker_thread, args=(stop_event, results, think_time))
        t.daemon = True
        t.start()
        threads.append(t)
        if concurrency > 50:
            time.sleep(duration_secs * 0.1 / concurrency)

    time.sleep(duration_secs)
    stop_event.set()

    for t in threads:
        t.join(timeout=1.5)

    total_time = time.perf_counter() - t_run_start
    total_reqs = len(results)
    if total_reqs == 0:
        return {"Scenario": name, "Status": "No requests executed"}

    latencies = [r["latency_ms"] for r in results]
    errors = sum(1 for r in results if r["is_error"] or r["status"] != 200)

    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    p99 = float(np.percentile(latencies, 99))
    throughput = round(total_reqs / total_time, 1)
    err_rate = round((errors / total_reqs) * 100, 2)

    return {
        "Scenario": name,
        "Concurrent Users": concurrency,
        "Total Requests": total_reqs,
        "Throughput (req/s)": throughput,
        "p50 Latency (ms)": round(p50, 2),
        "p95 Latency (ms)": round(p95, 2),
        "p99 Latency (ms)": round(p99, 2),
        "Error Rate (%)": err_rate,
    }


if __name__ == "__main__":
    print("=" * 70)
    print("TELECOM SERVICE LOAD TEST & BENCHMARK SUITE (GROUP 3)")
    print("=" * 70)

    scenarios = [
        {"name": "Scenario 1: Baseline Load", "concurrency": 10, "duration": 12, "think_time": 0.05},
        {"name": "Scenario 2: Peak Operating Load", "concurrency": 100, "duration": 15, "think_time": 0.05},
        {"name": "Scenario 3: Stress Spike (Breaking Test)", "concurrency": 500, "duration": 15, "think_time": 0.01},
    ]

    summary = []
    for sc in scenarios:
        res = execute_scenario(sc["name"], sc["concurrency"], sc["duration"], sc["think_time"])
        summary.append(res)
        print(f"      Throughput: {res['Throughput (req/s)']} req/s | p50: {res['p50 Latency (ms)']}ms | p95: {res['p95 Latency (ms)']}ms | Error: {res['Error Rate (%)']}%")
        time.sleep(2)

    df = pd.DataFrame(summary)
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY RESULTS TABLE:")
    print("=" * 70)
    print(df.to_string(index=False))
    df.to_csv("load_testing/load_test_summary.csv", index=False)
    print("\n[+] Results exported to load_testing/load_test_summary.csv")
