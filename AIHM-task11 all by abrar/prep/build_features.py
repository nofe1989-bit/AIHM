"""Build checked five-minute HR features from the supplied Project.zip.

Run: python build_features.py --project-zip Project.zip --out output
Only two nonduplicated HR sources in this archive are used. This script does
not train a model, invent activity labels, or infer a participant from a device.
"""

import argparse
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd


FIGSHARE = "Project/data/group_abrar/sensor_hrv_filtered.csv"
SAMSUNG = (
    "Project/data/group_lian_nofe/"
    "com.samsung.shealth.tracker.heart_rate.20261007080980.csv"
)
HR_FIELD = "com.samsung.health.heart_rate.heart_rate"
TIME_FIELD = "com.samsung.health.heart_rate.start_time"
OFFSET_FIELD = "com.samsung.health.heart_rate.time_offset"
MIN_BASELINE_WINDOWS = 30
MIN_BASELINE_DAYS = 2
FEATURE_COLUMNS = [
    "source", "wearer_group", "window_start_utc", "window_minutes",
    "mean_HR", "std_HR", "steps_total", "distance_total", "calories_total",
    "activity_context", "hour_of_day_utc", "window_count",
    "personal_baseline", "deviation_from_baseline", "baseline_window_count",
    "baseline_days", "baseline_available",
]


def read_source(archive, name, **kwargs):
    return pd.read_csv(io.BytesIO(archive.read(name)), low_memory=False, **kwargs)


def checked_rows(df, source, offset=None):
    df = df.copy()
    before = len(df)
    valid_hr = pd.to_numeric(df["hr"], errors="coerce").between(30, 220)
    valid_time = df["timestamp"].notna()
    df = df.loc[valid_hr & valid_time].copy()
    df["hr"] = pd.to_numeric(df["hr"])
    df = df.sort_values(["wearer_group", "timestamp"])
    duplicate = df.duplicated(["wearer_group", "timestamp", "hr"])
    duplicates = int(duplicate.sum())
    df = df.loc[~duplicate]
    return df, {
        "source": source,
        "input_records": int(before),
        "invalid_or_missing_hr": int((~valid_hr).sum()),
        "invalid_or_missing_time": int((~valid_time).sum()),
        "duplicate_measurements_removed": duplicates,
        "retained_measurements": int(len(df)),
        "time_interpretation": offset,
    }


def load_figshare(archive):
    raw = read_source(
        archive, FIGSHARE,
        usecols=["deviceId", "ts_start", "HR", "steps", "distance", "calories"],
    )
    times = pd.to_datetime(pd.to_numeric(raw.ts_start, errors="coerce"),
                           unit="ms", utc=True, errors="coerce")
    # This publisher's 4-week collection is in 2021. The supplied quality
    # table contains one out-of-period 2018 timestamp; report its exclusion.
    out_of_period = times.notna() & (times.dt.year != 2021)
    df = pd.DataFrame({
        "source": "figshare_quality",
        "wearer_group": raw.deviceId.astype(str),
        "timestamp": times.mask(out_of_period),
        "hr": raw.HR,
        "steps": pd.to_numeric(raw.steps, errors="coerce"),
        "distance": pd.to_numeric(raw.distance, errors="coerce"),
        "calories": pd.to_numeric(raw.calories, errors="coerce"),
    })
    df, audit = checked_rows(df, "figshare_quality", "ts_start: Unix milliseconds UTC")
    audit["out_of_period_2018_records"] = int(out_of_period.sum())
    return df, audit


def load_samsung(archive):
    # Samsung has a metadata line and a trailing comma in every data row.
    # index_col=False prevents pandas from shifting the columns by one.
    raw = read_source(archive, SAMSUNG, skiprows=1, index_col=False)
    expected = {HR_FIELD, TIME_FIELD, OFFSET_FIELD}
    if not expected.issubset(raw.columns):
        raise ValueError(f"Samsung fields missing: {expected - set(raw.columns)}")
    offsets = set(raw[OFFSET_FIELD].dropna().unique())
    if offsets != {"UTC+0300"}:
        raise ValueError(f"Unexpected Samsung time offsets: {offsets}")
    naive_time = pd.to_datetime(raw[TIME_FIELD], errors="coerce")
    times = naive_time.dt.tz_localize("Etc/GMT-3").dt.tz_convert("UTC")
    df = pd.DataFrame({
        "source": "samsung_export",
        # One archive is not proof of how many people wore its watches.
        "wearer_group": "samsung_export_01_unverified",
        "timestamp": times,
        "hr": raw[HR_FIELD],
        "steps": np.nan,
        "distance": np.nan,
        "calories": np.nan,
    })
    df, audit = checked_rows(df, "samsung_export", "local UTC+03:00 -> UTC")
    audit["interval_summary_records_not_expanded"] = int(
        raw["com.samsung.health.heart_rate.binning_data"].notna().sum()
    )
    audit["steps_and_activity"] = "not available in these HR records"
    return df, audit


def make_windows(measurements):
    measurements = measurements.copy()
    measurements["window_start_utc"] = measurements.timestamp.dt.floor("5min")
    feat = measurements.groupby(
        ["source", "wearer_group", "window_start_utc"], as_index=False
    ).agg(
        mean_HR=("hr", "mean"), std_HR=("hr", "std"),
        steps_total=("steps", lambda v: v.sum(min_count=1)),
        distance_total=("distance", lambda v: v.sum(min_count=1)),
        calories_total=("calories", lambda v: v.sum(min_count=1)),
        window_count=("hr", "count"),
    )
    feat["window_minutes"] = 5
    feat["hour_of_day_utc"] = feat.window_start_utc.dt.hour
    # A zero means observed zero steps; missing steps remain unknown.
    feat["activity_context"] = "unknown"
    observed = feat.steps_total.notna()
    feat.loc[observed & (feat.steps_total <= 10), "activity_context"] = "low_steps_observed"
    feat.loc[observed & (feat.steps_total > 10), "activity_context"] = "steps_observed"

    feat["personal_baseline"] = np.nan
    feat["baseline_window_count"] = 0
    feat["baseline_days"] = 0
    feat["baseline_available"] = False
    for _, part in feat.groupby(["source", "wearer_group"]):
        first = part.window_start_utc.min()
        week = part[part.window_start_utc < first + pd.Timedelta(days=7)]
        n = len(week)
        days = week.window_start_utc.dt.date.nunique()
        feat.loc[part.index, "baseline_window_count"] = n
        feat.loc[part.index, "baseline_days"] = days
        if n >= MIN_BASELINE_WINDOWS and days >= MIN_BASELINE_DAYS:
            feat.loc[part.index, "personal_baseline"] = week.mean_HR.median()
            feat.loc[part.index, "baseline_available"] = True
    feat["deviation_from_baseline"] = feat.mean_HR - feat.personal_baseline
    feat = feat[FEATURE_COLUMNS].sort_values(
        ["source", "wearer_group", "window_start_utc"]
    ).reset_index(drop=True)
    # A model should never receive a phantom 1970 time or a fabricated HR.
    assert feat.mean_HR.between(30, 220).all()
    assert feat.window_start_utc.dt.year.min() > 2000
    assert not feat.duplicated(["source", "wearer_group", "window_start_utc"]).any()
    assert (feat.loc[~feat.baseline_available, "personal_baseline"].isna()).all()
    return feat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-zip", required=True, type=Path)
    ap.add_argument("--out", default=Path("output"), type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.project_zip) as archive:
        if not {FIGSHARE, SAMSUNG}.issubset(archive.namelist()):
            raise ValueError("Required input files are absent from the archive")
        fig, fig_audit = load_figshare(archive)
        samsung, sam_audit = load_samsung(archive)
        duplicate_copy = archive.read(FIGSHARE) == archive.read(
            "Project/data/group_rehab/sensor_hrv_filtered.csv"
        )
    features = make_windows(pd.concat([fig, samsung], ignore_index=True))
    for source, name in [("figshare_quality", "figshare_features_5min.csv"),
                         ("samsung_export", "samsung_features_5min.csv")]:
        features[features.source == source].to_csv(args.out / name, index=False)
    features.to_csv(args.out / "ALL_checked_features_5min.csv", index=False)
    audit = {
        "input_archive": args.project_zip.name,
        "sources": [fig_audit, sam_audit],
        "figshare_quality_duplicate_copy_in_group_rehab": duplicate_copy,
        "duplicate_copy_counted_twice": False,
        "windows_by_source": features.groupby("source").size().to_dict(),
        "eligible_figshare_groups_for_baseline": int(features[
            (features.source == "figshare_quality") & features.baseline_available
        ].wearer_group.nunique()),
        "samsung_baseline_available": bool(features[
            features.source == "samsung_export"
        ].baseline_available.any()),
        "unavailable_inputs": [
            "No separate Lyan export is present in this Project.zip",
            "No GalaxyPPG source is present in this Project.zip",
            "No verified wearer identity or exercise tags in the Samsung HR CSV",
        ],
        "note": "Task 11 model training, tuning and evaluation were not performed.",
    }
    (args.out / "qa_report.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
