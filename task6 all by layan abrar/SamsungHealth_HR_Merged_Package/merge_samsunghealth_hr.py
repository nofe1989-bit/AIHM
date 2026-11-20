#!/usr/bin/env python3
"""Clean a new Samsung Health HR CSV and append to previously prepared records.
No imputation, participant identity inference, or expansion of absent JSON.
Run: python merge_samsunghealth_hr.py --previous PREVIOUS_FOLDER --new NEW.csv --out OUTPUT
Requires pandas>=2.0 and numpy>=1.24.
"""
import argparse,csv,json,hashlib,re
from pathlib import Path
import pandas as pd
import numpy as np


def load_export(path):
    with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
    if not rows or rows[0][0]!='com.samsung.shealth.tracker.heart_rate':
        raise ValueError('Expected Samsung Health HR export with a metadata first row')
    headers=rows[1];data=[]
    for lineno,r in enumerate(rows[2:],3):
        if not any(r):continue
        if len(r)<len(headers) or any(r[len(headers):]):
            raise ValueError(f'Unexpected row shape at line {lineno}')
        data.append(r[:len(headers)])
    names=[c.rsplit('.',1)[-1] for c in headers]
    if len(set(names))!=len(names):raise ValueError('Colliding column names')
    return pd.DataFrame(data,columns=names).mask(lambda d:d.eq(''))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--previous',type=Path,required=True)
    ap.add_argument('--new',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    (out/'audit').mkdir(exist_ok=True)
    raw=load_export(args.new);df=raw.drop_duplicates().copy()
    exact_removed=len(raw)-len(df)
    devices=sorted(df.deviceuuid.dropna().unique())
    # Source identity only. Different device UUIDs do not prove different people.
    aliases={d:f'new_device_{i+1:02d}' for i,d in enumerate(devices)}
    df['source_id_conflict']=df.datauuid.duplicated(False)
    for c in ('start_time','end_time'):
        df[c+'_utc']=pd.to_datetime(df[c],format='mixed',utc=True,errors='coerce')
    df['duration_seconds']=(df.end_time_utc-df.start_time_utc).dt.total_seconds()
    df['time_valid']=df.start_time_utc.notna()&df.end_time_utc.notna()&df.duration_seconds.ge(0)
    df['hr_bpm_raw']=pd.to_numeric(df.heart_rate,errors='coerce')
    df['hr_value_valid']=np.isfinite(df.hr_bpm_raw)&df.hr_bpm_raw.between(30,220)
    df['valid']=df.time_valid&df.hr_value_valid&~df.source_id_conflict
    df['hr_bpm']=df.hr_bpm_raw.where(df.valid)
    df['export_id']='export_02';df['device_id']=df.deviceuuid.map(aliases)
    df['source_datauuid']=df.datauuid
    df['detail_reference']=df.binning_data
    df['missing_json_detail']=df.binning_data.notna()
    df['kind']=np.where(df.missing_json_detail,'interval_summary_missing_details',
                         np.where(df.duration_seconds.eq(0),'spot','interval_summary_without_details'))
    df['device_model']='not_provided';df['device_type_verified']=False
    def minutes(x):
        m=re.fullmatch(r'UTC([+-])(\d{2})(\d{2})',str(x))
        return ((1 if m[1]=='+' else -1)*(int(m[2])*60+int(m[3]))) if m else np.nan
    df['utc_offset_minutes']=df.time_offset.map(minutes)
    df['start_time_local']=df.start_time_utc.dt.tz_localize(None)+pd.to_timedelta(df.utc_offset_minutes,unit='m')
    # Keep source/quality evidence; remove identifying device IDs and free text.
    new_cols=['export_id','device_id','device_model','device_type_verified','source_datauuid',
              'start_time_utc','end_time_utc','start_time_local','utc_offset_minutes',
              'duration_seconds','hr_bpm_raw','hr_bpm','kind','valid','hr_value_valid',
              'time_valid','source_id_conflict','missing_json_detail','detail_reference','min','max']
    new=df[new_cols].sort_values(['device_id','start_time_utc'])
    new.to_csv(out/'New_HR_clean.csv',index=False)
    missing=new.loc[new.missing_json_detail].copy()
    missing.to_csv(out/'audit/New_HR_missing_details.csv',index=False)
    old=pd.read_csv(args.previous/'GalaxyWatch_HR_clean.csv')
    steps=pd.read_csv(args.previous/'GalaxyWatch_steps_clean.csv')
    for d in (old,steps):
        d['device_id']='previous_'+d.device_id.astype(str)
        for c in ('start_time_utc','end_time_utc'):d[c]=pd.to_datetime(d[c],utc=True,format='mixed')
    old['device_model']='Galaxy Watch4 Classic';old['device_type_verified']=True
    old['missing_json_detail']=False;old['hr_bpm_raw']=old.hr_bpm
    old['duration_seconds']=(old.end_time_utc-old.start_time_utc).dt.total_seconds()
    old['utc_offset_minutes']=180
    old['start_time_local']=old.start_time_utc.dt.tz_localize(None)+pd.Timedelta(hours=3)
    columns=['export_id','device_id','device_model','device_type_verified','source_datauuid',
             'start_time_utc','end_time_utc','start_time_local','utc_offset_minutes',
             'duration_seconds','hr_bpm_raw','hr_bpm','kind','valid','missing_json_detail']
    combined=pd.concat([old[columns],new[columns]],ignore_index=True)
    measurement_keys=['export_id','device_id','source_datauuid','start_time_utc','end_time_utc','kind']
    dup=combined.duplicated(measurement_keys)
    removed=combined.loc[dup].copy();removed.to_csv(out/'audit/Combined_duplicate_rows.csv',index=False)
    combined=combined.loc[~dup].sort_values(['device_id','start_time_utc'])
    combined.to_csv(out/'Combined_HR_clean.csv',index=False)
    # Only measurements whose actual temporal resolution can support these bins.
    use=combined.loc[combined.valid & combined.kind.isin(['spot','minute_bin'])].copy()
    use['window_start_utc']=use.start_time_utc.dt.floor('5min')
    keys=['export_id','device_id','window_start_utc']
    hg=use.groupby(keys).agg(hr_mean_bpm=('hr_bpm','mean'),hr_median_bpm=('hr_bpm','median'),
        hr_min_bpm=('hr_bpm','min'),hr_max_bpm=('hr_bpm','max'),hr_sd_bpm=('hr_bpm','std'),
        hr_observations=('hr_bpm','count'),hr_minute_bins=('kind',lambda x:int(x.eq('minute_bin').sum())),
        hr_spot_observations=('kind',lambda x:int(x.eq('spot').sum())))
    steps['window_start_utc']=steps.start_time_utc.dt.floor('5min')
    sg=steps.loc[steps.time_valid].groupby(keys).agg(
        steps_observed_sum=('steps_clean',lambda x:x.sum(min_count=1)),
        step_records=('steps_raw','size'),step_valid_records=('steps_valid','sum'),
        step_records_crossing_boundary=('crosses_5min_boundary','sum'))
    five=hg.join(sg,how='outer').reset_index().sort_values(['device_id','window_start_utc'])
    five['hr_observed']=five.hr_observations.notna()
    five['steps_observed']=five.step_valid_records.fillna(0).gt(0)
    # Never link a new source's HR to the old source's steps just by time.
    off={('export_01',d):180 for d in old.device_id.unique()}
    for (e,d),g in new.groupby(['export_id','device_id']):
        unique=g.utc_offset_minutes.dropna().unique()
        off[(e,d)]=unique[0] if len(unique)==1 else np.nan
    five['utc_offset_minutes']=[off.get((r.export_id,r.device_id),np.nan) for r in five.itertuples()]
    five['window_start_local']=five.window_start_utc.dt.tz_localize(None)+pd.to_timedelta(five.utc_offset_minutes,unit='m')
    five['local_hour']=five.window_start_local.dt.hour
    five['device_type_verified']=five.export_id.eq('export_01')
    five.to_csv(out/'Combined_HR_5min.csv',index=False)
    # Reconciliation and integrity gates.
    assert int(five.hr_observations.sum())==len(use)
    assert np.isclose(five.steps_observed_sum.sum(),steps.steps_clean.sum())
    assert not five.duplicated(keys).any()
    assert not combined.duplicated(measurement_keys).any()
    assert combined.loc[combined.export_id.eq('export_01'),'hr_bpm'].sum()==old.hr_bpm.sum()
    assert five.loc[five.export_id.eq('export_02'),'steps_observed_sum'].isna().all()
    previous_five=pd.read_csv(args.previous/'GalaxyWatch_5min.csv') if (args.previous/'GalaxyWatch_5min.csv').exists() else None
    if previous_five is not None:
        prior_result=five.loc[five.export_id.eq('export_01')].copy()
        prior_result['device_id']=prior_result.device_id.str.removeprefix('previous_')
        previous_five['window_start_utc']=pd.to_datetime(previous_five.window_start_utc,utc=True,format='mixed')
        previous_five['window_start_local']=pd.to_datetime(previous_five.window_start_local,format='mixed')
        check_cols=list(previous_five.columns)
        pd.testing.assert_frame_equal(
            prior_result[check_cols].sort_values(keys).reset_index(drop=True),
            previous_five.sort_values(keys).reset_index(drop=True),check_dtype=False)
    counts={
        'new_source_file':args.new.name,'new_source_sha256':hashlib.sha256(args.new.read_bytes()).hexdigest(),
        'new_input_rows':len(raw),'new_exact_duplicate_rows_removed':exact_removed,
        'new_invalid_value_rows':int((~df.hr_value_valid).sum()),'new_invalid_time_rows':int((~df.time_valid).sum()),
        'new_conflicting_source_id_rows':int(df.source_id_conflict.sum()),
        'new_clean_rows':len(new),'new_valid_rows':int(new.valid.sum()),
        'new_point_rows':int((new.valid & new.kind.eq('spot')).sum()),
        'new_interval_summaries_missing_json':len(missing),
        'new_days_utc':int(new.start_time_utc.dt.date.nunique()),
        'new_start_utc':str(new.start_time_utc.min()),'new_end_utc':str(new.end_time_utc.max()),
        'previous_hr_rows':len(old),'combined_hr_rows':len(combined),
        'combined_duplicate_rows_removed':len(removed),'combined_5min_eligible_hr_observations':len(use),
        'combined_5min_rows':len(five),'new_5min_rows':int(five.export_id.eq('export_02').sum()),
        'windows_with_hr':int(five.hr_observed.sum()),'windows_with_steps':int(five.steps_observed.sum()),
        'windows_with_hr_and_steps':int((five.hr_observed&five.steps_observed).sum()),
        'participant_count_verified':None,'new_device_type_verified':False,
        'time_convention':'CSV interpreted as UTC consistent with earlier Samsung export; new CSV has no JSON to independently verify this convention',
        'new_sources':[{'export_id':'export_02','device_id':alias,'type':'not_verified_without_device_profile'} for alias in aliases.values()]}
    (out/'audit/merge_audit.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
    grouped=combined.assign(date_utc=combined.start_time_utc.dt.strftime('%Y-%m-%d')).groupby(['export_id','device_id','date_utc']).agg(hr_rows=('kind','size'),interval_summaries=('missing_json_detail','sum'))
    grouped.to_csv(out/'audit/Daily_record_counts.csv')
    print(json.dumps(counts,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
