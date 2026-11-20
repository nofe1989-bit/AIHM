"""Rebuild the supplied Task 10 group-split XGBoost for a paired Task 13 audit.

Original Task 10 archive has predictions but no saved fitted estimator. This
script rebuilds its stated features, split and hyperparameters from raw inputs.
"""
import io
import json
import zipfile
from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error


BASE="AIHM_Task10_Corrected/"
FEATURES=["steps_total","distance_total","calories_total","hour_sin","hour_cos",
          "personal_baseline","baseline_available"]


def feature_frame(d):
    d=d.copy()
    hour=pd.to_datetime(d.window_start_utc,utc=True).dt.hour
    d["hour_sin"]=np.sin(2*np.pi*hour/24)
    d["hour_cos"]=np.cos(2*np.pi*hour/24)
    for c in ["steps_total","distance_total","calories_total"]:
        d[c]=pd.to_numeric(d[c],errors="coerce").fillna(0)
    d["personal_baseline"]=np.nan
    d["baseline_available"]=d["baseline_available"].astype(int)
    d=pd.concat([d,pd.get_dummies(d.activity_context,prefix="act",dummy_na=False)],axis=1)
    d["mean_HR"]=pd.to_numeric(d.mean_HR,errors="coerce")
    return d.dropna(subset=["mean_HR"]).reset_index(drop=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--task10",required=True,type=Path)
    ap.add_argument("--task11",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.task10) as z:
        d=pd.read_csv(z.open(BASE+"Task8/sources/figshare_features_5min.csv"))
        groups=pd.read_csv(z.open(BASE+"Task9/results/group_split.csv"))
        published=json.loads(z.read(BASE+"Task10/results_corrected/run_001/metrics.json"))
    with zipfile.ZipFile(a.task11) as z:
        syn=pd.read_csv(z.open("input/synthetic_injection_5min.csv"))
        exercise=pd.read_csv(z.open("output/galaxy_exercise_control_scores.csv"))
    d=feature_frame(d)
    group_map=groups.loc[groups.source.eq("figshare"),["group_id","data_split"]].set_index("group_id").data_split
    d["split"]=d.wearer_group.map(group_map)
    assert d.split.notna().all()
    tr=d[d.split.eq("train")].copy();va=d[d.split.eq("validation")].copy();te=d[d.split.eq("test")].copy()
    assert [len(tr),len(va),len(te)]==[22983,8006,7922]
    per_group=tr.groupby("wearer_group").mean_HR.mean()
    global_mean=float(tr.mean_HR.mean())
    for frame in [tr,va,te]:
        known=frame.wearer_group.map(per_group)
        frame["personal_baseline"]=known.fillna(global_mean)
        frame["baseline_available"]=known.notna().astype(int)
        frame["wearer_mean_hr"]=known.fillna(global_mean)
    cols=FEATURES+[c for c in tr if c.startswith("act_")]+["wearer_mean_hr"]
    x=lambda frame:frame[cols].astype(float).to_numpy()
    model=xgb.XGBRegressor(n_estimators=1000,max_depth=6,learning_rate=.05,
                           subsample=.8,colsample_bytree=.8,early_stopping_rounds=50,
                           random_state=42,n_jobs=-1)
    model.fit(x(tr),tr.mean_HR.to_numpy(),eval_set=[(x(va),va.mean_HR.to_numpy())],verbose=False)
    va_mae=mean_absolute_error(va.mean_HR,model.predict(x(va)))
    te_mae=mean_absolute_error(te.mean_HR,model.predict(x(te)))
    assert abs(te_mae-published["splits"]["task9_group_based"]["metrics"]["XGBoost"]["test_MAE"])<.15,(te_mae,published)
    # Baseline and target-encoding values always come from train, including
    # when test group is unseen. Align injected rows to source by group+5min bin.
    full=pd.concat([va,te],ignore_index=True)
    full["slot"]=pd.to_datetime(full.window_start_utc,utc=True).dt.floor("5min")
    syn["slot"]=pd.to_datetime(syn.window_start_utc,utc=True,format="mixed").dt.floor("5min")
    paired=syn.loc[syn.data_split.isin(["validation","test"])].merge(full,
            left_on=["group_id","data_split","slot"],right_on=["wearer_group","split","slot"],
            validate="many_to_one",suffixes=("_synthetic",""))
    assert len(paired)==len(syn.loc[syn.data_split.isin(["validation","test"])])
    assert np.allclose(paired.normal_observed_hr_bpm,paired.mean_HR,atol=.0001)
    pred=model.predict(x(paired)); threshold=float(published["splits"]["task9_group_based"]["tuned_threshold_bpm"])
    rows=[]
    for label in (0,1):
        part=paired[["data_split","event_id","group_id","slot","mean_HR"]].copy()
        part["label"]=label
        part["observed_hr_bpm"]=paired.injected_hr_bpm if label else paired.mean_HR
        part["predicted_hr_bpm"]=pred
        part["absolute_residual_bpm"]=np.abs(part.observed_hr_bpm-pred)
        part["xgb_flag"]=(part.absolute_residual_bpm>threshold).astype(int)
        rows.append(part)
    out=pd.concat(rows,ignore_index=True)
    out.to_csv(a.out/"task10_replay_paired_scores.csv",index=False)
    exercise=exercise[exercise.data_split.isin(["validation","test"])].copy()
    transfer=pd.DataFrame(0.0,index=exercise.index,columns=cols)
    transfer["hour_sin"]=pd.to_datetime(exercise.time,utc=True).dt.hour.map(lambda h:np.sin(2*np.pi*h/24))
    transfer["hour_cos"]=pd.to_datetime(exercise.time,utc=True).dt.hour.map(lambda h:np.cos(2*np.pi*h/24))
    transfer["personal_baseline"]=global_mean
    transfer["wearer_mean_hr"]=global_mean
    transfer["act_unknown"]=1.
    exercise["xgb_predicted_hr"]=model.predict(transfer[cols].to_numpy())
    exercise["xgb_flag"]=(np.abs(exercise.hr_bpm-exercise.xgb_predicted_hr)>threshold).astype(int)
    exercise.to_csv(a.out/"task10_exercise_transfer_scores.csv",index=False)
    (a.out/"task10_replay_audit.json").write_text(json.dumps({
        "task10_val_mae_retrained":va_mae,"task10_test_mae_retrained":te_mae,
        "task10_published_val_mae":published["splits"]["task9_group_based"]["metrics"]["XGBoost"]["val_MAE"],
        "task10_published_test_mae":published["splits"]["task9_group_based"]["metrics"]["XGBoost"]["test_MAE"],
        "threshold_bpm_published":threshold,"model":"new reconstruction; not a saved original Task10 model",
        "xgboost_version":xgb.__version__,"feature_order":cols},indent=2))
    model.get_booster().save_model(a.out/"task10_replayed_xgboost.json")
    print((a.out/"task10_replay_audit.json").read_text())

if __name__=="__main__":main()
