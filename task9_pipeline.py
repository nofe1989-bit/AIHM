#!/usr/bin/env python3
"""AIHM Task 9 research data preparation from four separate cleaned sources.

Synthetic events are test fixtures, never observed diagnoses. Private exports
use the team's unverified assumption of one distinct wearer per export and
receive within-export chronological splits, not independent-person tests.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def split_for(source, group):
    h=hashlib.sha256(f'AIHM-task9-v2:{source}:{group}'.encode()).digest()
    x=int.from_bytes(h[:8],'big') / 2**64
    return 'train' if x<.6 else ('validation' if x<.8 else 'test')


def write(df, path):
    path.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(path,index=False)


def private_time_split(timestamps, gap=pd.Timedelta(hours=1)):
    """Chronological 60/20/20 split for one assumed wearer per export.

    Rows near each boundary are retained for audit but excluded from modeling.
    No person-independent test is implied by this split.
    """
    t=pd.to_datetime(timestamps,utc=True,format='mixed')
    order=t.sort_values(kind='mergesort')
    n=len(order)
    if n<10:
        raise ValueError('At least ten windows are needed for a private time split')
    train_end=order.iloc[int(n*.6)-1]
    validation_end=order.iloc[int(n*.8)-1]
    split=pd.Series('test',index=t.index,dtype='object')
    split.loc[t.le(train_end)]='train'
    split.loc[t.gt(train_end)&t.le(validation_end)]='validation'
    split.loc[t.gt(train_end)&t.le(train_end+gap)]='gap_after_train'
    split.loc[t.gt(validation_end)&t.le(validation_end+gap)]='gap_after_validation'
    return split,train_end,validation_end


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True,help='Folder with figshare, zenodo_galaxy, lyan, nofe subfolders')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    source_counts={}

    f=pd.read_csv(a.input/'figshare/figshare_sensor_quality_5min.csv')
    f['HR']=pd.to_numeric(f.HR,errors='coerce')
    f=f.loc[f.hrv_quality_pass.eq(True)&f.HR.between(30,220)].copy()
    f['group_id']=f.deviceId.astype(str)
    f['split']=[split_for('figshare_device',v) for v in f.group_id]
    f['start']=pd.to_datetime(f.window_start_utc,utc=True,format='mixed')
    f['end']=pd.to_datetime(f.window_end_utc,utc=True,format='mixed')
    ff=pd.DataFrame({'source':'figshare','group_id':f.group_id,'group_basis':'deviceId','device_alias':f.deviceId,
        'window_start_utc':f.start.dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        'hr_mean_bpm':f.HR,'hr_observations':pd.NA,'coverage':pd.NA,
        'activity_context':'unknown','data_split':f.split})
    write(ff,a.output/'figshare/features_5min.csv')
    source_counts['figshare']={'five_minute_rows':len(ff),'device_groups':int(f.group_id.nunique())}

    z=pd.read_csv(a.input/'zenodo_galaxy/GalaxyWatch_5min.csv')
    z['group_id']=z.uid.astype(str)
    z['split']=[split_for('zenodo_participant',v) for v in z.group_id]
    zz=pd.DataFrame({'source':'zenodo_galaxy','group_id':z.group_id,'group_basis':'uid','device_alias':'galaxy',
        'window_start_utc':z.window_start_utc,'hr_mean_bpm':z.galaxy_hr_mean_bpm,
        'hr_observations':z.galaxy_hr_valid_n,'coverage':z.galaxy_hr_coverage,
        'activity_context':np.where(z.category.notna(),z.category,'unknown'),'data_split':z.split})
    write(zz,a.output/'zenodo_galaxy/features_5min.csv')
    source_counts['zenodo_galaxy']={'five_minute_rows':len(zz),'uid_groups':int(z.group_id.nunique()),
        'valid_hr_windows':int(z.galaxy_hr_valid_n.gt(0).sum())}

    private_splits=[]
    for label in ['lyan','nofe']:
        x=pd.read_csv(a.input/label/'heart_rate_5min.csv')
        split,train_end,validation_end=private_time_split(x.window_start_utc)
        group=label+'_assumed_person_01'
        feat=pd.DataFrame({'source':label+'_collected_export','group_id':group,
            'group_basis':'assumed_one_person_per_export','device_alias':x.device_alias,
            'window_start_utc':x.window_start_utc,'hr_mean_bpm':x.hr_mean_bpm,
            'hr_observations':x.hr_observations,'coverage':x.hr_coverage,
            'activity_context':'unknown','data_split':split,
            'wearer_identity_assumption':'team_assumption_unverified'})
        feat=feat.sort_values('window_start_utc',kind='mergesort')
        write(feat,a.output/label/'features_5min.csv')
        for segment,part in feat.groupby('data_split'):
            private_splits.append({'source':label,'assumed_person_id':group,
                'data_split':segment,'windows':len(part),
                'first_window_utc':part.window_start_utc.min(),
                'last_window_utc':part.window_start_utc.max(),
                'split_method':'chronological_60_20_20_with_1h_boundary_gap',
                'identity_status':'assumed_one_person_per_export_unverified'})
        source_counts[label]={'five_minute_rows':len(feat),
            'device_aliases':int(feat.device_alias.nunique()),
            'split_counts':feat.data_split.value_counts().to_dict(),
            'assumed_person_id':group,
            'train_end_utc':train_end.isoformat(),
            'validation_end_utc':validation_end.isoformat()}
    write(pd.DataFrame(private_splits),a.output/'private_temporal_split.csv')

    split_rows=[]
    split_rows.extend({'source':'figshare','group_id':g,'group_basis':'deviceId','data_split':split_for('figshare_device',g)}
                      for g in sorted(f.group_id.unique()))
    split_rows.extend({'source':'zenodo_galaxy','group_id':g,'group_basis':'uid','data_split':split_for('zenodo_participant',g)}
                      for g in sorted(z.group_id.unique()))
    splits=pd.DataFrame(split_rows)
    write(splits,a.output/'group_split.csv')

    sec=pd.read_csv(a.input/'zenodo_galaxy/GalaxyWatch_hr_1hz.csv')
    valid=sec.hr_galaxy.between(30,220)
    exercise=sec.loc[valid & sec.category.eq('activity') & sec.session.isin(['jogging','running']),
                     ['uid','t_ms','session','hr_galaxy']].copy()
    exercise['time_utc']=pd.to_datetime(exercise.t_ms,unit='ms',utc=True)
    exercise['high_hr_gt_100']=exercise.hr_galaxy.gt(100)
    exercise['data_split']=[split_for('zenodo_participant',v) for v in exercise.uid]
    exercise=exercise.rename(columns={'uid':'group_id','hr_galaxy':'observed_hr_bpm','session':'activity_label'})
    write(exercise[['group_id','time_utc','activity_label','observed_hr_bpm','high_hr_gt_100','data_split']],
          a.output/'exercise_controls_seconds.csv')

    z['t']=pd.to_datetime(z.window_start_utc,utc=True,format='mixed')
    resting=z.loc[z.window_seconds.eq(300)&z.rest_fraction.ge(.8)&z.galaxy_hr_coverage.ge(.8)&
                  z.galaxy_hr_mean_bpm.between(30,220)].sort_values(['uid','t']).copy()
    prev=resting.shift()
    pairs=resting.loc[resting.uid.eq(prev.uid)&(resting.t-prev.t).eq(pd.Timedelta(minutes=5))].copy()
    if len(pairs):
        ph=prev.loc[pairs.index,'galaxy_hr_mean_bpm']
        pairs['research_screening_label']=np.select([pairs.galaxy_hr_mean_bpm.gt(100)&ph.gt(100),
            pairs.galaxy_hr_mean_bpm.lt(50)&ph.lt(50)],['high_candidate','low_candidate'],default='none')
    else:pairs['research_screening_label']=pd.Series(index=pairs.index,dtype=str)
    observed=pairs.rename(columns={'uid':'group_id','galaxy_hr_mean_bpm':'current_hr_mean_bpm'})
    write(observed[['group_id','window_start_utc','current_hr_mean_bpm','research_screening_label']],
          a.output/'observed_10min_rest_candidates.csv')

    # Modify copies of two truly adjacent observed normal Figshare windows.
    # Their rest context is unknown: the *synthetic event* assumes rest, not the source.
    base=f.loc[f.HR.between(60,95)&f.duration_seconds.ge(290)].sort_values(['group_id','start']).copy()
    prev=base.shift()
    consecutive=base.group_id.eq(prev.group_id)&(base.start-prev.start).dt.total_seconds().between(298,302)&\
        (base.start-prev.end).dt.total_seconds().abs().le(3)
    candidate=base.loc[consecutive].copy()
    synthetic_rows=[];events=[]
    for group,subset in candidate.groupby('group_id',sort=True):
        used=set();selected=[]
        for idx in subset.index:
            j=base.index.get_loc(idx)
            if j<1:continue
            first=base.index[j-1]
            if first in used or idx in used:continue
            selected.append((first,idx));used.update((first,idx))
            if len(selected)==2:break
        for kind,ij in zip(('high','low'),selected):
            target=110 if kind=='high' else 45
            event_id=f'SYN_{group}_{kind}_{len(events)+1:03d}'
            first,last=base.loc[list(ij)].sort_values('start').iloc[[0,-1]].to_dict('records')
            for k,row in enumerate((first,last)):
                synthetic_rows.append({'event_id':event_id,'source':'figshare','group_id':group,
                    'data_split':split_for('figshare_device',group),
                    'window_start_utc':row['start'].isoformat(),'window_end_utc':row['end'].isoformat(),
                    'normal_observed_hr_bpm':round(float(row['HR']),4),'injected_hr_bpm':target,
                    'injected_label':kind,'context_for_synthetic_event':'simulated_rest',
                    'source_context':'unknown','is_synthetic':True,'reference_is_observed':True,
                    'source_window_duration_seconds':round(float(row['duration_seconds']),3)})
            events.append({'event_id':event_id,'source':'figshare','group_id':group,
                'data_split':split_for('figshare_device',group),'start_utc':first['start'].isoformat(),
                'end_utc':last['end'].isoformat(),'injected_label':kind,'injected_hr_bpm':target,
                'modified_observed_windows':2,'is_synthetic':True,'source_rest_label_available':False})
    syn_cols=['event_id','source','group_id','data_split','window_start_utc','window_end_utc',
              'normal_observed_hr_bpm','injected_hr_bpm','injected_label','context_for_synthetic_event',
              'source_context','is_synthetic','reference_is_observed','source_window_duration_seconds']
    event_cols=['event_id','source','group_id','data_split','start_utc','end_utc','injected_label',
                'injected_hr_bpm','modified_observed_windows','is_synthetic','source_rest_label_available']
    write(pd.DataFrame(synthetic_rows,columns=syn_cols),a.output/'synthetic_injection_5min.csv')
    write(pd.DataFrame(events,columns=event_cols),a.output/'synthetic_event_manifest.csv')

    audits={'source_counts':source_counts,'split_counts':splits.groupby(['source','data_split']).size().rename('groups').reset_index().to_dict('records'),
        'observed_rest_10min_pairs':len(observed),
        'observed_abnormal_rest_candidates':int(observed.research_screening_label.isin(['high_candidate','low_candidate']).sum()),
        'exercise_labeled_seconds':len(exercise),'exercise_seconds_over_100_bpm':int(exercise.high_hr_gt_100.sum()),
        'synthetic_events':len(events),'synthetic_events_by_split':pd.DataFrame(events).groupby('data_split').size().to_dict() if events else {},
        'research_rule':'For research screening only: two adjacent 5-minute rest windows each with mean HR >100 or <50 bpm, >=80% rest and HR coverage; thresholds from assignment example, not a diagnosis.',
        'split_policy':'Before injection: Zenodo by uid; Figshare by deviceId as a proxy group, not a verified person. Lyan and Nofe each assumed one wearer per export by team instruction, split chronologically approximately 60/20/20 with one-hour boundary gaps. Private validation and test contain later readings from the assumed same person, not unseen people.',
        'synthetic_policy':'Two observed contiguous normal Figshare windows are copied and modified. Rest context exists only as a synthetic assumption; original source rest context is unknown. No observed clinical event is inferred.',
        'private_activity_policy':'No rest or exercise label inferred from heart rate, steps, or collector name.'}
    (a.output/'task9_audit.json').write_text(json.dumps(audits,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(audits,indent=2))


if __name__=='__main__':main()
