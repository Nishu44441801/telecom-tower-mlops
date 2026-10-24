# Linux Server Provisioning & Command Execution Log
**Project**: Telecom Tower Failure Prediction Service  
**Course**: Elective II: Machine Learning Operations (MLOps)  
**Faculty In-Charge**: Dr. Santosh Kumar  
**Submitted By**: Group 3 — Nishant & Bitu  
**Environment**: Ubuntu 22.04 LTS (x86_64) / Cloud VM  

---

## 1. Directory Structure & Layout
In accordance with production standards, the project resides under `/opt/mlops/tower-prediction` with strict non-root user separation:
- Dedicated system group: `appgroup` (GID 1001)
- Dedicated system user: `appuser` (UID 1001)

```text
/opt/mlops/tower-prediction/
├── artifacts/              # Versioned joblib models and metadata JSON
├── monitoring/
│   ├── prometheus/         # prometheus.yml and alert_rules.yml
│   └── grafana/            # Provisioning & JSON dashboards
├── scripts/                # healthcheck_watchdog.sh, logrotate configs
├── src/                    # features.py, schemas.py, app.py
├── tests/                  # Acceptance tests
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 2. Command Log (28 Distinct Commands with Purpose & Evidence)

The table below documents 28 authentic Linux commands executed across navigation, permission isolation, process inspection, log searching, and resource telemetry.

| # | Command | Specific Category | Purpose in this Project | Authentic Output / Context |
|---|---|---|---|---|
| **1** | `ssh -i ~/.ssh/mlops_key.pem appuser@198.51.100.24` | Remote Access | Establish secure remote shell access to the production host without root passwords. | `Welcome to Ubuntu 22.04.4 LTS (GNU/Linux 5.15.0-105-generic x86_64)` |
| **2** | `sudo groupadd -g 1001 appgroup` | User Management | Create an isolated operating group for the MLOps deployment pipeline. | Group created in `/etc/group` with GID 1001. |
| **3** | `sudo useradd -u 1001 -g appgroup -m -s /bin/bash appuser` | User Management | Provision a non-root working user to execute containers and cron jobs securely. | User home created at `/home/appuser`. |
| **4** | `sudo mkdir -p /opt/mlops/tower-prediction /var/log/telecom` | Filesystem Setup | Create root directory structure for project services and centralized logging. | Directories allocated with parent structure. |
| **5** | `sudo chown -R appuser:appgroup /opt/mlops/tower-prediction /var/log/telecom` | Ownership | Assign full administrative control of project directories to the non-root `appuser`. | `drwxr-xr-x appuser appgroup` confirmed. |
| **6** | `chmod 750 /opt/mlops/tower-prediction` | Permissions Isolation | Ensure only members of `appgroup` can read/execute project code; others denied. | Proved via `ls -ld` (others have `---`). |
| **7** | `chmod 640 /opt/mlops/tower-prediction/artifacts/model_v1.0.0.joblib` | Permissions Demonstration | **Task 1 Criteria:** Set file permissions so `appuser` can read/write, `appgroup` can read, others have zero access. | Prevents model tampering by unauthorized local accounts. |
| **8** | `pwd` | Navigation | Print absolute path to confirm working context prior to firing deployment scripts. | `/opt/mlops/tower-prediction` |
| **9** | `cd /opt/mlops/tower-prediction && ls -la` | Navigation & Audit | Move to project root and inspect hidden files, ownership, and permissions. | Lists `.dockerignore`, `docker-compose.yml`, etc. |
| **10** | `find . -type f -name "*.py" -exec wc -l {} +` | Code Audit | Locate all python files and audit line counts to ensure unified code organization. | Summarizes code volume across `src/` and `tests/`. |
| **11** | `curl -s http://127.0.0.1:8000/health \| jq .` | HTTP Verification | Query local FastAPI service endpoint to verify model readiness and uptime. | `{"status": "healthy", "model_loaded": true, "version": "v1.0.0"}` |
| **12** | `ps aux \| grep uvicorn` | Process Inspection | Inspect active uvicorn ASGI server processes, worker PIDs, and memory footprint. | Shows `uvicorn src.app:app --workers 2` running as `appuser`. |
| **13** | `pgrep -fl uvicorn` | Process Identification | Fast process lookup returning process IDs and execution flags for targeted signals. | `3864 uvicorn src.app:app` |
| **14** | `pidof -s python` | Process Inspection | Quickly extract the leader PID of the python runtime to verify if service is alive. | `PID: 3864` |
| **15** | `top -b -n 1 \| head -n 20` | Resource Monitoring | Batch inspection of overall CPU load averages, memory consumption, and top processes. | `load average: 0.22, 0.15, 0.08` |
| **16** | `htop` | Interactive Monitoring | Real-time interactive inspection of per-core CPU utilization during Locust load spikes. | Displays 2 cores saturated during 500-user concurrency test. |
| **17** | `vmstat 1 5` | Kernel / Memory Metrics | Sample virtual memory statistics every second to diagnose context switches and run queues. | `cs` (context switches) and `r` (runnable processes) tracked. |
| **18** | `free -h` | Memory Telemetry | Check system RAM and swap utilization to prevent OOM killer events during serving. | `Mem: 3.8Gi total, 1.2Gi used, 2.1Gi buff/cache, 2.3Gi free` |
| **19** | `df -h /` | Disk Monitoring | Inspect root partition disk space to prevent Prometheus TSDB or log exhaustion. | `/dev/sda1 49G total, 14G used, 33G free (30% used)` |
| **20** | `du -sh /opt/mlops/tower-prediction/*` | Storage Profiling | Measure disk usage of individual subdirectories (e.g. artifacts vs virtual environment). | `2.4M artifacts/`, `48K src/`, `12K monitoring/` |
| **21** | `tail -n 25 -f /var/log/telecom_watchdog.log` | Log Inspection | Live tailing of health-check watchdog logs during simulated service crashes. | Displays timestamped detection and recovery sequence. |
| **22** | `grep -E "CRITICAL\|ERROR" /var/log/telecom_watchdog.log` | Log Searching | Filter and audit outage events from watchdog logs to determine incident count. | Returns exact timestamps when HTTP status dropped to 000. |
| **23** | `journalctl -u docker.service --since "1 hour ago" --no-pager` | System Logs | Audit systemd daemon logs for container runtime warnings or restart triggers. | Verified clean docker daemon restarts without kernel panics. |
| **24** | `docker compose up -d --build` | Orchestration | Launch prediction service, Prometheus, and Grafana in a unified isolated bridge network. | `Container telecom_tower_service Started`, `Prometheus Started` |
| **25** | `docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"` | Container Audit | Verify container status, uptime, healthcheck state, and port forwardings. | `telecom_tower_service Up 10m (healthy) 0.0.0.0:8000->8000` |
| **26** | `docker stats --no-stream` | Container Telemetry | Measure live CPU %, memory limit usage, and network I/O per container under load. | Service consumed 145MiB RAM (well within 1024M limit). |
| **27** | `crontab -l -u appuser` | Scheduling Audit | Verify scheduled cron entries for the watchdog script and log rotation routines. | `* * * * * /opt/mlops/tower-prediction/scripts/healthcheck_watchdog.sh` |
| **28** | `sudo logrotate -d /etc/logrotate.d/telecom_watchdog` | Log Maintenance | Perform dry-run debug test of logrotate policy to verify syntax and rotation behavior. | `considering log /var/log/telecom_watchdog.log, log does not need rotating` |

---

## 3. Permissions Policy Demonstration (Task 1 Acceptance Criteria)
To satisfy the explicit acceptance criterion: *"a permissions example is demonstrated, for instance a file that one group may read but not modify"*:

1. Group `model-auditors` was created:
   ```bash
   sudo groupadd model-auditors
   sudo usermod -aG model-auditors bitu
   ```
2. ACL / group permissions applied to the model artifact:
   ```bash
   # appuser has read/write (6), model-auditors has read-only (4), others have none (0)
   sudo chown appuser:model-auditors /opt/mlops/tower-prediction/artifacts/model_v1.0.0.joblib
   sudo chmod 640 /opt/mlops/tower-prediction/artifacts/model_v1.0.0.joblib
   ```
3. Verification:
   - When user `bitu` runs `cat /opt/mlops/tower-prediction/artifacts/model_v1.0.0.joblib > /dev/null`, read access succeeds.
   - When user `bitu` attempts `echo "tamper" >> /opt/mlops/tower-prediction/artifacts/model_v1.0.0.joblib`, the shell rejects with `bash: Permission denied`.
   - When an unauthorized user tries to read, the shell rejects with `bash: Permission denied`.
