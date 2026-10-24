# Project Demonstration Guide & Live Veda Walkthrough
**Project**: Telecom Tower Failure Prediction Service  
**Team**: Group 3 — Nishant & Bitu  
**Course**: Elective II: Machine Learning Operations (MLOps)  
**Faculty In-Charge**: Dr. Santosh Kumar  
**Target Duration**: 5 Minutes  

---

## 1. Division of Responsibilities (Who Explains What)

| Time Window | Presenter | Topic & Demonstrated Actions |
|---|---|---|
| **0:00 – 1:30** | **Nishant** | **Architecture, Linux Setup & Service Correctness (Tasks 1, 2, 3)**<br>- Show directory layout (`/opt/mlops/tower-prediction`) and non-root user `appuser`.<br>- Explain the permissions isolation example (`chmod 640` on model artifact).<br>- Explain the unified `features.py` module and ROC-AUC / Recall justification for the 20.8% failure imbalance.<br>- Run the automated acceptance test script (`python -m tests.test_service_acceptance`) showing 50/50 prediction parity and HTTP 422 input rejection without crash. |
| **1:30 – 3:30** | **Bitu** | **Deployment, Live Dashboards & Load Testing (Tasks 4, 5, 6)**<br>- Demonstrate single-command deployment with Docker Compose (`docker compose up -d`).<br>- Open Grafana dashboard showing live Request Rate, Latency percentiles (p50, p95, p99), Error Rate, and Tower Failure Prediction share.<br>- Trigger load benchmark and explain the before-and-after results table (single worker vs 4 workers). |
| **3:30 – 5:00** | **Joint (Nishant & Bitu)** | **Automated Recovery, Killing the Service & Capacity Defense (Tasks 7 & 8)**<br>- **Live Kill Demo**: Deliberately stop the container (`docker stop telecom_tower_service`).<br>- Show `healthcheck_watchdog.sh` detecting the failure in `/var/log/telecom_watchdog.log`, restarting the service, and restoring health within seconds.<br>- Explain restart loop prevention.<br>- Conclude with the 1-page Capacity Memo defending the 4-worker setup, 150ms latency alert, and 5% error alert. |

---

## 2. Step-by-Step Live Demonstration Commands

### Step 1: Verify Code & Model Acceptance (Nishant)
```bash
# 1. Run the acceptance test suite
python -m tests.test_service_acceptance
```
*Expected output*: 
- `/health` and `/version` verified.
- 50/50 exact parity between offline joblib model and live HTTP API verified.
- Out-of-bounds temperature (250°C), voltage (<20V), and invalid characters rejected with HTTP 422 without server crash.

---

### Step 2: Start the Full Monitoring Stack (Bitu)
```bash
# 1. Start the container stack with single command (Task 4)
docker compose up -d --build

# 2. Verify running containers and health status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
- Open browser to Grafana: `http://<SERVER_IP>:3000` (User: `admin`, Pass: `admin`).
- Navigate to **MLOps Operations -> Telecom Tower Failure Prediction Operations Dashboard**.
- Point out the 6 instrumented panels:
  1. Prediction Throughput (req/s)
  2. Latency Percentiles (p50, p95, p99)
  3. Share of Failure Predictions over time
  4. Error Rate (%)
  5. Cumulative Predictions by Class
  6. Service Uptime

---

### Step 3: Run the Load Test & Observe Dashboard Live (Bitu)
```bash
# Execute multi-stage benchmark using load_test_requests.csv
python load_testing/run_load_test.py
```
- Show the live request throughput surge on Grafana.
- Point out p95 latency holding steady under 150ms with 4 workers.

---

### Step 4: Live Kill & Self-Healing Demonstration (Nishant & Bitu)
```bash
# 1. In Terminal 1: Watch the watchdog log live
tail -f /var/log/telecom_watchdog.log

# 2. In Terminal 2: Deliberately kill the service container
docker stop telecom_tower_service

# 3. In Terminal 1: Run or wait for the watchdog routine
/opt/mlops/tower-prediction/scripts/healthcheck_watchdog.sh
```
*What the evaluator will see in the log*:
```text
[2026-10-24T15:10:00Z] [CRITICAL] Health probe failed! HTTP status: 000 (Consecutive failures: 1)
[2026-10-24T15:10:00Z] [WARN] Initiating automated container recovery for service 'telecom_tower_service'...
[2026-10-24T15:10:04Z] [RECOVERED] Service successfully recovered and healthy in 4s. Auto-healing complete.
```
- Query health endpoint to confirm recovery:
```bash
curl -s http://127.0.0.1:8000/health | jq .
```

---

## 3. Anticipated Questions from Dr. Santosh Kumar & Confident Answers

**Q1: Why did you evaluate your model using PR-AUC and Recall rather than standard Accuracy?**  
> **Nishant**: "In our dataset, the failure rate is 20.8% (about 1 in 5 towers). A naive model that predicts 0 for every tower achieves 79.2% accuracy while missing 100% of outages. In telecom, an unpredicted tower failure causes a massive cellular black spot and SLA penalty. Therefore, we optimized for high Recall and PR-AUC, tuning our decision threshold to catch at least 85% of at-risk towers while keeping false dispatches manageable."

**Q2: How did you ensure serving-time feature engineering exactly matches training?**  
> **Nishant**: "Per Rule 7, we engineered a single module, `src/features.py`, containing `TelecomFeatureTransformer`. During training, it learns median values and clips sensor extremes. That exact transformer object is serialized inside `artifacts/model_v1.0.0.joblib`. When FastAPI loads the model at startup, it executes the identical transformer. We verified this with `tests/test_service_acceptance.py`, achieving an exact 50-out-of-50 match between offline and online inference."

**Q3: What was the bottleneck in your single-worker server during load testing?**  
> **Bitu**: "The single Uvicorn worker bound Python's GIL and event loop during GBDT tree traversal and NumPy calculations. When concurrent users scaled past 50, incoming TCP connections sat in the socket backlog until client timeouts triggered at 4.0s. This caused a 21.27% error rate at 100 users and 80.7% at 500 users. We eliminated this by deploying 4 pre-forked workers with an expanded socket listen backlog of 2048, which reduced p95 latency from 4,013ms down to 134ms at baseline and kept errors at 0%."

**Q4: How do your alerts prevent false alarms and missed outages?**  
> **Bitu**: "We set our p95 latency alert to 150ms and error rate to 5%. If we had set latency tighter, say 80ms, harmless GC pauses would trigger false alarms since our median p50 is 82ms. Conversely, if we had set it looser to 500ms, our load test proved that by 500ms the request queue was already collapsing toward total timeout. The 150ms mark gives the on-call engineer early warning before real connection drops occur."
