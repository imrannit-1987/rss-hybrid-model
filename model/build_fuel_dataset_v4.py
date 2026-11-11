"""Fuel dataset v4: WEEKLY truth (weekly reports: daily fuel + site DG meter kWh) alongside the monthly truth,
with extended per-family features from hourly unit counters. All features scaled to the report's site DG-meter kWh.
usage: build_fuel_dataset_v4.py gen_hourly.csv.gz site_day.csv month_truth.csv gen_families.csv weekly_daily_all.csv out_week.csv out_month.csv"""
import sys, os, pandas as pd, numpy as np
sys.path.insert(0,os.path.dirname(__file__)); from weekly_names import WEEKLY
gh,sdp,mtp,gfp,wkp,outw,outm=sys.argv[1:8]
D=pd.read_csv(gh,parse_dates=['t']); sd=pd.read_csv(sdp,parse_dates=['date']); T=pd.read_csv(mtp,parse_dates=['month']); GF=pd.read_csv(gfp).drop_duplicates('dev_clean').set_index('dev_clean')
KV=[(0,150,'≤125 kVA'),(150,235,'200–220 kVA'),(235,275,'250 kVA'),(275,325,'300 kVA'),(325,400,'350 kVA'),(400,650,'500 kVA'),(650,900,'800 kVA'),(900,1400,'1000–1250 kVA')]
D['kcls']=D.kva.map(lambda k:next(n for lo,hi,n in KV if lo<=k<hi))
D['fam']=D.gen.map(GF.family); D['fam']=D.fam.fillna(D.kcls.map(lambda c:f'unlisted {c}'))
D=D.sort_values(['project','gen','t'])
D['date']=D.t.dt.normalize(); D['rated']=D.kva*0.8; D['rated_h']=D.rated*D.run
D['l']=np.where(D.run>0.05,D.kwh/(D.rated*D.run.clip(lower=0.05)),0).clip(0,1.2)
D['kwh_l']=D.kwh*D.l; D['kwh_l2']=D.kwh*D.l**2
D['rh_low']=D.rated_h*(D.l<0.25)                       # rated kW-hours spent below 25% loading
gap=D.groupby(['project','gen']).t.diff().dt.total_seconds().div(3600)
D['starts']=((gap.isna())|(gap>1.01)).astype(float)*D.rated   # rated kW started
FEATS=['rated_h','kwh','kwh_l','kwh_l2','rh_low','starts']
# day quality: unit counters vs portal site DG meter
dq=D.groupby(['project','date']).kwh.sum().rename('ck').reset_index().merge(sd[['project','date','dg_kwh']],on=['project','date'],how='left')
dq['r']=dq.ck/dq.dg_kwh
ref=dq[dq.dg_kwh>100].groupby('project').r.median().clip(0.9,1.15).rename('ref'); dq=dq.join(ref,on='project')
dq['good']=(dq.dg_kwh.fillna(0)<=20)|((dq.r/dq.ref).between(0.94,1.06)); dq.loc[dq.dg_kwh.isna(),'good']=False
D=D.merge(dq[['project','date','good']],on=['project','date'])
F=D[D.good]
dayf=F.groupby(['project','date','fam'])[FEATS].sum().unstack('fam').fillna(0); dayf.columns=[f'{a}|{b}' for a,b in dayf.columns]
dayf['ck']=F.groupby(['project','date']).kwh.sum()
nun=F[F.run>0.5].groupby(['project','date']).gen.nunique().rename('units_run'); dayf=dayf.join(nun)
feat=[c for c in dayf.columns if '|' in c]

# Sites where part of the solar feeds in at a local board (confirmed by RSS): the load meter does not see that solar, so
# "load - solar" understates the generators by the locally-fed share. Share k estimated per site from days with good data:
# generator counters = (load - solar) + k * solar.
LOCAL_SOLAR=['UAE - Target - C','UAE - Galfar - C','KSA - Fame Fardani - C']   # AYTB Jubail also has local solar but its meter gap does not vary with solar (fixed offset), so no correction is applied there
kd=dq.merge(sd[['project','date','solar_kwh']],on=['project','date'],how='left'); kd=kd[kd.project.isin(LOCAL_SOLAR)&(kd.dg_kwh>200)&(kd.solar_kwh>0)&kd.r.between(0.85,1.35)]
K=(kd.groupby('project').apply(lambda g:(g.ck-g.dg_kwh).sum()/g.solar_kwh.sum())).clip(0,1).to_dict()
print('local solar share k:',{p:round(v,3) for p,v in K.items()})
pd.Series(K,name='local_solar_share').rename_axis('project').to_csv(os.path.join(os.path.dirname(outw),'local_solar_share.csv'))
def finish(X,label):
    X=X.copy(); kk=X.index.get_level_values(0).map(lambda p:K.get(p,0.0)).values
    X['dg_reported']=X.dg; X['dg']=X.dg+kk*X.solar.fillna(0); X['scale']=X.dg/X.ck; X[feat]=X[feat].mul(X.scale,axis=0)
    X['country']=X.index.get_level_values(0).str[:3]; n0=len(X)
    X=X[(X.fuel>0)&(X.dg>0)&X.scale.between(0.8,1.6)]
    X['eff']=X.fuel/X.dg; X=X[X.eff.between(0.15,1.5)]
    print(f'{label}: {len(X)} of {n0}; {X.index.get_level_values(0).nunique()} sites; scale median {X.scale.median():.3f}'); return X

# ---- weekly truth ----
w=pd.read_csv(wkp,parse_dates=['date']); w['project']=w.sheet.map(WEEKLY); w=w.dropna(subset=['project','fuel','dg'])
w=w.sort_values(['project','date','file']).drop_duplicates(['project','date'],keep='last')
w=w[(w.dg>0)&(w.fuel>=0)]
w=w[~((w.dg>50)&(w.fuel/w.dg<0.1))]      # zero/near-zero fuel on a day the generators ran = missing reading, not a real zero
w=w.merge(dayf.reset_index(),on=['project','date'],how='inner')            # only days with good counters
w['week']=w.date.dt.to_period('W-SUN').dt.start_time
agg={c:'sum' for c in feat+['ck','fuel','dg','load','solar']}; agg.update(days=('date','size')) if False else None
W=w.groupby(['project','week'])[feat+['ck','fuel','dg','load','solar','fuel_estimated','refuel_day']].sum()
W['days']=w.groupby(['project','week']).size(); W['kwp']=w.groupby(['project','week']).kwp.median()
W=W[W.days>=5]
# reconcile to the MONTHLY report (final truth): scale each week's fuel by that site-month's monthly/weekly efficiency ratio
w['month']=w.date.dt.to_period('M').dt.to_timestamp()
mw=w.groupby(['project','month']).agg(wf=('fuel','sum'),wdg=('dg','sum'),nd=('fuel','size')).join(T.set_index(['project','month'])[['fuel','dg']].rename(columns={'fuel':'mf','dg':'mdg'}),how='left')
mw['rec']=((mw.mf/mw.mdg)/(mw.wf/mw.wdg)).where((mw.nd>=20)&(mw.mf>0)&(mw.mdg>0))
mw['rec']=mw.rec.where(mw.rec.between(0.75,1.35))
w=w.join(mw.rec,on=['project','month']); w['fuel_rec']=w.fuel*w.rec
Wr=w.groupby(['project','week']).agg(fuel_rec=('fuel_rec',lambda x:x.sum(min_count=len(x))),rec=('rec','mean'))
W=W.join(Wr); W['fuel_weekly_report']=W.fuel
W=finish(W,'weekly'); W['month']=W.index.get_level_values(1).to_period('M').to_timestamp() if False else pd.DatetimeIndex(W.index.get_level_values(1)).to_period('M').to_timestamp()
W.to_csv(outw)
Wm=W.dropna(subset=['fuel_rec']).copy(); Wm['fuel']=Wm.fuel_rec; Wm['eff']=Wm.fuel/Wm.dg; Wm=Wm[Wm.eff.between(0.15,1.5)]
Wm.to_csv(outw.replace('.csv','_rec.csv')); print(f'weekly reconciled to monthly reports: {len(Wm)} weeks; {Wm.index.get_level_values(0).nunique()} sites; median adjustment {Wm.rec.median():.3f}')
# ---- monthly truth (as v3, extended features) ----
dq['month']=dq.date.dt.to_period('M').dt.to_timestamp()
dm=dayf.reset_index(); dm['month']=dm.date.dt.to_period('M').dt.to_timestamp()
M=dm.groupby(['project','month'])[feat+['ck']].sum()
dgg=dq[dq.good].groupby(['project','month']).dg_kwh.sum().rename('dg_good'); dga=dq.groupby(['project','month']).dg_kwh.sum().rename('dg_portal')
M=M.join(dgg).join(dga).join(T.set_index(['project','month'])[['fuel','dg','load','solar','kwp']],how='inner')
M['good_share']=M.dg_good/M.dg_portal; M=M[M.good_share>=0.5]
M=finish(M,'monthly'); M.to_csv(outm)
