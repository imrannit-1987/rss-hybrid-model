"""Site-month fuel dataset v3: truth = monthly-report fuel & DG kWh; features from hourly unit counters, by engine family.
Day-level quality check (unit counters vs portal site DG meter), month features scaled to the report's DG kWh.
usage: build_fuel_dataset_v3.py gen_hourly.csv.gz site_day.csv month_truth.csv gen_families.csv out.csv"""
import sys, pandas as pd, numpy as np
gh,sdp,mtp,gfp,out=sys.argv[1:6]
D=pd.read_csv(gh,parse_dates=['t']); sd=pd.read_csv(sdp,parse_dates=['date']); T=pd.read_csv(mtp,parse_dates=['month']); GF=pd.read_csv(gfp).drop_duplicates('dev_clean').set_index('dev_clean')
KV=[(0,150,'≤125 kVA'),(150,235,'200–220 kVA'),(235,275,'250 kVA'),(275,325,'300 kVA'),(325,400,'350 kVA'),(400,650,'500 kVA'),(650,900,'800 kVA'),(900,1400,'1000–1250 kVA')]
D['kcls']=D.kva.map(lambda k:next(n for lo,hi,n in KV if lo<=k<hi))
D['fam']=D.gen.map(GF.family)
D['fam']=D.fam.fillna(D.kcls.map(lambda c:f'unlisted {c}'))
D['hours']=D.gen.map(GF.hours_n); D['year']=D.gen.map(GF.year_n)
D['date']=D.t.dt.normalize(); D['rated']=D.kva*0.8; D['rated_h']=D.rated*D.run
D['l']=np.where(D.run>0.05,D.kwh/(D.rated*D.run.clip(lower=0.05)),0).clip(0,1.2); D['kwh_l']=D.kwh*D.l
D['rh_hours']=D.rated_h*D.hours.fillna(D.hours.median()); D['kwh_hours']=D.kwh*D.hours.fillna(D.hours.median())
# day quality vs portal DG meter
dq=D.groupby(['project','date']).kwh.sum().rename('ck').reset_index().merge(sd[['project','date','dg_kwh']],on=['project','date'],how='left')
dq['r']=dq.ck/dq.dg_kwh
ref=dq[dq.dg_kwh>100].groupby('project').r.median().clip(0.9,1.15).rename('ref'); dq=dq.join(ref,on='project')
dq['good']=(dq.dg_kwh.fillna(0)<=20)|((dq.r/dq.ref).between(0.94,1.06))
dq.loc[dq.dg_kwh.isna(),'good']=False
D=D.merge(dq[['project','date','good']],on=['project','date'])
D['month']=D.date.dt.to_period('M').dt.to_timestamp()
F=D[D.good]
Mf=F.groupby(['project','month','fam'])[['rated_h','kwh','kwh_l']].sum().unstack('fam').fillna(0); Mf.columns=[f'{a}|{b}' for a,b in Mf.columns]
Mk=F.groupby(['project','month','kcls'])[['rated_h','kwh','kwh_l']].sum().unstack('kcls').fillna(0); Mk.columns=[f'{a}|K:{b}' for a,b in Mk.columns]
Mx=F.groupby(['project','month'])[['rh_hours','kwh_hours','rated_h','kwh']].sum(); Mx['fleet_hours']=Mx.kwh_hours/Mx.kwh.replace(0,np.nan); Mx=Mx[['fleet_hours']]
ck=F.groupby(['project','month']).kwh.sum().rename('ck_good'); gd=dq.groupby(['project','month' if 'month' in dq else 'date']).size()
dq['month']=dq.date.dt.to_period('M').dt.to_timestamp()
dgg=dq[dq.good].groupby(['project','month']).dg_kwh.sum().rename('dg_good'); dga=dq.groupby(['project','month']).dg_kwh.sum().rename('dg_portal')
X=Mf.join(Mk).join(Mx).join(ck).join(dgg).join(dga).join(T.set_index(['project','month'])[['fuel','dg','load','solar','kwp','kva','cfg']],how='inner')
X['good_share']=X.dg_good/X.dg_portal
X['scale']=X.dg/X.ck_good
feat=[c for c in X.columns if '|' in c]
X[feat]=X[feat].mul(X.scale,axis=0)
X['country']=X.index.get_level_values(0).str[:3]
n0=len(X)
X=X[(X.fuel>0)&(X.good_share>=0.5)&X.scale.between(0.8,1.6)]
X.to_csv(out)
print(f'{len(X)} site-months of {n0} with report fuel; {X.index.get_level_values(0).nunique()} sites; good-day share median {X.good_share.median():.2f}; scale median {X.scale.median():.3f}')
print(X.groupby(level=0).size().to_string())
