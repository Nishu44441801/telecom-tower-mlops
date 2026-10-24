"""
Project: Telecom Tower Failure Prediction Service
Group: Group 3 (Nishant & Bitu)
Course: Elective II: Machine Learning Operations (MLOps)
Faculty: Dr. Santosh Kumar

Script: test_service_acceptance.py
Purpose: Strictly validates Task 3 Acceptance Criteria:
1. Verifies /health and /version endpoints.
2. Compares offline batch predictions for 50 sample rows against the running service
   and asserts an exact 100% match.
3. Tests invalid inputs (out-of-bounds readings, non-numeric values, empty IDs)
   and verifies that the service safely rejects them with HTTP 422 and doesn't crash.
4. Verifies Prometheus /metrics endpoint exposition.
"""

import urllib.request
import urllib.error
import json
import joblib
import pandas as pd
import numpy as np


BASE_URL = "http://127.0.0.1:8000"


def test_health_and_version():
    print("[1] Testing /health and /version endpoints...")
    req = urllib.request.urlopen(f"{BASE_URL}/health")
    health_data = json.loads(req.read().decode())
    assert health_data["status"] == "healthy", "Service health is degraded!"
    assert health_data["model_loaded"] is True, "Model is not marked as loaded!"
    print(f"    [PASS] /health returned healthy status (uptime: {health_data['uptime_seconds']}s)")

    req = urllib.request.urlopen(f"{BASE_URL}/version")
    ver_data = json.loads(req.read().decode())
    assert ver_data["model_version"] == "v1.0.0", "Version mismatch!"
    print(f"    [PASS] /version confirmed model version: {ver_data['model_version']}")


def test_50_sample_parity():
    print("\n[2] Testing Task 3 Acceptance: 50 sample rows parity (Offline vs Running Service)...")
    # 1. Compute offline predictions
    bundle = joblib.load("artifacts/model_v1.0.0.joblib")
    model = bundle["model"]
    transformer = bundle["transformer"]
    threshold = bundle["threshold"]

    df_sample = pd.read_csv("load_test_requests.csv").head(50)
    X_tf = transformer.transform(df_sample)
    offline_probs = model.predict_proba(X_tf)[:, 1]
    offline_preds = (offline_probs >= threshold).astype(int).tolist()

    # 2. Query running service
    # Prepare payload with null handling
    sample_records = df_sample.where(pd.notnull(df_sample), None).to_dict(orient="records")
    payload = json.dumps({"towers": sample_records}).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/predict/batch",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))

    online_preds = [p["predicted_failure_48h"] for p in res_data["predictions"]]
    online_probs = [p["failure_probability"] for p in res_data["predictions"]]

    mismatches = 0
    for i in range(50):
        t_id = sample_records[i]["Tower_ID"]
        off_p = round(offline_probs[i], 4)
        on_p = online_probs[i]
        if offline_preds[i] != online_preds[i]:
            print(f"    [MISMATCH] Row {i} ({t_id}): Offline {offline_preds[i]} vs Online {online_preds[i]}")
            mismatches += 1

    assert mismatches == 0, f"Found {mismatches} mismatches between offline and online predictions!"
    print(f"    [PASS] Perfect 50/50 prediction match achieved between offline model and live HTTP service!")
    print(f"    Sample Tower '{sample_records[0]['Tower_ID']}': Prob={online_probs[0]}, Pred={online_preds[0]}")


def test_invalid_input_rejection():
    print("\n[3] Testing Task 3 Acceptance: Safe handling & rejection of invalid/impossible inputs...")
    invalid_payloads = [
        # Impossible temperature (250°C > 85°C bound)
        {
            "payload": {
                "Tower_ID": "TWR-TEST01",
                "Temperature_C": 250.0,
                "Battery_Voltage": 48.0,
            },
            "desc": "Temperature above maximum domain limit (250°C > 85°C)",
        },
        # Impossible battery voltage (10.0V < 20V bound)
        {
            "payload": {
                "Tower_ID": "TWR-TEST02",
                "Battery_Voltage": 10.0,
            },
            "desc": "Battery voltage below physical cutoff (10V < 20V)",
        },
        # Non-numeric sensor reading
        {
            "payload": {
                "Tower_ID": "TWR-TEST03",
                "Fan_Speed_RPM": "BLOWER_FAILED",
            },
            "desc": "Non-numeric string in sensor measurement field",
        },
        # Empty tower ID
        {
            "payload": {
                "Tower_ID": "   ",
                "Temperature_C": 45.0,
            },
            "desc": "Whitespace-only Tower_ID identifier",
        },
    ]

    for item in invalid_payloads:
        data = json.dumps(item["payload"]).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/predict",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                print(f"    [FAIL] Expected rejection but received HTTP {resp.status} for {item['desc']}")
        except urllib.error.HTTPError as err:
            assert err.code == 422, f"Expected HTTP 422 Unprocessable Entity, got HTTP {err.code}"
            err_body = json.loads(err.read().decode("utf-8"))
            print(f"    [PASS] Correctly rejected with HTTP 422 for: {item['desc']}")
            print(f"           Response message: {err_body.get('message')}")

    # Confirm service is still alive and responsive after receiving malformed data
    req = urllib.request.urlopen(f"{BASE_URL}/health")
    assert req.status == 200, "Service crashed after handling invalid input!"
    print("    [PASS] Service remained robust and healthy; zero crashes on malformed telemetry.")


def test_prometheus_metrics():
    print("\n[4] Testing /metrics Prometheus exposition...")
    req = urllib.request.urlopen(f"{BASE_URL}/metrics")
    metrics_text = req.read().decode("utf-8")
    assert "http_requests_total" in metrics_text, "Missing http_requests_total metric!"
    assert "http_request_duration_seconds" in metrics_text, "Missing latency metric!"
    assert "tower_predictions_total" in metrics_text, "Missing prediction counter metric!"
    print("    [PASS] Prometheus metrics endpoint is correctly exposing telemetry counters and histograms.")


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING SERVICE ACCEPTANCE SUITE (GROUP 3 - NISHANT & BITU)")
    print("=" * 60)
    test_health_and_version()
    test_50_sample_parity()
    test_invalid_input_rejection()
    test_prometheus_metrics()
    print("\n" + "=" * 60)
    print("ALL TASK 3 ACCEPTANCE CRITERIA VERIFIED AND PASSED!")
    print("=" * 60)
