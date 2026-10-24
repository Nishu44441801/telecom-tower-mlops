"""
Project: Telecom Tower Failure Prediction Service
Group: Group 3 (Nishant & Bitu)
Course: Elective II: Machine Learning Operations (MLOps)
Faculty: Dr. Santosh Kumar

Module: schemas.py
Purpose: Pydantic v2 schemas defining the Raw-Input Contract (Task 2 & 3).
Provides runtime type enforcement, domain boundaries, clear error messaging,
and support for both single-tower and batch-telemetry ingestion.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class TowerTelemetryInput(BaseModel):
    """
    Raw sensor readings contract for an individual telecom tower.
    Notice: Tower_ID is an identifier, not a feature.
    Sensor bounds adhere to realistic operating limits.
    """
    Tower_ID: str = Field(..., description="Unique alphanumeric tower identifier, e.g. TWR-09001")
    Temperature_C: Optional[float] = Field(
        None, ge=-20.0, le=85.0, description="Ambient tower temperature in Celsius"
    )
    Battery_Voltage: Optional[float] = Field(
        None, ge=20.0, le=65.0, description="Battery bank voltage in Volts (nominal ~48V)"
    )
    Power_Consumption_W: Optional[float] = Field(
        None, ge=50.0, le=3000.0, description="Total active power drawn by site equipment in Watts"
    )
    Signal_Strength_Percent: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Transceiver signal strength percentage"
    )
    Fan_Speed_RPM: Optional[float] = Field(
        None, ge=500.0, le=6000.0, description="Cooling unit blower speed in RPM"
    )
    Humidity_Percent: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Relative humidity percentage inside shelter"
    )
    Traffic_Load: Optional[float] = Field(
        None, ge=0.0, le=2000.0, description="Active user traffic served (0 = idle tower)"
    )
    Tower_Age_Years: Optional[int] = Field(
        None, ge=0, le=30, description="Tower physical installation age in years"
    )

    @field_validator("Tower_ID")
    @classmethod
    def validate_tower_id(cls, v: str) -> str:
        v_clean = v.strip()
        if not v_clean:
            raise ValueError("Tower_ID must not be empty or whitespace.")
        return v_clean


class BatchTelemetryInput(BaseModel):
    """
    Payload for batch prediction endpoint accepting a list of tower telemetry records.
    """
    towers: List[TowerTelemetryInput] = Field(
        ..., min_length=1, description="List of raw tower telemetry records"
    )


class TowerPredictionOutput(BaseModel):
    Tower_ID: str
    failure_probability: float
    predicted_failure_48h: int
    risk_level: str
    model_version: str


class BatchPredictionOutput(BaseModel):
    count: int
    failures_predicted: int
    predictions: List[TowerPredictionOutput]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    version: str
    uptime_seconds: float


class VersionResponse(BaseModel):
    service_name: str
    model_version: str
    algorithm: str
    features: List[str]
    threshold: float
