"""Initial Task 13 evaluation using frozen Task 11 models.
Usage: python evaluate_task13.py --task11 PATH.zip --out results
No training, threshold tuning, or final model selection is performed.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, f1_score

def evaluate(archive, out):
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        def read(n): return pd.read_csv(z.open(n), dtype={"group_id":str, "wearer_group":str})
        def model(n): return joblib.load(io.BytesIO(z.read("output/models/"+n)))
        metrics=json.loads(z.read("output/metrics.json"))
        fig=read("input/figshare_checked_5min.csv").rename(columns={"wearer_group":"group_id","mean_HR":"hr_bpm"})
        groups=read("input/group_split.csv")
        fig=fig.merge(groups.loc[groups.source.eq("figshare"),["group_id","data_split"]],on="group_id",validate="many_to_one")
        fig["time"]=pd.to_datetime(fig.window_start_utc,utc=True,format="mixed").dt.floor("5min")
        assert not fig.duplicated(["group_id","time"]).any()
        fig["steps_missing"]=fig.steps_total.isna().astype(int)
        saved=model("figshare_global.joblib")
        assert saved["columns"]==["hr_bpm","steps_total","steps_missing"]
        syn=read("input/synthetic_injection_5min.csv")
        syn["time"]=pd.to_datetime(syn.window_start_utc,utc=True,format="mixed").dt.floor("5min")
        summaries=[]
        def baseline(hr): return ((hr>100)|(hr<60)).to_numpy(dtype=int)
        def flag(frame,bundle):
            scores=bundle["pipeline"].score_samples(frame[bundle["columns"]])
            return scores,(scores<=bundle["threshold"]).astype(int)
        for phase in ("validation","test"):
            injected=syn.loc[syn.data_split.eq(phase)].copy()
            paired=injected.merge(fig[["group_id","time","data_split","hr_bpm","steps_total","steps_missing"]],
                                  on=["group_id","time","data_split"],validate="many_to_one")
            assert len(paired)==len(injected)
            assert np.allclose(paired.normal_observed_hr_bpm,paired.hr_bpm,atol=.0001)
            assert paired.hr_bpm.between(50,100,inclusive="both").all()
            pieces=[]
            for label in [0,1]:
                a=paired.copy()
                a["label"]=label
                if label: a["hr_bpm"]=a.injected_hr_bpm
                a["baseline_prediction"]=baseline(a.hr_bpm)
                a["if_score"],a["if_prediction"]=flag(a,saved)
                a["sample_type"]="injected" if label else "original_reference"
                pieces.append(a)
            bench=pd.concat(pieces,ignore_index=True)
            bench["sample_id"]=[f"{phase}_{i:04d}" for i in range(len(bench))]
            bench.to_csv(out/f"paired_synthetic_{phase}_scores.csv",index=False)
            for name,column in [("FixedThreshold","baseline_prediction"),("IsolationForest","if_prediction")]:
                y,pred=bench.label,bench[column]
                tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
                precision,recall,f1,_=precision_recall_fscore_support(y,pred,average="binary",zero_division=0)
                events=bench.loc[bench.label.eq(1)].groupby("event_id")[column].agg(["min","max"])
                summaries.append(dict(split=phase,model=name,reference_windows=int((y==0).sum()),
                    injected_windows=int((y==1).sum()),tn=int(tn),fp=int(fp),fn=int(fn),tp=int(tp),
                    precision=float(precision),recall=float(recall),f1=float(f1),
                    macro_f1=float(f1_score(y,pred,average="macro",labels=[0,1],zero_division=0)),
                    synthetic_events=len(events),events_both_windows_flagged=int(events["min"].sum()),
                    events_any_window_flagged=int(events["max"].sum())))
        pd.DataFrame(summaries).to_csv(out/"paired_synthetic_metrics.csv",index=False)
        # Recheck all held-out original windows. These have no verified binary labels.
        public=[]
        for name,data,bundle in [("figshare",fig,saved),
                               ("galaxy",read("input/galaxy_task9_5min.csv").rename(columns={"hr_mean_bpm":"hr_bpm"}),model("galaxy_global.joblib"))]:
            if name=="galaxy":
                data["time"]=pd.to_datetime(data.window_start_utc,utc=True,format="mixed")
                hour=data.time.dt.hour+data.time.dt.minute/60
                data["hour_sin"]=np.sin(2*np.pi*hour/24);data["hour_cos"]=np.cos(2*np.pi*hour/24)
            for phase in ("validation","test"):
                a=data.loc[data.data_split.eq(phase)].copy()
                a["if_score"],a["if_prediction"]=flag(a,bundle)
                a["baseline_prediction"]=baseline(a.hr_bpm)
                a.to_csv(out/f"{name}_{phase}_unlabelled_scores.csv",index=False)
                for label,col in [("FixedThreshold","baseline_prediction"),("IsolationForest","if_prediction")]:
                    public.append(dict(source=name,split=phase,model=label,windows=len(a),flags=int(a[col].sum()),
                                       flag_rate=float(a[col].mean()),interpretation="Unlabelled flag rate, not clinical false alarm rate"))
        pd.DataFrame(public).to_csv(out/"public_unlabelled_flag_rates.csv",index=False)
        # Activity-context controls use the same 5-minute windows as Task 11.
        exercise=read("output/galaxy_exercise_control_scores.csv")
        exercise["if_prediction"]=exercise.flagged.astype(int)
        exercise["baseline_prediction"]=baseline(exercise.hr_bpm)
        exercise=exercise.loc[exercise.data_split.isin(["validation","test"])]
        exercise.to_csv(out/"exercise_control_window_scores.csv",index=False)
        erows=[]
        for phase,a in exercise.groupby("data_split"):
            for label,col in [("FixedThreshold","baseline_prediction"),("IsolationForest","if_prediction")]:
                erows.append(dict(split=phase,model=label,exercise_windows=len(a),flags=int(a[col].sum()),
                                  exercise_control_flag_rate=float(a[col].mean()),
                                  windows_mean_hr_over_100=int(a.hr_bpm.gt(100).sum())))
        pd.DataFrame(erows).to_csv(out/"exercise_control_metrics.csv",index=False)
        # Private later windows are scored with the Figshare global model as a transfer check.
        # Lyan's saved personal model is an additional separate experiment.
        bounds=read("input/private_temporal_split.csv")
        private_rows=[]
        for name in ["lyan","nofe"]:
            d=read(f"input/{name}_task9_5min.csv").rename(columns={"hr_mean_bpm":"hr_bpm"})
            d["time"]=pd.to_datetime(d.window_start_utc,utc=True,format="mixed")
            d["steps_total"]=np.nan;d["steps_missing"]=1
            hour=d.time.dt.hour+d.time.dt.minute/60
            d["hour_sin"]=np.sin(2*np.pi*hour/24);d["hour_cos"]=np.cos(2*np.pi*hour/24)
            for phase in ("validation","test"):
                b=bounds.loc[bounds.source.eq(name)&bounds.data_split.eq(phase)].iloc[0]
                a=d.loc[d.time.between(pd.to_datetime(b.first_window_utc,utc=True),pd.to_datetime(b.last_window_utc,utc=True))].copy()
                a["baseline_prediction"]=baseline(a.hr_bpm)
                a["if_global_score"],a["if_global_prediction"]=flag(a,saved)
                columns=[("FixedThreshold","baseline_prediction"),("IF_Figshare_transfer","if_global_prediction")]
                if name=="lyan":
                    a["if_personal_score"],a["if_personal_prediction"]=flag(a,model("lyan_personal.joblib"))
                    columns.append(("IF_Lyan_personal","if_personal_prediction"))
                a.to_csv(out/f"{name}_{phase}_unlabelled_scores.csv",index=False)
                for label,col in columns:
                    private_rows.append(dict(source=name,split=phase,model=label,windows=len(a),flags=int(a[col].sum()),
                        flag_rate=float(a[col].mean()),interpretation="Unlabelled; no accuracy, F1 or false alarm claim"))
        pd.DataFrame(private_rows).to_csv(out/"private_unlabelled_flag_rates.csv",index=False)
        status=dict(status="partial",baseline_rule="HR > 100 OR HR < 60, per five-minute window; no rest/persistence condition",
            threshold_policy="Reuse frozen Task 11 thresholds; do not tune on Task 13 test samples",
            task11_sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
            features=saved["columns"],task11_thresholds={r["source"]:r["selection"]["threshold"] for r in metrics["global_models"]},
            pending=["Task 10 model bundles, feature preparation, inference code and validation/test split identifiers",
                     "Trained Task 12 model and inference code if this optional model will be compared",
                     "Final selection from validation results on a common sample cohort",
                     "Selected model export, Android integration and Python/Android numerical parity check"],
            limitations=["Paired reference windows are not independently clinically verified normal",
                         "Synthetic benchmark deliberately balanced; precision does not estimate deployed alert precision",
                         "Two windows per synthetic event are dependent; event summaries also supplied",
                         "Some Galaxy exercise windows mix activities; exercise control rate is descriptive only",
                         "Baseline is evaluated on window means; short high-HR seconds may be hidden",
                         "Private exports have assumed wearer grouping, no trusted activity/abnormal labels",
                         "Task 11 test results were previously inspected; this is a reproducibility check, not a new untouched final test"])
        (out/"evaluation_status.json").write_text(json.dumps(status,indent=2)+"\n")
        print(pd.DataFrame(summaries).to_string(index=False))
        print(pd.DataFrame(erows).to_string(index=False))
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--task11",type=Path,required=True);ap.add_argument("--out",type=Path,default=Path("results"))
    args=ap.parse_args();evaluate(args.task11,args.out)
