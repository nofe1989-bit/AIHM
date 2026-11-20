"""Task 13 comparison, frozen model selection and ONNX parity audit.

Inputs are the supplied T10/T11/T12 files and the precomputed T10 replay.
The selection policy is based solely on validation synthetic pairs and
validation exercise controls. Test results are reported after selection.
"""
import argparse
import io
import json
import zipfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import onnx
import onnxruntime as ort
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, f1_score
from skl2onnx import to_onnx


def binary(y,p):
    tn,fp,fn,tp=confusion_matrix(y,p,labels=[0,1]).ravel()
    precision,recall,f1,_=precision_recall_fscore_support(y,p,average="binary",zero_division=0)
    return dict(n=int(len(y)),tn=int(tn),fp=int(fp),fn=int(fn),tp=int(tp),
                precision=float(precision),recall=float(recall),f1=float(f1),
                macro_f1=float(f1_score(y,p,average="macro",labels=[0,1],zero_division=0)))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--task11",required=True,type=Path)
    ap.add_argument("--task10-replay",required=True,type=Path)
    ap.add_argument("--task12-results",required=True,type=Path)
    ap.add_argument("--initial",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    pairs=[]
    xgb=pd.read_csv(args.task10_replay/"task10_replay_paired_scores.csv")
    for split in ("validation","test"):
        d=pd.read_csv(args.initial/f"paired_synthetic_{split}_scores.csv")
        src=xgb[xgb.data_split.eq(split)].copy()
        d["slot"]=pd.to_datetime(d.time,utc=True).dt.floor("5min")
        src["slot"]=pd.to_datetime(src.slot,utc=True)
        d=d.merge(src[["event_id","group_id","slot","label","xgb_flag","absolute_residual_bpm"]],
                  on=["event_id","group_id","slot","label"],validate="one_to_one")
        assert len(d)==(72 if split=="validation" else 88)
        pairs.append(d)
    pairs=pd.concat(pairs,ignore_index=True)
    pairs.to_csv(out/"same_window_model_comparison.csv",index=False)
    exercise=pd.read_csv(args.initial/"exercise_control_window_scores.csv")
    xexercise=pd.read_csv(args.task10_replay/"task10_exercise_transfer_scores.csv")
    exercise=exercise.merge(xexercise[["group_id","time","data_split","xgb_flag","xgb_predicted_hr"]],
                            on=["group_id","time","data_split"],validate="one_to_one")
    with zipfile.ZipFile(args.task11) as z:
        selected_bundle=joblib.load(io.BytesIO(z.read("output/models/figshare_global.joblib")))
    exercise["galaxy_if_prediction"]=exercise["if_prediction"]
    transfer=exercise[["hr_bpm"]].copy()
    transfer["steps_total"]=np.nan
    transfer["steps_missing"]=1
    exercise["if_figshare_transfer_score"]=selected_bundle["pipeline"].score_samples(transfer[selected_bundle["columns"]])
    exercise["if_prediction"]=(exercise.if_figshare_transfer_score<=selected_bundle["threshold"]).astype(int)
    exercise.to_csv(out/"exercise_control_comparison.csv",index=False)
    methods={"Fixed HR threshold":"baseline_prediction","Task10 XGBoost replay":"xgb_flag",
             "Task11 Isolation Forest":"if_prediction"}
    summary=[]
    for split in ("validation","test"):
        g=pairs[pairs.data_split.eq(split)]
        e=exercise[exercise.data_split.eq(split)]
        for model,col in methods.items():
            q=binary(g.label,g[col]);events=g.loc[g.label.eq(1)].groupby("event_id")[col]
            flags=int(e[col].sum())
            summary.append(dict(split=split,model=model,reference_windows=int((g.label==0).sum()),
                injected_windows=int((g.label==1).sum()),synthetic_events=int(events.ngroups),
                events_both_windows_flagged=int(events.min().sum()),
                events_any_window_flagged=int(events.max().sum()),
                exercise_control_windows=len(e),exercise_flags=flags,
                exercise_flag_rate=float(flags/len(e)),**q))
    report=pd.DataFrame(summary);report.to_csv(out/"comparison_metrics.csv",index=False)
    # One deterministic validation-only selection policy: among approaches
    # detecting all 18 validation events with both windows, minimize observed
    # exercise flags; then maximize paired F1, then prefer the frozen model.
    v=report[report.split.eq("validation")].copy()
    feasible=v[v.events_both_windows_flagged.eq(v.synthetic_events)]
    feasible=feasible.sort_values(["exercise_flags","f1","model"],ascending=[True,False,True])
    chosen=str(feasible.iloc[0].model)
    assert chosen=="Task11 Isolation Forest",feasible.to_string(index=False)

    with zipfile.ZipFile(args.task11) as z:
        bundle=joblib.load(io.BytesIO(z.read("output/models/figshare_global.joblib")))
        assert bundle["columns"]==["hr_bpm","steps_total","steps_missing"]
        threshold=float(bundle["threshold"])
        expected_feature_median=bundle["pipeline"].named_steps["simpleimputer"].statistics_.tolist()
        # Parity cohort: public val+test, private val+test, paired synthetics,
        # and known activity controls. Excludes train from the holdout audit.
        frames=[(f"paired_{s}",pairs[pairs.data_split.eq(s)]) for s in ("validation","test")]
        for source in ("figshare","galaxy","lyan","nofe"):
            for split in ("validation","test"):
                if source=="galaxy":continue # Galaxy has a distinct saved model/features.
                filename=(args.initial/f"{source}_{split}_unlabelled_scores.csv")
                a=pd.read_csv(filename)
                if source=="figshare":
                    a=a.rename(columns={"mean_HR":"hr_bpm"})
                    a["steps_missing"]=a.steps_total.isna().astype(int)
                else:
                    a=a.rename(columns={"hr_mean_bpm":"hr_bpm"})
                    a["steps_total"]=np.nan;a["steps_missing"]=1
                frames.append((source+"_"+split,a))
        # Exercise controls use Figshare IF with missing steps, the same model
        # selected for deployment; include them in the ONNX parity audit.
        ex=exercise.copy();ex["steps_total"]=np.nan;ex["steps_missing"]=1
        frames.append(("galaxy_exercise_transfer",ex))
        X=pd.concat([f[["hr_bpm","steps_total","steps_missing"]] for _,f in frames],ignore_index=True)
        cohort=[]
        for name,frame in frames:cohort.extend([name]*len(frame))
        X=X.astype(np.float32)
        native_score=bundle["pipeline"].score_samples(X)
        onx=to_onnx(bundle["pipeline"],X.iloc[:1].to_numpy(),
                    target_opset={"":15,"ai.onnx.ml":3},
                    options={id(bundle["pipeline"][-1]):{"score_samples":True}})
        score_output=next(v for v in onx.graph.output if v.name=="score_samples")
        score_output.type.tensor_type.shape.dim.add().dim_param="N"
        score_output.type.tensor_type.shape.dim.add().dim_value=1
        model_path=out/"selected_figshare_isolation_forest.onnx"
        model_path.write_bytes(onx.SerializeToString())
        onnx.checker.check_model(onnx.load(str(model_path)))
        sess=ort.InferenceSession(str(model_path),providers=["CPUExecutionProvider"])
        assert [i.name for i in sess.get_inputs()]==["X"]
        assert "score_samples" in [i.name for i in sess.get_outputs()]
        onnx_score=sess.run(["score_samples"],{"X":X.to_numpy()})[0].reshape(-1)
        native_flag=(native_score<=threshold).astype(int)
        onnx_flag=(onnx_score<=threshold).astype(int)
        dif=np.abs(native_score-onnx_score)
        parity=pd.DataFrame({"cohort":cohort,"hr_bpm":X.hr_bpm,"steps_total":X.steps_total,
                             "steps_missing":X.steps_missing,"sklearn_score":native_score,
                             "onnxruntime_score":onnx_score,"sklearn_flag":native_flag,
                             "onnxruntime_flag":onnx_flag,"abs_score_difference":dif})
        parity.to_csv(out/"python_onnx_parity_samples.csv",index=False)
        parity_summary={"sample_count":len(parity),"max_absolute_score_difference":float(dif.max()),
                        "mean_absolute_score_difference":float(dif.mean()),
                        "decision_mismatches":int((native_flag!=onnx_flag).sum()),
                        "comparison":"scikit-learn 1.8.0 vs ONNX Runtime Python 1.32.0; Android app parity not tested"}
        assert parity_summary["decision_mismatches"]==0
        assert parity_summary["max_absolute_score_difference"]<1e-5
        (out/"python_onnx_parity_summary.json").write_text(json.dumps(parity_summary,indent=2))
        config={"selected_model":"Task11 Figshare global Isolation Forest",
                "model_file":model_path.name,"input_name":"X","output_name":"score_samples",
                "input_shape":[1,3],"feature_order":bundle["columns"],
                "numeric_scaling":"none; SimpleImputer median is embedded in ONNX",
                "imputer_medians":expected_feature_median,
                "missing_steps_policy":"steps_total=NaN and steps_missing=1; if observed, value and 0",
                "threshold":threshold,"flag_rule":"score_samples <= threshold",
                "window_minutes":5,"input_hr":"mean HR in BPM for completed 5-minute window",
                "activity_context":"model input does not encode verified exercise; app must collect context separately"}
        (out/"scaler_and_inference.json").write_text(json.dumps(config,indent=2))
        # Save the frozen original as provenance and for Python-only replay.
        (out/"selected_model_source.sha256").write_text(__import__('hashlib').sha256(z.read("output/models/figshare_global.joblib")).hexdigest()+"\n")
    task12=json.loads((args.task12_results/"thresholds_and_metrics.json").read_text())
    selection={"selection_policy":"Validation: require both windows detected in every synthetic event; minimize flags on observed exercise controls; tie-break paired F1. Test not used to select.",
               "selected":chosen,"selected_threshold_from_task11":threshold,
               "matched_5min_comparison":"Task9 paired synthetic Figshare windows and separate GalaxyPPG exercise controls",
               "task10_replay":json.loads((args.task10_replay/"task10_replay_audit.json").read_text()),
               "task12_sequence_results":task12["methods"],
               "private_unlabelled":pd.read_csv(args.initial/"private_unlabelled_flag_rates.csv").to_dict(orient="records"),
               "parity":parity_summary,
               "integration_status":"ONNX integrated in supplied AIHM-Rawan Android source; compilation and on-device parity unverified"}
    (out/"selection_and_status.json").write_text(json.dumps(selection,indent=2))
    print(report.to_string(index=False));print('chosen',chosen);print('parity',parity_summary)

if __name__=='__main__':main()
