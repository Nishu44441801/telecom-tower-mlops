# Capacity and Alerting Memo
# Prepared by: Nishant & Bitu (Group 3)
# Date: October 2026

Target: NOC On-Call & Systems Team
Context: Capacity planning and alert thresholds for the Tower Failure Prediction endpoint

---

1. Expected Peak Traffic
We sized this service for a normal peak of 60 requests per second. In a live telecom setup, this corresponds to roughly 120 field sensors and SCADA loops polling the service at 2-second heartbeat intervals, plus periodic batch queries from regional dispatchers.

Our target latency is to keep 95% of prediction requests (p95) under 150ms, with error rates below 1%.

---

2. Recommended Server & Container Configuration
During our load tests, the default single-worker process broke under 100 concurrent users (throughput peaked at ~35 req/s before dropping requests, with p95 latency spiking past 4 seconds). 

To support our 60 req/s target with headroom, we recommend:
- Workers: 4 Uvicorn workers behind a process manager (e.g., Gunicorn or Uvicorn workers).
- Concurrency: Set socket listen backlog to 2048 to absorb brief traffic spikes without dropping connections.
- Resources: 2.0 vCPU and 1 GB RAM. Under sustained testing, our container used around 145 MB of RAM, so 1 GB provides safe buffer for temporary NumPy batch matrix allocations.
- Restart Policy: 'restart: unless-stopped' with automated healthchecks every 15 seconds.

Measured evidence:
Under 4-worker serving, at 64.2 req/s, our measured p50 latency was 82.4ms, p95 was 134.1ms, and error rate remained at 0.00%.

---

3. Alert Threshold Defense

Alert 1: High Latency (p95 > 150ms over 15 seconds)
- Chosen: 150ms.
- Why not tighter (e.g., 80ms)? At 10 concurrent users, our median response time is ~82ms. Minor garbage collection pauses or batch requests push latency into the 90-110ms range naturally. Setting 80ms triggers constant false alarms.
- Why not looser (e.g., 500ms)? During our stress tests, once p95 crossed 500ms, the request queue backed up rapidly, causing client timeouts within 20-30 seconds. 150ms gives the team enough lead time to scale or reroute before users see dropped requests.

Alert 2: High Error Rate (> 5% failed requests over 1 minute)
- Chosen: 5%.
- Why not tighter (e.g., 1%)? Remote IoT sensors occasionally transmit noisy readings or extreme voltage spikes that get rejected with HTTP 422 by our validation logic. A 1% threshold treats normal sensor bad data as a server outage.
- Why not looser (e.g., 20%)? In our load test, a 20% error rate meant the service had essentially stalled and was dropping 1 in 5 queries. An alert must fire long before error rates reach 20%. 5% cleanly separates ordinary sensor noise from backend degradation.

---

4. Quick Reference Runbook
- Target Peak: 60 req/s
- Worker Count: 4
- Memory Limit: 1024 MB
- Alert: p95 latency > 150ms (Warning)
- Alert: HTTP error rate > 5% (Critical)
