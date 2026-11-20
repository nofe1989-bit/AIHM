                      
import argparse
import hashlib
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    confusion_matrix, f1_score, cohen_kappa_score,
)
import xgboost as xgb

warnings.filterwarnings("ignore")
sns.set_theme(style="whitegrid", context="talk")

TASK10_HIGH, TASK10_LOW = 100.0, 60.0
TASK9_HIGH, TASK9_LOW, TASK9_PERSIST = 100.0, 50.0, 2
FEATURE_COLS = ["steps_total", "distance_total", "calories_total",
                "hour_sin", "hour_cos", "personal_baseline", "baseline_available"]
ACT_PREFIX = "act_"


def next_run_dir(output_base):
    output_base = Path(output_base)
    output_base.mkdir(parents=True, exist_ok=True)
    existing = [int(m.group(1)) for p in output_base.iterdir() if p.is_dir()
                for m in [re.match(r"run_(\d+)$", p.name)] if m]
    nxt = max(existing) + 1 if existing else 1
    d = output_base / f"run_{nxt:03d}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def load_and_audit(data_dir, out_dir):
    audit = json.loads((Path(data_dir) / "audit.json").read_text())
    src_dir = Path(data_dir) / "sources"
    dfs = {}
    log = ["AUDIT CHECK (file vs audit.json)", "=" * 60]
    for entry in audit["sources"]:
        f = entry["file"]
        df = pd.read_csv(src_dir / f, parse_dates=["window_start_utc"])
        dfs[f] = df
        ok = (len(df) == entry["windows"]) and (df.shape[1] == entry["columns"])
        log.append(f"  {f:32s} rows={len(df):6d}/{entry['windows']:<6d} "
                   f"cols={df.shape[1]}/{entry['columns']} -> {'OK' if ok else 'MISMATCH'}")
    log.append(f"  definition: {audit['definition']}")
    log.append(f"  lineage   : {audit['lineage']}\n")
    text = "\n".join(log)
    print(text)
    (out_dir / "00_audit_check.txt").write_text(text)
    return audit, dfs


def flag_per_window(hr, high, low):
    return (hr > high) | (hr < low)


def flag_persistence(df, group_col, time_col, hr_col, high, low, persist):
    df = df.sort_values([group_col, time_col]).copy()
    final = pd.Series(False, index=df.index)
    for cond in [df[hr_col] > high, df[hr_col] < low]:
        block = cond.groupby(df[group_col]).cumsum()
        block_id = (~cond).groupby(df[group_col]).cumsum()
        run_len = cond.groupby([df[group_col], block_id]).transform("sum")
        final = final | ((run_len >= persist) & cond)
    return final.reindex(df.index).fillna(False).astype(bool)


def run_baselines(dfs, out_dir):
    hr_col_map = {
        "figshare_features_5min.csv": ("mean_HR", "wearer_group"),
        "galaxyppg_features_5min.csv": ("hr_mean_bpm", "source"),
        "lyan_features_5min.csv": ("hr_mean_bpm", "source"),
        "nofe_features_5min.csv": ("hr_mean_bpm", "source"),
    }
    rows = []
    for f, (hr_col, group_col) in hr_col_map.items():
        df = dfs[f].copy()
        df[hr_col] = pd.to_numeric(df[hr_col], errors="coerce")
        valid = df[hr_col].notna()
        dfv = df.loc[valid].copy()
        s10 = flag_per_window(dfv[hr_col], TASK10_HIGH, TASK10_LOW)
        if group_col not in dfv.columns:
            dfv["source"] = f
            group_col = "source"
        s9 = flag_persistence(dfv, group_col, "window_start_utc", hr_col,
                              TASK9_HIGH, TASK9_LOW, TASK9_PERSIST)
        rows.append({
            "source": f.replace("_features_5min.csv", ""),
            "valid_windows": int(valid.sum()),
            "task10_flagged_gt100_lt60": int(s10.sum()),
            "task10_rate_pct": round(100 * s10.mean(), 3),
            "task9_flagged_gt100_lt50_10min": int(s9.sum()),
            "task9_rate_pct": round(100 * s9.mean(), 3),
        })
    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "baseline_both_standards.csv", index=False)
    print("(1) BASELINE — BOTH STANDARDS (Task10 per-window vs Task9 10-min persistence)")
    print(summary.to_string(index=False), "\n")
    return summary


def build_features(df):
    df = df.copy()
    df["hour"] = pd.to_datetime(df["window_start_utc"], utc=True).dt.hour
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    for c in ["steps_total", "distance_total", "calories_total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                                                                                
                                                                              
                                                                            
    df["personal_baseline_task8"] = pd.to_numeric(df["personal_baseline"], errors="coerce")
    df["personal_baseline"] = np.nan
    df["baseline_available"] = df["baseline_available"].astype(int)
    act = pd.get_dummies(df["activity_context"], prefix="act", dummy_na=False)
    df = pd.concat([df, act], axis=1)
    df["mean_HR"] = pd.to_numeric(df["mean_HR"], errors="coerce")
    return df.dropna(subset=["mean_HR"]).reset_index(drop=True)


def split_for_group(group_name):
    h = hashlib.sha256(f"AIHM-task10-group:{group_name}".encode()).digest()
    x = int.from_bytes(h[:8], "big") / 2**64
    return "train" if x < 0.6 else ("val" if x < 0.8 else "test")


def time_based_split(df, train_frac=0.70, val_frac=0.15):
    df = df.sort_values(["wearer_group", "window_start_utc"]).reset_index(drop=True)
    tr, va, te = [], [], []
    for _, g in df.groupby("wearer_group"):
        i = g.index.values
        n_tr, n_va = int(len(i) * train_frac), int(len(i) * val_frac)
        tr.extend(i[:n_tr]); va.extend(i[n_tr:n_tr + n_va]); te.extend(i[n_tr + n_va:])
    return df.loc[tr].copy(), df.loc[va].copy(), df.loc[te].copy()


def task9_group_split(df, task9_results_dir):
    """Use the persisted Task 9 Figshare device-level split assignments."""
    split_file = Path(task9_results_dir) / "group_split.csv"
    if not split_file.exists():
        raise FileNotFoundError(f"Task 9 split file not found: {split_file}")
    s = pd.read_csv(split_file)
    s = s[(s["source"] == "figshare") & s["group_basis"].eq("deviceId")].copy()
    s["data_split"] = s["data_split"].replace({"validation": "val"})
    if s["group_id"].duplicated().any():
        raise ValueError("Task 9 group_split.csv contains duplicate Figshare group assignments")
    out = df.copy()
    out["_split"] = out["wearer_group"].astype(str).map(s.set_index("group_id")["data_split"])
    if out["_split"].isna().any():
        missing = sorted(out.loc[out["_split"].isna(), "wearer_group"].unique())
        raise ValueError(f"Missing Task 9 split assignments for groups: {missing}")
    tr = out[out._split == "train"].copy(); va = out[out._split == "val"].copy(); te = out[out._split == "test"].copy()
    return tr.drop(columns=["_split"]), va.drop(columns=["_split"]), te.drop(columns=["_split"])


def add_split_safe_baseline(train, val, test):
    """Derive personal baseline only from training observations.

    For unseen validation/test wearers, use the training global mean and mark
    baseline_available=0. This prevents future/test HR values from entering a
    personal baseline feature.
    """
    train = train.copy(); val = val.copy(); test = test.copy()
    group_baseline = train.groupby("wearer_group")["mean_HR"].mean()
    global_baseline = float(train["mean_HR"].mean())
    for d in (train, val, test):
        known = d["wearer_group"].map(group_baseline)
        d["personal_baseline"] = known.fillna(global_baseline)
        d["baseline_available"] = known.notna().astype(int)
    return train, val, test


def add_wearer_target_encode(train, val, test):
    enc = train.groupby("wearer_group")["mean_HR"].mean()
    gmean = train["mean_HR"].mean()
    for d in (train, val, test):
        d["wearer_mean_hr"] = d["wearer_group"].map(enc).fillna(gmean)
    return train, val, test


def feature_matrix(train, val, test):
    act_cols = [c for c in train.columns if c.startswith(ACT_PREFIX)]
    cols = FEATURE_COLS + act_cols + ["wearer_mean_hr"]
    return (train[cols].astype(float).values, val[cols].astype(float).values,
            test[cols].astype(float).values, cols)


def train_models(Xtr, ytr, Xva, yva, Xte, yte, seed):
    rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=5, n_jobs=-1, random_state=seed)
    rf.fit(Xtr, ytr)
    xgr = xgb.XGBRegressor(n_estimators=1000, max_depth=6, learning_rate=0.05,
                           subsample=0.8, colsample_bytree=0.8,
                           early_stopping_rounds=50, random_state=seed, n_jobs=-1)
    xgr.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    models = {"RandomForest": rf, "XGBoost": xgr}
    metrics, preds = {}, {}
    for name, m in models.items():
        p_va, p_te = m.predict(Xva), m.predict(Xte)
        preds[name] = {"val": p_va, "test": p_te}
        metrics[name] = {
            "val_MAE": round(float(mean_absolute_error(yva, p_va)), 3),
            "val_RMSE": round(float(np.sqrt(mean_squared_error(yva, p_va))), 3),
            "val_R2": round(float(r2_score(yva, p_va)), 3),
            "test_MAE": round(float(mean_absolute_error(yte, p_te)), 3),
            "test_RMSE": round(float(np.sqrt(mean_squared_error(yte, p_te))), 3),
            "test_R2": round(float(r2_score(yte, p_te)), 3),
        }
        print(f"  {name:13s} test MAE={metrics[name]['test_MAE']:.2f}  "
              f"RMSE={metrics[name]['test_RMSE']:.2f}  R2={metrics[name]['test_R2']:.3f}")
    return models, preds, metrics


def tune_threshold(resid_val, baseline_flags_val, out_dir, grid=None):
    if grid is None:
        grid = np.arange(1.5, 4.51, 0.25)
    mad = np.median(np.abs(resid_val - np.median(resid_val)))
    records, best = [], {"kappa": -1}
    for k in grid:
        thr = k * mad
        fl = np.abs(resid_val) > thr
        records.append({
            "k": round(float(k), 2), "threshold_bpm": round(float(thr), 3),
            "model_flag_rate_pct": round(100 * fl.mean(), 3),
            "F1_vs_baseline": round(float(f1_score(baseline_flags_val, fl, zero_division=0)), 3),
            "cohen_kappa_vs_baseline": round(float(cohen_kappa_score(baseline_flags_val, fl)), 3),
        })
        kap = records[-1]["cohen_kappa_vs_baseline"]
        if kap > best["kappa"]:
            best = {"k": float(k), "threshold_bpm": float(thr), "kappa": float(kap), "mad": float(mad)}
    pd.DataFrame(records).to_csv(out_dir / "threshold_tuning.csv", index=False)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot([r["k"] for r in records], [r["cohen_kappa_vs_baseline"] for r in records], "o-")
    ax.axvline(best["k"], color="crimson", ls="--",
               label=f"best k={best['k']:.2f} (thr={best['threshold_bpm']:.1f} bpm)")
    ax.set_xlabel("k  (threshold = k x MAD)"); ax.set_ylabel("Cohen kappa vs fixed baseline")
    ax.set_title("(3) Deviation-threshold tuning (validation; agreement objective)"); ax.legend(fontsize=11)
    fig.tight_layout(); fig.savefig(out_dir / "threshold_tuning.png", dpi=130); plt.close(fig)
    return best


def evaluate_anomalies(name, resid_test, baseline_flags_test, threshold, out_dir):
    fl = np.abs(resid_test) > threshold
    cm = confusion_matrix(baseline_flags_test, fl, labels=[False, True])
    tn, fp, fn, tp = cm.ravel()
    res = {
        "model_flag_rate_pct": round(100 * fl.mean(), 3),
        "baseline_flag_rate_pct": round(100 * baseline_flags_test.mean(), 3),
        "precision_vs_baseline": round(tp / max(tp + fp, 1), 3),
        "recall_vs_baseline": round(tp / max(tp + fn, 1), 3),
        "F1_vs_baseline": round(f1_score(baseline_flags_test, fl, zero_division=0), 3),
        "cohen_kappa": round(cohen_kappa_score(baseline_flags_test, fl), 3),
        "n_flagged_by_model": int(fl.sum()), "n_flagged_by_baseline": int(baseline_flags_test.sum()),
        "n_overlap": int((fl & baseline_flags_test).sum()),
        "n_model_only": int((fl & ~baseline_flags_test).sum()),
        "n_baseline_only": int((~fl & baseline_flags_test).sum()),
    }
    fig, ax = plt.subplots(figsize=(5.5, 4.8))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=["normal", "anomaly"], yticklabels=["normal", "anomaly"],
                cbar=False, ax=ax)
    ax.set_xlabel(f"{name} model flag"); ax.set_ylabel("Fixed-threshold baseline flag")
    ax.set_title(f"Anomaly agreement — {name}")
    fig.tight_layout(); fig.savefig(out_dir / f"confusion_{name}.png", dpi=130); plt.close(fig)
    return fl, res


def plot_residuals(resid_test, threshold, name, out_dir):
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.histplot(resid_test, bins=80, kde=True, ax=ax, color="steelblue")
    ax.axvline(threshold, color="crimson", ls="--", label=f"+/-{threshold:.1f} bpm")
    ax.axvline(-threshold, color="crimson", ls="--")
    ax.set_xlabel("residual = actual HR - predicted HR (bpm)")
    ax.set_title(f"Test residual distribution — {name}"); ax.legend()
    fig.tight_layout(); fig.savefig(out_dir / f"residuals_{name}.png", dpi=130); plt.close(fig)


def explain_models(models, Xte, yte, feature_names, best_name, out_dir, do_shap, seed):
    imp_rows = []
    for name, m in models.items():
        for f, imp in zip(feature_names, m.feature_importances_):
            imp_rows.append({"model": name, "feature": f, "importance": float(imp)})
    imp_df = pd.DataFrame(imp_rows)
    imp_df.to_csv(out_dir / "feature_importance.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, (name, _) in zip(axes, models.items()):
        d = imp_df[imp_df.model == name].sort_values("importance", ascending=True)
        ax.barh(d["feature"], d["importance"], color="teal")
        ax.set_title(f"{name} — feature importance"); ax.tick_params(axis="y", labelsize=9)
    fig.tight_layout(); fig.savefig(out_dir / "feature_importance.png", dpi=130); plt.close(fig)
    best_m = models[best_name]
    try:
        perm = permutation_importance(best_m, Xte, yte, n_repeats=5, random_state=seed, n_jobs=-1)
        perm_df = pd.DataFrame({"feature": feature_names,
                                "perm_importance_mean": perm.importances_mean,
                                "perm_importance_std": perm.importances_std}
                               ).sort_values("perm_importance_mean", ascending=True)
        perm_df.to_csv(out_dir / "permutation_importance.csv", index=False)
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.barh(perm_df["feature"], perm_df["perm_importance_mean"],
                xerr=perm_df["perm_importance_std"], color="darkorange")
        ax.set_title(f"Permutation importance (test) — {best_name}")
        fig.tight_layout(); fig.savefig(out_dir / "permutation_importance.png", dpi=130); plt.close(fig)
    except Exception as e:
        print(f"  permutation importance skipped: {e}")
    if do_shap:
        try:
            import shap
            rng = np.random.default_rng(seed)
            idx = rng.choice(Xte.shape[0], size=min(1500, Xte.shape[0]), replace=False)
            X_sample = pd.DataFrame(Xte[idx], columns=feature_names)
            sv = shap.TreeExplainer(best_m).shap_values(X_sample)
            plt.figure(figsize=(9, 6))
            shap.summary_plot(sv, X_sample, plot_type="bar", show=False)
            plt.title(f"SHAP mean |impact| — {best_name}"); plt.tight_layout()
            plt.savefig(out_dir / "shap_bar.png", dpi=130, bbox_inches="tight"); plt.close()
            plt.figure(figsize=(9, 6))
            shap.summary_plot(sv, X_sample, show=False)
            plt.title(f"SHAP beeswarm — {best_name}"); plt.tight_layout()
            plt.savefig(out_dir / "shap_beeswarm.png", dpi=130, bbox_inches="tight"); plt.close()
        except Exception as e:
            print(f"  SHAP skipped: {e}")


def run_split(figshare_df, split_name, split_fn, out_dir, seed, do_shap):
    print(f"\n=== SPLIT: {split_name} ===")
    train, val, test = split_fn(figshare_df)
    print(f"  train={len(train)} val={len(val)} test={len(test)} "
          f"(wearers: train={train.wearer_group.nunique()} val={val.wearer_group.nunique()} test={test.wearer_group.nunique()})")
    train, val, test = add_split_safe_baseline(train, val, test)
    train, val, test = add_wearer_target_encode(train, val, test)
    Xtr, Xva, Xte, cols = feature_matrix(train, val, test)
    ytr, yva, yte = train["mean_HR"].values, val["mean_HR"].values, test["mean_HR"].values
    models, preds, metrics = train_models(Xtr, ytr, Xva, yva, Xte, yte, seed)
    best_name = min(metrics, key=lambda n: metrics[n]["val_MAE"])
    resid_val = yva - preds[best_name]["val"]
    resid_test = yte - preds[best_name]["test"]
    base_val = flag_per_window(pd.Series(yva), TASK10_HIGH, TASK10_LOW).values
    base_test = flag_per_window(pd.Series(yte), TASK10_HIGH, TASK10_LOW).values
    best = tune_threshold(resid_val, base_val, out_dir)
    fl, anom = evaluate_anomalies(best_name, resid_test, base_test, best["threshold_bpm"], out_dir)
    plot_residuals(resid_test, best["threshold_bpm"], best_name, out_dir)
    test_out = test.copy()
    test_out["predicted_hr"] = preds[best_name]["test"]
    test_out["residual"] = resid_test
    test_out["anomaly_flag"] = fl.astype(int)
    test_out["anomaly_dir"] = np.where(resid_test > best["threshold_bpm"], "high",
                                np.where(resid_test < -best["threshold_bpm"], "low", "normal"))
    test_out[["wearer_group", "window_start_utc", "mean_HR", "predicted_hr",
              "residual", "anomaly_flag", "anomaly_dir"]].to_csv(
        out_dir / f"anomaly_flags_{split_name}.csv", index=False)
    top5 = test_out.reindex(np.abs(test_out.residual).sort_values(ascending=False).index).head(5)
    print("  Top-5 anomalous test windows:")
    print(top5[["wearer_group", "window_start_utc", "mean_HR", "predicted_hr", "residual"]].to_string(index=False))
    if split_name == "time_based":
        explain_models(models, Xte, yte, cols, best_name, out_dir, do_shap, seed)
    return {
        "split": split_name, "best_model": best_name,
        "train_n": len(train), "val_n": len(val), "test_n": len(test),
        "train_wearers": int(train.wearer_group.nunique()),
        "val_wearers": int(val.wearer_group.nunique()),
        "test_wearers": int(test.wearer_group.nunique()),
        "metrics": metrics, "tuned_threshold_bpm": round(best["threshold_bpm"], 3),
        "tuned_k": best["k"], "residual_MAD": round(best["mad"], 3),
        "threshold_objective": "agreement_with_task10_fixed_threshold_baseline",
        "anomaly_vs_task10_baseline": anom,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="AIHM_Task8_Corrected_Features")
    p.add_argument("--output-base", default="results")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--no-shap", action="store_true")
    p.add_argument("--task9-results", default="../Task9/results",
                   help="Task 9 results directory containing group_split.csv")
    a = p.parse_args()
    cross = []
    for run_i in range(a.runs):
        seed = 42 + run_i
        out_dir = next_run_dir(a.output_base)
        print(f"\n{'#'*72}\n# RUN -> {out_dir}   (seed={seed})\n{'#'*72}\n")
        audit, dfs = load_and_audit(a.input, out_dir)
        run_baselines(dfs, out_dir)
        figshare = build_features(dfs["figshare_features_5min.csv"])
        splits = {
            "time_based": time_based_split,
            "task9_group_based": lambda d: task9_group_split(d, a.task9_results),
        }
        split_results = {}
        for sname, sfn in splits.items():
            split_results[sname] = run_split(figshare, sname, sfn, out_dir, seed, not a.no_shap)
        (out_dir / "metrics.json").write_text(json.dumps({
            "run_folder": out_dir.name, "seed": seed,
            "task10_standard": {"high_bpm": TASK10_HIGH, "low_bpm": TASK10_LOW, "persistence": "per_window"},
            "task9_standard": {"high_bpm": TASK9_HIGH, "low_bpm": TASK9_LOW,
                               "persistence_windows": TASK9_PERSIST, "persistence_minutes": 10,
                               "note": "rest/coverage >=80% filter omitted — not available in Task8 feature files"},
            "split_provenance": {
                "task9_group_based": str(Path(a.task9_results) / "group_split.csv"),
                "task9_group_policy": "figshare deviceId proxy groups from Task 9",
                "personal_baseline_policy": "recomputed from training rows only; unseen groups use training global mean",
                "threshold_policy": "tuned on validation by agreement with fixed Task 10 baseline; not independent clinical ground truth"
            },
            "splits": split_results,
        }, indent=2))
        comp = pd.DataFrame([
            {"split": s, "best_model": r["best_model"],
             "train_n": r["train_n"], "val_n": r["val_n"], "test_n": r["test_n"],
             "train_wearers": r["train_wearers"], "val_wearers": r["val_wearers"], "test_wearers": r["test_wearers"],
             "XGB_test_MAE": r["metrics"]["XGBoost"]["test_MAE"],
             "XGB_test_R2": r["metrics"]["XGBoost"]["test_R2"],
             "RF_test_MAE": r["metrics"]["RandomForest"]["test_MAE"],
             "tuned_threshold_bpm": r["tuned_threshold_bpm"],
             "model_F1_vs_task10_baseline": r["anomaly_vs_task10_baseline"]["F1_vs_baseline"],
             "model_flag_rate_pct": r["anomaly_vs_task10_baseline"]["model_flag_rate_pct"],
             "n_model_only_anomalies": r["anomaly_vs_task10_baseline"]["n_model_only"]}
            for s, r in split_results.items()])
        comp.to_csv(out_dir / "comparison_summary.csv", index=False)
        print("\n(4) COMPARISON SUMMARY — dual splits (Task10 time-based vs Task9 group-based)")
        print(comp.to_string(index=False))
        cross.append({"run": out_dir.name, "seed": seed, **{f"{s}_{k}": v for s, r in split_results.items()
                                                           for k, v in [("best", r["best_model"]),
                                                                        ("XGB_MAE", r["metrics"]["XGBoost"]["test_MAE"])]}})
        print(f"\nDONE -> outputs in: {out_dir}")
    pd.DataFrame(cross).to_csv(Path(a.output_base) / "cross_run_summary.csv", index=False)
    print("\nALL RUNS COMPLETE.")


if __name__ == "__main__":
    main()
