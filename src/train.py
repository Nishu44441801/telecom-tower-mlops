# Model training and artifact generation
# Group 3: Nishant & Bitu

import os
import json
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
)
from src.features import TowerFeatureTransformer, RAW_COLS


def run_training():
    csv_file = "telecom_tower_failure.csv"
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"Missing {csv_file}")

    print(f"Loading raw data: {csv_file}")
    df = pd.read_csv(csv_file)
    X = df[RAW_COLS]
    y = df["Failure_Within_48Hrs"].values

    pct_failures = (np.sum(y) / len(y)) * 100
    print(f"Loaded {len(df)} rows. Failure rate is {pct_failures:.1f}% (~1 in 5).")

    # 80/20 train-test split with stratified labels
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Fit transformer strictly on training split
    pipe = TowerFeatureTransformer()
    pipe.fit(X_train)

    X_tr = pipe.transform(X_train)
    X_te = pipe.transform(X_test)

    # RandomForestClassifier pickles cleanly across different scikit-learn versions
    # and handles tabular class imbalance with class_weight='balanced'
    clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=8,
        min_samples_leaf=4,
        class_weight="balanced",
        random_state=42,
    )

    # 5-fold cross validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    roc_scores = []
    pr_scores = []

    for f_idx, (tr_idx, val_idx) in enumerate(cv.split(X_tr, y_train)):
        clf.fit(X_tr.iloc[tr_idx], y_train[tr_idx])
        probs = clf.predict_proba(X_tr.iloc[val_idx])[:, 1]
        roc_scores.append(roc_auc_score(y_train[val_idx], probs))
        pr_scores.append(average_precision_score(y_train[val_idx], probs))

    print(f"CV ROC-AUC: {np.mean(roc_scores):.4f} (+/- {np.std(roc_scores):.4f})")
    print(f"CV PR-AUC : {np.mean(pr_scores):.4f} (+/- {np.std(pr_scores):.4f})")

    # Fit on all train data
    clf.fit(X_tr, y_train)

    # Test set check
    test_probs = clf.predict_proba(X_te)[:, 1]
    test_roc = float(roc_auc_score(y_test, test_probs))
    test_pr = float(average_precision_score(y_test, test_probs))

    # We use 0.50 as balanced operational threshold
    decision_threshold = 0.50
    preds = (test_probs >= decision_threshold).astype(int)
    cm = confusion_matrix(y_test, preds).tolist()
    rep = classification_report(y_test, preds, output_dict=True)

    print("\n--- Test Set Metrics ---")
    print(f"ROC-AUC: {test_roc:.4f}")
    print(f"PR-AUC : {test_pr:.4f}")
    print(f"Recall (Failures) : {rep['1']['recall']:.4f}")
    print(f"F1 (Failures)     : {rep['1']['f1-score']:.4f}")
    print(f"Confusion Matrix  : TN={cm[0][0]}, FP={cm[0][1]}, FN={cm[1][0]}, TP={cm[1][1]}")

    os.makedirs("artifacts", exist_ok=True)
    version = "v1.0.0"
    out_model = f"artifacts/model_{version}.joblib"
    out_meta = f"artifacts/model_metadata_{version}.json"

    # Save both model and transformer together in joblib bundle
    save_payload = {
        "model": clf,
        "transformer": pipe,
        "feature_names": list(X_tr.columns),
        "threshold": decision_threshold,
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_metrics": {
            "cv_roc_auc_mean": float(np.mean(roc_scores)),
            "cv_pr_auc_mean": float(np.mean(pr_scores)),
            "test_roc_auc": test_roc,
            "test_pr_auc": test_pr,
            "test_f1": float(rep["1"]["f1-score"]),
            "test_recall": float(rep["1"]["recall"]),
            "optimal_threshold": decision_threshold,
            "confusion_matrix": cm,
        },
    }

    joblib.dump(save_payload, out_model)
    with open(out_meta, "w") as f:
        json.dump(
            {
                "model_name": "TowerFailurePredictor",
                "version": version,
                "features": list(X_tr.columns),
                "threshold": decision_threshold,
                "metrics": save_payload["training_metrics"],
                "team": "Group 3 (Nishant & Bitu)",
            },
            f,
            indent=2,
        )

    print(f"Saved model bundle -> {out_model}")


if __name__ == "__main__":
    run_training()
