# Telecom Tower Failure Prediction Service
## MLOps Project - Group 3: Nishant & Bitu
Supervisor: Dr. Santosh Kumar

---

### 1. Introduction & Problem Statement
Telecom base stations are remote physical assets where power instability, fan failure, and excessive heat frequently cause unexpected hardware downtime. When a tower goes offline without warning, nearby cells get overloaded, leading to dropped calls and regulatory fines.

In this practical, we took the mobile tower sensor dataset (`telecom_tower_failure.csv`), built a feature engineering and HistGradientBoosting classification pipeline, and packaged it as a monitored Linux microservice. The goal is to provide 48-hour advance warning of failure while surviving peak traffic spikes and self-recovering from process crashes.

---

### 2. Linux Setup & Server Environment (Tasks 1 & 7)
We prepared an Ubuntu 22.04 LTS server layout under `/opt/mlops/tower-prediction` using a non-root system account:
- User: `appuser` (UID: 1001)
- Group: `appgroup` (GID: 1001)

Permissions Demonstration:
We tested file permissions by creating a `model-auditors` group. The trained model artifact (`artifacts/model_v1.0.0.joblib`) was set to permission `640` (`rw-r-----`). Members of `model-auditors` can read the weights for audit purposes, but any write or overwrite attempt throws `bash: Permission denied`.

Our complete 28-command audit log—covering navigation, process inspection (`pidof`, `pgrep`), memory (`free -h`, `vmstat`), and disk monitoring (`df -h`)—is documented in `docs/task1_linux_command_log.md`.

---

### 3. Model Training & Class Imbalance Handling (Task 2)
Inspection of `telecom_tower_failure.csv` showed that ~20.8% of towers fail within 48 hours. 

Why accuracy is misleading:
A trivial model that always predicts "No Failure" would score 79.2% accuracy while failing to detect a single outage. In telecommunications, missing an active failure is much more damaging than dispatching a technician to double-check a false alarm. Therefore, we evaluated our model using:
- ROC-AUC: measures overall discrimination across thresholds.
- PR-AUC (Average Precision): focuses directly on the minority failure class.
- Recall: ensures we catch at least 85% of at-risk towers.

Features engineered in `src/features.py`:
- `Thermal_Stress_Ratio`: Temperature divided by fan RPM (scaled).
- `Power_Per_Traffic`: Power consumption per unit traffic (handles 0-traffic idle towers).
- `Battery_Voltage_Dev48`: Absolute deviation from nominal 48V DC telecom battery voltage.
- `Heat_Humidity_Index`: Interaction between heat and shelter humidity.
- `Aging_Power_Stress`: Total power draw weighted by tower age in years.

Results from 5-fold Stratified CV:
- CV ROC-AUC: 0.8680 (+/- 0.0248)
- CV PR-AUC: 0.6732 (+/- 0.0449)
- Holdout Test ROC-AUC: 0.7798
- Holdout Test PR-AUC: 0.5014

---

### 4. Serving Implementation & Offline Parity (Tasks 3 & 4)
We implemented the API using FastAPI (`src/app.py`):
- `/predict`: Accepts single or batch telemetry payloads.
- `/health`: Reports service status and uptime for synthetic probes.
- `/version`: Displays active model tag (`v1.0.0`) and features.
- `/metrics`: Exports Prometheus format metrics.

Acceptance Verification:
Using `tests/test_service_acceptance.py`:
1. We took 50 rows from `load_test_requests.csv` and scored them offline using joblib, then sent identical rows to the running HTTP endpoint. Predictions matched 50 out of 50 (100% parity).
2. We submitted physically impossible readings (e.g., 250°C temperature, 10V battery). The service safely returned `HTTP 422 Unprocessable Content` with clear error details without crashing.

Deployment:
The service is containerized via Docker and orchestrated with Prometheus and Grafana in `docker-compose.yml` (`restart: unless-stopped`).

---

### 5. Load Testing & Bottleneck Diagnosis (Task 6)
We load-tested the service with `load_test_requests.csv` across three traffic scenarios:
- Baseline (10 concurrent users)
- Peak (100 concurrent users)
- Stress Spike (500 concurrent users)

Diagnosis:
In our initial test with a single worker process, the service broke at ~35 req/s. Under 100 users, CPU feature transformations and GBDT calculations tied up the event loop, causing socket backlogs to overflow and triggering a 21.27% error rate due to client timeouts.

Fix:
We upgraded the deployment to a 4-worker pre-fork architecture with a socket listen backlog of 2048. 

Measured comparison:
- Baseline throughput jumped from 36.8 req/s to 64.2 req/s (+74.5%).
- Baseline p95 latency fell from 296.6ms down to 134.1ms (-54.8%).
- Peak load error rate dropped from 21.27% down to 5.48%.

---

### 6. Automated Recovery & Alert Defense (Tasks 5, 7, 8)
- Watchdog: `scripts/healthcheck_watchdog.sh` runs via cron, probes `/health`, logs with timestamps, and restarts the container if down. It prevents restart loops by stopping after 3 consecutive failures.
- Latency Alert (150ms): Setting 80ms caused false alarms from standard garbage collection pauses (median latency is 82ms). Setting 500ms was too loose, because load tests showed queues collapse quickly once latency exceeds 500ms.
- Error Alert (5%): Setting 1% fired alerts on ordinary bad sensor data (HTTP 422). Setting 20% would let major outages persist unnoticed.

---

### 7. Conclusion
We successfully delivered an end-to-end MLOps pipeline for tower failure prediction. The system combines verified ML feature logic with real-world Linux resilience, verified load capacity, and empirical alert thresholds.
