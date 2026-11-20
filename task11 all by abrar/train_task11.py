"""Reproducible research prototype for AIHM Task 11.

Run from this directory: python train_task11.py
Original public train/validation/test groups come from Task 9. Private exports
are never inferred to be verified participant identities.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parent
IN = ROOT / "input"
OUT = ROOT / "output"
MODELS = OUT / "models"
CANDIDATES = [0.005, 0.01, 0.02, 0.05]


def read(name):
    return pd.read_csv(IN / name)


def fit_model(frame, cols, seed=42):
    model = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=False),
        IsolationForest(n_estimators=100, max_samples=min(256, len(frame)),
                        contamination="auto", random_state=seed, n_jobs=1),
    )
    model.fit(frame[cols])
    return model


def add_time_features(df, time_col):
    df = df.copy()
    df["time"] = pd.to_datetime(df[time_col], utc=True)
    hour = df.time.dt.hour + df.time.dt.minute / 60
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    return df


def public_data():
    fig = add_time_features(read("figshare_checked_5min.csv"), "window_start_utc")
    fig = fig.rename(columns={"wearer_group": "group_id", "mean_HR": "hr_bpm"})
    split = read("group_split.csv")
    split = split[split.source == "figshare"][["group_id", "data_split"]]
    fig = fig.merge(split, on="group_id", validate="many_to_one")
    assert fig.data_split.notna().all()
    # Steps can be missing in the Figshare table; missing does not mean zero.
    fig["steps_missing"] = fig.steps_total.isna().astype(int)
    galaxy = add_time_features(read("galaxy_task9_5min.csv"), "window_start_utc")
    galaxy = galaxy.rename(columns={"hr_mean_bpm": "hr_bpm"})
    return fig, galaxy


def tune_public(name, data, columns, synthetic=None):
    train = data[data.data_split == "train"]
    val = data[data.data_split == "validation"]
    test = data[data.data_split == "test"]
    model = fit_model(train, columns)
    train_score = model.score_samples(train[columns])
    val_score = model.score_samples(val[columns])
    syn_score = model.score_samples(synthetic[columns]) if synthetic is not None else None
    options = []
    for c in CANDIDATES:
        threshold = float(np.quantile(train_score, c))
        fpr_proxy = float((val_score <= threshold).mean())
        recall = float((syn_score <= threshold).mean()) if syn_score is not None else None
        options.append({"contamination_candidate": c, "threshold": threshold,
                        "validation_flag_rate": fpr_proxy,
                        "validation_synthetic_recall": recall})
    if syn_score is not None:
        viable = [x for x in options if x["validation_flag_rate"] <= 0.05]
        chosen = max(viable, key=lambda x: (x["validation_synthetic_recall"],
                                           -x["validation_flag_rate"])) if viable else min(
            options, key=lambda x: x["validation_flag_rate"])
    else:
        chosen = min(options, key=lambda x: (abs(x["validation_flag_rate"] - 0.01),
                                            x["contamination_candidate"]))
    threshold = chosen["threshold"]
    for phase, frame in [("validation", val), ("test", test)]:
        scored = frame[["group_id", "time", "hr_bpm", "data_split"]].copy()
        scored["score"] = model.score_samples(frame[columns])
        scored["flagged"] = scored.score <= threshold
        scored.to_csv(OUT / f"{name}_{phase}_scores.csv", index=False)
    joblib.dump({"pipeline": model, "columns": columns, "threshold": threshold,
                 "selected_contamination": chosen["contamination_candidate"]},
                MODELS / f"{name}_global.joblib")
    return model, threshold, {
        "source": name, "train_windows": len(train), "validation_windows": len(val),
        "test_windows": len(test), "train_groups": train.group_id.nunique(),
        "validation_groups": val.group_id.nunique(), "test_groups": test.group_id.nunique(),
        "selection": chosen, "candidate_results": options,
        "test_flag_rate_unlabelled": float((model.score_samples(test[columns]) <= threshold).mean()),
    }


def evaluate_synthetic(fig, model, threshold):
    syn = add_time_features(read("synthetic_injection_5min.csv"), "window_start_utc")
    syn["bin"] = syn.time.dt.floor("5min")
    context = fig[["group_id", "time", "steps_total", "steps_missing"]].copy()
    context["bin"] = context.time.dt.floor("5min")
    syn = syn.merge(context.drop(columns="time"), on=["group_id", "bin"],
                    how="left", validate="many_to_one")
    assert syn.steps_missing.notna().all(), "Synthetic windows must match original windows"
    syn["hr_bpm"] = syn.injected_hr_bpm
    cols = ["hr_bpm", "steps_total", "steps_missing"]
    syn["score"] = model.score_samples(syn[cols])
    syn["flagged"] = syn.score <= threshold
    syn.to_csv(OUT / "figshare_synthetic_scores.csv", index=False)
    return syn.groupby(["data_split", "injected_label"]).flagged.agg(
        ["sum", "count", "mean"]
    ).reset_index().to_dict(orient="records")


def evaluate_exercise(galaxy, model, threshold):
    c = read("exercise_controls_seconds.csv")
    c["time"] = pd.to_datetime(c.time_utc, utc=True).dt.floor("5min")
    c = c[["group_id", "time", "data_split", "activity_label"]].drop_duplicates()
    c = c.groupby(["group_id", "time", "data_split"], as_index=False).agg(
        activity_label=("activity_label", lambda x: ",".join(sorted(set(x))))
    )
    base = galaxy[["group_id", "time", "hr_bpm", "coverage", "hour_sin", "hour_cos"]]
    c = c.merge(base, on=["group_id", "time"], validate="many_to_one")
    assert len(c) == 30, "Expected 30 distinct exercise control windows"
    c["score"] = model.score_samples(c[["hr_bpm", "coverage", "hour_sin", "hour_cos"]])
    c["flagged"] = c.score <= threshold
    c.to_csv(OUT / "galaxy_exercise_control_scores.csv", index=False)
    return c.groupby("data_split").flagged.agg(["sum", "count", "mean"]).reset_index().to_dict(orient="records")


def personal_models(fig):
    # Calibrate on the first calendar week of each device group. These groups
    # are dataset device IDs, not verified people. Later windows only are scored.
    out = []
    for uid, part in fig.groupby("group_id"):
        part = part.sort_values("time")
        week_end = part.time.min() + pd.Timedelta(days=7)
        week = part[part.time < week_end]
        later = part[part.time >= week_end]
        dates = week.time.dt.date.nunique()
        row = {"source": "figshare", "group_id": uid, "first_week_windows": len(week),
               "first_week_dates": dates, "later_windows": len(later)}
        if len(week) < 30 or dates < 2 or len(later) < 20:
            row["status"] = "insufficient_calibration_or_followup"
            out.append(row)
            continue
        cols = ["hr_bpm", "steps_total", "steps_missing", "hour_sin", "hour_cos"]
        model = fit_model(week, cols)
        mid = len(later) // 2
        val, test = later.iloc[:mid], later.iloc[mid:]
        train_scores = model.score_samples(week[cols])
        val_scores = model.score_samples(val[cols])
        choices = [(c, float(np.quantile(train_scores, c))) for c in CANDIDATES]
        c, threshold = min(choices, key=lambda item: (
            abs(float((val_scores <= item[1]).mean()) - 0.01), item[0]
        ))
        test_scores = model.score_samples(test[cols])
        row.update(status="trained", validation_windows=len(val), test_windows=len(test),
                   selected_contamination=c, threshold=threshold,
                   validation_flag_rate_unlabelled=float((val_scores <= threshold).mean()),
                   test_flag_rate_unlabelled=float((test_scores <= threshold).mean()))
        out.append(row)
        joblib.dump({"pipeline": model, "columns": cols, "threshold": threshold},
                    MODELS / f"figshare_personal_{uid}.joblib")
    return out


def private_personal():
    rows = []
    bounds = read("private_temporal_split.csv")
    for name in ("lyan", "nofe"):
        d = add_time_features(read(f"{name}_task9_5min.csv"), "window_start_utc")
        d = d.rename(columns={"hr_mean_bpm": "hr_bpm"}).sort_values("time")
        first = d.time.min()
        week = d[d.time < first + pd.Timedelta(days=7)]
        days = week.time.dt.date.nunique()
        row = {"source": name, "group_id": f"{name}_export_unverified",
               "first_week_windows": len(week), "first_week_dates": days,
               "total_windows": len(d)}
        if len(week) < 30 or days < 2:
            row["status"] = "insufficient_first_week"
            rows.append(row)
            continue
        # Validation/test use the chronological holdouts defined in Task 9.
        def slice_phase(phase):
            b = bounds[(bounds.source == name) & (bounds.data_split == phase)].iloc[0]
            return d[(d.time >= pd.to_datetime(b.first_window_utc, utc=True)) &
                     (d.time <= pd.to_datetime(b.last_window_utc, utc=True))]
        val, test = slice_phase("validation"), slice_phase("test")
        assert len(val) > 20 and len(test) > 20
        cols = ["hr_bpm", "hour_sin", "hour_cos"]
        model = fit_model(week, cols)
        train_scores = model.score_samples(week[cols])
        val_scores = model.score_samples(val[cols])
        choices = [(c, float(np.quantile(train_scores, c))) for c in CANDIDATES]
        c, threshold = min(choices, key=lambda item: (
            abs(float((val_scores <= item[1]).mean()) - 0.01), item[0]
        ))
        test_scores = model.score_samples(test[cols])
        row.update(status="trained", validation_windows=len(val), test_windows=len(test),
                   selected_contamination=c, threshold=threshold,
                   validation_flag_rate_unlabelled=float((val_scores <= threshold).mean()),
                   test_flag_rate_unlabelled=float((test_scores <= threshold).mean()))
        rows.append(row)
        joblib.dump({"pipeline": model, "columns": cols, "threshold": threshold},
                    MODELS / f"{name}_personal.joblib")
    return rows


def main():
    MODELS.mkdir(parents=True, exist_ok=True)
    fig, galaxy = public_data()
    syn = read("synthetic_injection_5min.csv")
    syn_val = syn[syn.data_split == "validation"].copy()
    syn_val = add_time_features(syn_val, "window_start_utc")
    syn_val["bin"] = syn_val.time.dt.floor("5min")
    context = fig[["group_id", "time", "steps_total", "steps_missing"]].copy()
    context["bin"] = context.time.dt.floor("5min")
    syn_val = syn_val.merge(context.drop(columns="time"), on=["group_id", "bin"],
                            validate="many_to_one")
    syn_val["hr_bpm"] = syn_val.injected_hr_bpm
    assert syn_val.steps_missing.notna().all()
    # Avoid UTC hour in the public Figshare model: participants were recorded
    # at uneven hours, and the validation set favored HR plus observed steps.
    fcols = ["hr_bpm", "steps_total", "steps_missing"]
    gcols = ["hr_bpm", "coverage", "hour_sin", "hour_cos"]
    fmodel, fthreshold, fmetrics = tune_public("figshare", fig, fcols, syn_val)
    gmodel, gthreshold, gmetrics = tune_public("galaxy", galaxy, gcols)
    synthetic = evaluate_synthetic(fig, fmodel, fthreshold)
    exercise = evaluate_exercise(galaxy, gmodel, gthreshold)
    personal = personal_models(fig) + private_personal()
    pd.DataFrame(personal).to_csv(OUT / "personalization_results.csv", index=False)
    report = {"global_models": [fmetrics, gmetrics], "synthetic_recall": synthetic,
              "exercise_control_false_alarm_windows": exercise,
              "personal_models_trained": sum(x["status"] == "trained" for x in personal),
              "personal_models_skipped": [x for x in personal if x["status"] != "trained"],
              "interpretation": "Unlabelled originals are presumed-normal candidates, not verified normal readings. Synthetic recall and exercise control flags are research metrics, not clinical performance."}
    (OUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"trained": report["personal_models_trained"],
                      "skipped": len(report["personal_models_skipped"]),
                      "models": [x["source"] for x in report["global_models"]]}, indent=2))


if __name__ == "__main__":
    main()
