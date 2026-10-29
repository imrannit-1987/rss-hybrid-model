"""Month-by-month simulation for every site: hourly generator demand (unit counters, scaled to the month-end site-meter DG kWh)
-> PMS start/stop dispatch (site/quarter settings) -> engine-family fuel curves fitted WITHOUT that site -> month fuel & L/kWh vs report.
usage: sim_all.py pms_quarterly.csv out.csv"""
import sys, json, numpy as np, pandas as pd
pq,out=sys.argv[1:3]
LOSO=json.load(open('fit_v3/loso_coefs_v3.json')); FULL=json.load(open('fit_v3/coef_v3.json'))
GF=pd.read_csv('gen_families.csv').drop_duplicates('dev_clean').set_index('dev_clean')
KV=[(0,150,'≤125 kVA'),(150,235,'200–220 kVA'),(235,275,'250 kVA'),(275,325,'300 kVA'),(325,400,'350 kVA'),(400,650,'500 kVA'),(650,900,'800 kVA'),(900,1400,'1000–1250 kVA')]
def fam_of(g,k):
    f=GF.family.get(g); return f if isinstance(f,str) else 'unlisted '+next(n for lo,hi,n in KV if lo<=k<hi)
D=pd.read_csv('gen_hourly.csv.gz',parse_dates=['t']); D['month']=D.t.dt.to_period('M').dt.to_timestamp(); D['fam']=[fam_of(g,k) for g,k in zip(D.gen,D.kva)]
T=pd.read_csv('month_truth.csv',parse_dates=['month']); T=T[(T.fuel>0)&(T.dg>0)]
P=pd.read_csv(pq) if pq!='none' else pd.DataFrame(columns=['project','q','starts','start_pct_p50','stops','stop_pct_p50'])
DEF={'C':(0.65,0.37),'I':(0.50,0.30),'S':(0.50,0.30)}
def settings(p,month):
    q=f'{month.year}Q{(month.month-1)//3+1}'; pp=P[P.project==p]
    st=sp=None
    r=pp[(pp.q==q)&(pp.starts>=15)]
    if len(r): st=float(r.start_pct_p50.iloc[0])
    r=pp[(pp.q==q)&(pp.stops>=15)]
    if len(r): sp=float(r.stop_pct_p50.iloc[0])
    if st is None and len(pp[pp.starts>=15]): st=float(pp[pp.starts>=15].start_pct_p50.median())
    if sp is None and len(pp[pp.stops>=15]): sp=float(pp[pp.stops>=15].stop_pct_p50.median())
    d=DEF.get(p[-1],(0.6,0.35)); src='quarter' if len(pp[(pp.q==q)&(pp.starts>=15)]) else ('site' if st is not None else 'default')
    st=st if st is not None else d[0]; sp=sp if sp is not None else d[1]
    st=max(st,0.45); sp=min(sp,st-0.10)          # estimates below 45% are manual starts, not a PMS setting
    return st,sp,src
def mk_fuel(C,p):
    fold=C['_fold']; q=C['kwh_l|*']; m=C['country|'+p[:3]]
    def f(fam,kva,run,kwh):
        fam=fold.get(fam,fam); a=C[f'rated_h|{fam}']; b=C[f'kwh|{fam}']; r=kva*0.8; l=kwh/(r*run) if run>0 else 0
        return m*(a*r*run+b*kwh+q*kwh*l)
    return f
# typical site-meter ratio (report DG / unit counters) from full months
full=[]
for (p,month),g in D.groupby(['project','month']):
    t=T[(T.project==p)&(T.month==month)]
    if len(t) and g.t.dt.normalize().nunique()>=25 and g.kwh.sum()>0: full.append((p,float(t.dg.iloc[0])/g.kwh.sum()))
RATIO=pd.DataFrame(full,columns=['p','r']).groupby('p').r.median().clip(0.8,1.25).to_dict()
rows=[]
for (p,month),g in D.groupby(['project','month']):
    t=T[(T.project==p)&(T.month==month)]
    if t.empty: continue
    t=t.iloc[0]; C=LOSO.get(p,FULL); uf=mk_fuel(C,p); START,STOP,src=settings(p,month)
    units=g.groupby('gen').agg(kva=('kva','first'),fam=('fam','first'),use=('run','sum')).sort_values('use',ascending=False)
    fleet=list(units.index); rat=lambda n:sum(units.kva[x]*0.8 for x in fleet[:n])
    dem=g.groupby('t').kwh.sum(); hrs=dem.index
    if dem.sum()<=0: continue
    ndays=g.t.dt.normalize().nunique()
    ratio=t.dg/dem.sum() if ndays>=25 else RATIO.get(p,1.0)     # site-meter ratio; for part-months use the site's typical ratio
    ratio=float(np.clip(ratio,0.8,1.25)); sc=ratio; cover=dem.sum()*sc/t.dg   # share of the month's DG kWh covered by hourly data
    k=1; fsim=0.0; kon=[]; ld=[]
    for d in dem.values*sc:
        if d<=0: kon.append(0); continue
        k=min(max(k,1),len(fleet))
        while k<len(fleet) and d/rat(k)>START: k+=1
        while k>1 and d/rat(k)<STOP and d/rat(k-1)<=START: k-=1
        r=rat(k); fsim+=sum(uf(units.fam[u],units.kva[u],1.0,d*units.kva[u]*0.8/r) for u in fleet[:k]); kon.append(k); ld.append(d/r)
    fsim=fsim/cover; fact=sum(uf(f,kk,rr,e*sc) for f,kk,rr,e in zip(g.fam,g.kva,g.run,g.kwh))/cover
    rows.append(dict(project=p,month=month,country=p[:3],type=p[-1],days_with_data=g.t.dt.normalize().nunique(),hours=len(hrs),
        act_fuel=t.fuel,dg=t.dg,dg_portal=t.dg_portal,load=t.load,solar=t.solar,act_LkWh=t.fuel/t.dg,meter_ratio=ratio,hourly_cover=cover,
        model_fuel=fsim,model_LkWh=fsim/t.dg,model_err=fsim/t.fuel-1,
        curves_on_actual_fuel=fact,curves_on_actual_LkWh=fact/t.dg,
        pms_start=START,pms_stop=STOP,pms_source=src,fleet=' + '.join(f'{units.kva[u]}' for u in fleet),families=', '.join(sorted(set(units.fam))),
        sim_mean_loading=float(np.mean(ld)) if ld else np.nan,solar_share=t.solar/t.load if t.load else np.nan))
R=pd.DataFrame(rows)
R['flag']=np.where(R.days_with_data<20,'part month (<20 days of hourly data)',np.where((R.dg/R.dg_portal).sub(1).abs()>0.2,'report DG differs >20% from portal','ok'))
R.to_csv(out,index=False); print(R.flag.value_counts().to_dict()); R=R[R.flag=='ok']
e=R.model_err; s=R.groupby('project').apply(lambda x:x.model_fuel.sum()/x.act_fuel.sum()-1)
print(f'{len(R)} site-months, {R.project.nunique()} sites | monthly |err| median {e.abs().median():.1%} p90 {e.abs().quantile(.9):.1%} bias {e.median():+.1%} | site total |err| median {s.abs().median():.1%} p90 {s.abs().quantile(.9):.1%}')
print(R.pms_source.value_counts().to_dict())
