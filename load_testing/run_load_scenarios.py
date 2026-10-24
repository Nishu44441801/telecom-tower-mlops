"""
Project: Telecom Tower Failure Prediction Service
Group: Group 3 (Nishant & Bitu)
Course: Elective II: Machine Learning Operations (MLOps)
Faculty: Dr. Santosh Kumar

Script: run_load_scenarios.py
Purpose: Executes Task 6 multi-stage load scenarios (Headless Locust):
  Scenario 1: Baseline Load (10 concurrency, 30s)
  Scenario 2: Peak Ramp-Up (100 concurrency, 45s)
  Scenario 3: Stress Spike / Breaking Test (500 concurrency, 45s)

Collects exact measured percentiles (p50, p95, p99), throughput, error rate,
and generates the 'Before & After' evaluation table for Task 6 & Task 8.
"""

import subprocess
import os
import json
import pandas as pd
import time


SCENARIOS = [
    {"name": "Scenario 1: Baseline Load", "users": 10, "spawn_rate": 5, "duration": "25s"},
    {"name": "Scenario 2: Peak Ramp-Up", "users": 100, "spawn_rate": 20, "duration": "35s"},
    {"name": "Scenario 3: Stress Spike", "users": 500, "spawn_rate": 100, "duration": "35s"},
]

RESULTS_DIR = "load_testing/results"


def run_scenario(name, users, spawn_rate, duration, prefix):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    csv_prefix = os.path.join(RESULTS_DIR, f"{prefix}_{users}users")
    cmd = [
        "locust",
        "-f", "load_testing/locustfile.py",
        "--headless",
        "-u", str(users),
        "-r", str(spawn_rate),
        "-t", duration,
        "--host", "http://127.0.0.1:8000",
        "--csv", csv_prefix,
    ]
    print(f"\n[>>>] Running {name} ({users} users, spawn rate {spawn_rate}/s, run time {duration})...")
    start = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - start
    print(f"      Completed in {elapsed:.1f}s.")

    # Parse generated stats CSV
    stats_file = f"{csv_prefix}_stats.csv"
    if os.path.exists(stats_file):
        df_stats = pd.read_csv(stats_file)
        aggregated = df_stats[df_stats["Name"] == "Aggregated"]
        if not aggregated.empty:
            row = aggregated.iloc[0]
            req_count = row["Request Count"]
            fail_count = row["Failure Count"]
            req_per_sec = row["Requests/s"]
            p50 = row["50%"]
            p95 = row["95%"]
            p99 = row["99%"]
            err_rate = (fail_count / req_count * 100) if req_count > 0 else 0.0

            return {
                "Scenario": name,
                "Concurrent Users": users,
                "Requests Sent": int(req_count),
                "Throughput (req/s)": round(float(req_per_sec), 1),
                "p50 Latency (ms)": round(float(p50), 1),
                "p95 Latency (ms)": round(float(p95), 1),
                "p99 Latency (ms)": round(float(p99), 1),
                "Error Rate (%)": round(float(err_rate), 2),
            }
    return None


if __name__ == "__main__":
    print("=" * 65)
    print("STARTING AUTOMATED LOAD TEST EXECUTION (TASK 6)")
    print("=" * 65)
    records = []
    for sc in SCENARIOS:
        rec = run_scenario(sc["name"], sc["users"], sc["spawn_rate"], sc["duration"], "run1")
        if rec:
            records.append(rec)

    if records:
        df_results = pd.DataFrame(records)
        print("\n" + "=" * 65)
        print("MEASURED LOAD TEST BENCHMARK RESULTS:")
        print("=" * 65)
        print(df_results.to_markdown(index=False))
        df_results.to_csv(os.path.join(RESULTS_DIR, "load_test_summary.csv"), index=False)
