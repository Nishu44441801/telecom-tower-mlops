"""
Project: Telecom Tower Failure Prediction Service
Group: Group 3 (Nishant & Bitu)
Course: Elective II: Machine Learning Operations (MLOps)
Faculty: Dr. Santosh Kumar

Script: locustfile.py
Purpose: Realistic load testing engine (Task 6 & 8)
- Ingests 'load_test_requests.csv' as realistic payloads (explicitly forbidden from training).
- Generates realistic traffic distributions:
  * 85% single prediction traffic (/predict)
  * 10% multi-tower batch prediction (/predict/batch)
  * 5% health check ping (/health)
"""

import random
import pandas as pd
from locust import HttpUser, task, between, events

# Load realistic test requests once per worker process
PAYLOADS_DF = pd.read_csv("load_test_requests.csv")
# Clean NaNs to None for valid JSON serialization
CLEAN_RECORDS = PAYLOADS_DF.where(pd.notnull(PAYLOADS_DF), None).to_dict(orient="records")


class TelecomTowerOperatorUser(HttpUser):
    # Think time between telemetry batches: 50ms to 200ms
    wait_time = between(0.05, 0.2)

    @task(85)
    def predict_single_tower(self):
        """Simulates field SCADA polling single tower status."""
        record = random.choice(CLEAN_RECORDS)
        with self.client.post(
            "/predict",
            json=record,
            name="/predict (Single)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(10)
    def predict_batch_towers(self):
        """Simulates regional NOC dispatcher checking a cluster of 5-15 towers."""
        batch_size = random.randint(5, 15)
        batch_records = random.sample(CLEAN_RECORDS, batch_size)
        with self.client.post(
            "/predict/batch",
            json={"towers": batch_records},
            name="/predict/batch (Cluster)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(5)
    def check_health(self):
        """Simulates load balancer synthetic health probe."""
        self.client.get("/health", name="/health")
