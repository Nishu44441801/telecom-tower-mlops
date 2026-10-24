# Feature processing pipeline for tower telemetry
# Authors: Nishant & Bitu (Group 3)
# Shared between training and FastAPI serving

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

# Raw telemetry fields coming from tower sensors
RAW_COLS = [
    "Temperature_C",
    "Battery_Voltage",
    "Power_Consumption_W",
    "Signal_Strength_Percent",
    "Fan_Speed_RPM",
    "Humidity_Percent",
    "Traffic_Load",
    "Tower_Age_Years",
]

# Reasonable operating ranges based on cell tower hardware specs
# Used to filter out obvious sensor glitches (like 250C temp)
SENSOR_LIMITS = {
    "Temperature_C": (-20.0, 85.0),
    "Battery_Voltage": (20.0, 65.0),
    "Power_Consumption_W": (50.0, 3000.0),
    "Signal_Strength_Percent": (0.0, 100.0),
    "Fan_Speed_RPM": (500.0, 6000.0),
    "Humidity_Percent": (0.0, 100.0),
    "Traffic_Load": (0.0, 2000.0),
    "Tower_Age_Years": (0.0, 30.0),
}


class TowerFeatureTransformer(BaseEstimator, TransformerMixin):
    """
    Custom transformer to clean sensor readings and engineer domain ratios.
    Fits medians on train set so serving can fill any missing fields.
    """
    def __init__(self):
        self.medians_ = {}
        self.is_fitted = False

    def fit(self, X, y=None):
        df = X.copy()
        for col in RAW_COLS:
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors="coerce")
                min_v, max_v = SENSOR_LIMITS[col]
                clipped = vals.clip(lower=min_v, upper=max_v)
                self.medians_[col] = float(clipped.median())
            else:
                self.medians_[col] = 0.0

        self.is_fitted = True
        return self

    def transform(self, X):
        if not getattr(self, "fitted_", getattr(self, "is_fitted", False)):
            raise RuntimeError("Transformer needs to be fitted first.")

        if isinstance(X, list):
            df = pd.DataFrame(X)
        else:
            df = X.copy()

        # Fill missing columns if any payload misses a field
        for col in RAW_COLS:
            if col not in df.columns:
                df[col] = np.nan
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Impute missing values with learned training medians and clip to limits
        for col in RAW_COLS:
            low, high = SENSOR_LIMITS[col]
            df[col] = df[col].fillna(self.medians_.get(col, 0.0)).clip(lower=low, upper=high)

        # Domain features:
        # 1. Thermal load relative to fan RPM
        fan_rpm = df["Fan_Speed_RPM"].clip(lower=500.0)
        df["Thermal_Stress_Ratio"] = df["Temperature_C"] / (fan_rpm / 1000.0)

        # 2. Power drawn per active traffic unit (handling idle 0 traffic towers)
        traffic = df["Traffic_Load"].clip(lower=0.0)
        df["Power_Per_Traffic"] = df["Power_Consumption_W"] / (traffic + 1.0)

        # 3. Deviation from nominal 48V DC telecom bus voltage
        df["Battery_Voltage_Dev48"] = (df["Battery_Voltage"] - 48.0).abs()

        # 4. Temperature-humidity interaction
        df["Heat_Humidity_Index"] = df["Temperature_C"] * (df["Humidity_Percent"] / 100.0)

        # 5. Combined aging and power load factor
        df["Aging_Power_Stress"] = (df["Power_Consumption_W"] / 1000.0) * df["Tower_Age_Years"]

        out_cols = RAW_COLS + [
            "Thermal_Stress_Ratio",
            "Power_Per_Traffic",
            "Battery_Voltage_Dev48",
            "Heat_Humidity_Index",
            "Aging_Power_Stress",
        ]
        return df[out_cols]


# Aliases for backward compatibility
TelecomFeatureTransformer = TowerFeatureTransformer
RAW_FEATURE_COLUMNS = RAW_COLS
SENSOR_BOUNDS = SENSOR_LIMITS
