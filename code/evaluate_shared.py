"""Finalize Task 12's validation threshold and compare on the same sequences.

Usage:
  python evaluate_shared.py --task12 AIHM_Task12-Rawan_R4-R7.zip \
      --task11 AIHM_Task11_IsolationForest_Results.zip --out results

The test split is scored only after thresholds have been fixed from validation.
Labels mean synthetic injection (1) versus no injection (0), not a diagnosis.
"""
import argparse
import io
import json
import zipfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, roc_auc_score


def load_npy(z, name):
    return np.load(io.BytesIO(z.read("AIHM_Task12/data/" + name)))


def metrics(y, pred, score=None):
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    result = dict(n=int(len(y)), injected=int(sum(y)), tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
                  precision=float(p), recall=float(r), f1=float(f),
                  reference_flag_rate=float(fp / (tn + fp)))
    if score is not None and len(set(y)) == 2:
        result["roc_auc"] = float(roc_auc_score(y, score))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task12", required=True, type=Path)
    parser.add_argument("--task11", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.task12) as z:
        X = {s: load_npy(z, f"X_{s}.npy") for s in ("val", "test")}
        y = {s: load_npy(z, f"y_{s}.npy").astype(int) for s in ("val", "test")}
        scaler = json.loads(z.read("AIHM_Task12/data/scaler.json"))
        metadata = pd.read_csv(io.BytesIO(z.read("AIHM_Task12/data/sequence_metadata.csv")))
        raw = pd.read_csv(io.BytesIO(z.read("AIHM_Task12/results_lstm_ae.csv")))
    assert scaler["feature_order"] == ["hr_bpm", "steps_total", "steps_missing"]
    assert scaler["fit_split"] == "train" and scaler["fit_label"] == 0
    assert X["val"].shape[1:] == X["test"].shape[1:] == (12, 3)
    assert np.isfinite(X["val"]).all() and np.isfinite(X["test"]).all()
    assert len(raw) == len(X["val"]) + len(X["test"])
    assert set(raw.split) == {"val", "test"}
    # Never merge on (device,start): an injected copy can share these with its reference.
    aligned = {}
    errors = {}
    for split in ("val", "test"):
        m = metadata[metadata.split == split].sort_values("row_index").reset_index(drop=True)
        r = raw[raw.split == split].reset_index(drop=True)
        assert np.array_equal(m.row_index.to_numpy(), np.arange(len(m)))
        assert len(m) == len(r) == len(y[split])
        assert np.array_equal(m.label.to_numpy(), y[split])
        assert np.array_equal(r.label.to_numpy(), y[split])
        assert np.array_equal(m.device_id.astype(str).to_numpy(), r.device_id.astype(str).to_numpy())
        assert np.array_equal(m.start_utc.astype(str).to_numpy(), r.start_time.astype(str).to_numpy())
        aligned[split] = m
        errors[split] = r.error.to_numpy(dtype=float)
        assert np.isfinite(errors[split]).all()

    # An independent, documented validation-only policy: at most approximately
    # 5% of the reference validation sequences exceed the learned cutoff.
    ae_threshold = float(np.quantile(errors["val"][y["val"] == 0], .95))

    # Task 11's frozen Figshare IF is applied to EXACTLY the Task 12 sequences.
    # A sequence score is the largest 5-minute anomaly score among its 12 windows.
    with zipfile.ZipFile(args.task11) as z:
        frozen = joblib.load(io.BytesIO(z.read("output/models/figshare_global.joblib")))
        assert frozen["columns"] == ["hr_bpm", "steps_total", "steps_missing"]
        model = frozen["pipeline"]
    mean = np.asarray(scaler["mean"])
    scale = np.asarray(scaler["scale"])
    if_score = {}
    fixed_hr = {}
    for split in ("val", "test"):
        original = X[split].astype(float) * scale + mean
        flat = original.reshape(-1, 3)
        steps = flat[:, 1].copy()
        steps[flat[:, 2] > .5] = np.nan
        features = pd.DataFrame({"hr_bpm": flat[:, 0], "steps_total": steps,
                                 "steps_missing": (flat[:, 2] > .5).astype(int)})
        if_score[split] = -model.score_samples(features).reshape(-1, 12).min(axis=1)
        hr = original[:, :, 0]
        high = hr > 100
        low = hr < 50
        fixed_hr[split] = np.any((high[:, 1:] & high[:, :-1]) | (low[:, 1:] & low[:, :-1]), axis=1).astype(int)
    if_threshold = float(np.quantile(if_score["val"][y["val"] == 0], .95))

    summary = {"label_meaning": {"0": "reference without synthetic injection",
                                 "1": "sequence containing synthetic injection"},
               "unit": "one 12 x 5-minute sequence (60 minutes)",
               "selection": "95th percentile of reference validation scores; test unseen during selection",
               "thresholds": {"lstm_ae_sequence_mse": ae_threshold,
                              "isolation_forest_sequence_max_anomaly": if_threshold},
               "methods": {}}
    rows = []
    for split in ("val", "test"):
        ae_pred = (errors[split] > ae_threshold).astype(int)
        if_pred = (if_score[split] > if_threshold).astype(int)
        for method, pred, score in [("LSTM Autoencoder", ae_pred, errors[split]),
                                    ("Isolation Forest adapted to sequence", if_pred, if_score[split]),
                                    ("Two consecutive HR windows rule", fixed_hr[split], None)]:
            summary["methods"][f"{method} | {split}"] = metrics(y[split], pred, score)
        m = aligned[split]
        rows.append(pd.DataFrame({"split": split, "row_index": m.row_index,
                                  "sequence_id": m.sequence_id, "device_id": m.device_id,
                                  "start_utc": m.start_utc, "injected_label": y[split],
                                  "event_id": m.event_id,
                                  "ae_error": errors[split], "ae_flag": ae_pred,
                                  "if_max_anomaly_score": if_score[split], "if_flag": if_pred,
                                  "hr_rule_flag": fixed_hr[split]}))
    pd.concat(rows, ignore_index=True).to_csv(args.out / "matched_sequence_scores.csv", index=False)
    (args.out / "thresholds_and_metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
