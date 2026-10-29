"""One-week site simulation: hourly load (+measured or simulated solar) -> PMS dispatch -> family fuel curves -> L/kWh.
usage: sim_week.py <project> <start YYYY-MM-DD> <days> <start_pct> <stop_pct> <out.json> <hourly_csv> <weekly_sheet> [solar_on_load_side 0/1]"""
import sys, json, numpy as np, pandas as pd, pvlib
proj,start,days,START,STOP,out,HF,SHEET=sys.argv[1],pd.Timestamp(sys.argv[2]),int(sys.argv[3]),float(sys.argv[4]),float(sys.argv[5]),sys.argv[6],sys.argv[7],sys.argv[8]
SOLAR_SIDE=len(sys.argv)>9 and sys.argv[9]=='1'
end=start+pd.Timedelta(days=days)
C=json.load(open('fit_v3/loso_coefs_v3.json')).get(proj) or json.load(open('fit_v3/coef_v3.json'))
GF=pd.read_csv('gen_families.csv').drop_duplicates('dev_clean').set_index('dev_clean')
D=pd.read_csv('gen_hourly.csv.gz',parse_dates=['t']); D=D[(D.project==proj)&(D.t>=start)&(D.t<end)].copy()
sd=pd.read_csv('site_day.csv',parse_dates=['date']); sd=sd[(sd.project==proj)&(sd.date>=start)&(sd.date<end)].set_index('date')
W=pd.read_csv('/tmp/claude-0/-home-claude/18b46c3b-d06a-56f6-b365-028dae5fb897/scratchpad/xl/weekly_daily_all.csv',parse_dates=['date'])
wk=W[(W.sheet==SHEET)&(W.date>=start)&(W.date<end)]
# hourly load from controller load meters (all five counters), solar = load - generator output (unit counters scaled to the site DG meter)
h=pd.read_csv(HF,low_memory=False)
h['t']=pd.to_datetime(h.time,unit='ms',utc=True).dt.tz_convert('Asia/Dubai').dt.tz_localize(None); h=h[(h.t>=start-pd.Timedelta(hours=2))&(h.t<end+pd.Timedelta(hours=2))]
parts=[]
for dev,g in h[h.SiteName.fillna('').str.startswith('CP')].groupby('SiteName'):
    g=g.set_index('t').sort_index()
    for c in [x for x in g.columns if (x.startswith('ActiveEnergySumLoadMeter') or (SOLAR_SIDE and x.startswith('ActiveEnergySumSolarMeter'))) and g[x].notna().sum()>24]:
        s=g[c].dropna(); s=s[~s.index.duplicated()]; d=s.diff().where(lambda v:(v>=0)&(v<5000)); d.index=d.index.floor('h'); parts.append(d[~d.index.duplicated()])
load=pd.concat(parts,axis=1).sum(axis=1,min_count=1)
hours=pd.date_range(start,end-pd.Timedelta(hours=1),freq='h'); load=load.reindex(hours).interpolate().bfill().ffill()
D['date']=D.t.dt.normalize()
MT=pd.read_csv('month_truth.csv',parse_dates=['month']); mt=MT[(MT.project==proj)&(MT.month>=start.to_period('M').to_timestamp())&(MT.month<end)]
if len(mt)==1 and days>=28:   # site-meter basis: scale unit output to the month-end report's DG kWh (the kWh the efficiency is quoted on)
    sc=float(mt.dg.iloc[0])/D.kwh.sum(); D['kwh_s']=D.kwh*sc; BASIS=f'site meter (report) x{sc:.3f}'
else:
    scd=(sd.dg_kwh/D.groupby('date').kwh.sum()).clip(0.8,1.2); D['kwh_s']=D.kwh*D.date.map(scd); BASIS='site meter (portal daily)'
print('kWh basis:',BASIS)
gen=D.groupby('t').kwh_s.sum().reindex(hours).fillna(0)
solar_meas=(load-gen).clip(lower=0)
def cls(k,p): 
    f=GF.family.get(k) if False else None
def fam_of(gen_id,kva):
    f=GF.family.get(gen_id); 
    if isinstance(f,str): return f
    KV=[(0,150,'≤125 kVA'),(150,235,'200–220 kVA'),(235,275,'250 kVA'),(275,325,'300 kVA'),(325,400,'350 kVA'),(400,650,'500 kVA'),(650,900,'800 kVA'),(900,1400,'1000–1250 kVA')]
    return 'unlisted '+next(n for lo,hi,n in KV if lo<=kva<hi)
fold=C['_fold']; q=C['kwh_l|*']; m=C['country|'+proj[:3]]
def coefs(f):
    f=fold.get(f,f); return C[f'rated_h|{f}'],C[f'kwh|{f}']
def unit_fuel(f,kva,run,kwh):
    a,b=coefs(f); r=kva*0.8; l=kwh/(r*run) if run>0 else 0; return m*(a*r*run+b*kwh+q*kwh*l)
units=D.groupby('gen').agg(kva=('kva','first'),use=('run','sum')).sort_values('use',ascending=False); units['fam']=[fam_of(g,k) for g,k in zip(units.index,units.kva)]
fleet=list(units.index)
# simulated solar: pvlib clear-sky, flat array, UAE default location; defaults site_factor .9, floor .2, maxpen .6
loc=pvlib.location.Location(25.1,55.2,tz='Etc/GMT-4',altitude=50); tmid=pd.DatetimeIndex(hours).tz_localize('Etc/GMT-4')-pd.Timedelta(minutes=30)
sp=loc.get_solarposition(tmid); cs=loc.get_clearsky(tmid,model='ineichen',solar_position=sp)
poa=pvlib.irradiance.get_total_irradiance(0,180,sp.apparent_zenith,sp.azimuth,cs.dni,cs.ghi,cs.dhi,albedo=0.25)['poa_global'].fillna(0).values
ta=np.array([20,21,24,29,33,35,37,37,34,31,26,22])[hours.month-1]+3; tc=ta+poa/800*25; cs0=poa/1000*(1-0.004*(tc-25))
KWP=float(sd.kwp.iloc[0]) if 'kwp' in sd and sd.kwp.notna().any() else 1896.0
pot=cs0*KWP*0.9
def dispatch(demand_series,solar_pot=None,floor=0.2,maxpen=0.6):
    rows=[]; k=1
    for t in hours:
        L=float(load[t])
        if solar_pot is not None:
            s=min(float(solar_pot[t]),maxpen*L); dem=max(L-s,0)
        else: dem=float(demand_series[t])
        k=min(max(k,1),len(fleet)); rat=lambda n:sum(units.kva[x]*0.8 for x in fleet[:n])
        while k<len(fleet) and dem/rat(k)>START: k+=1
        while k>1 and dem/rat(k)<STOP and dem/rat(k-1)<=START: k-=1
        on=fleet[:k]; r=rat(k)
        if solar_pot is not None: dem=max(dem,floor*r); dem=min(dem,L)   # generators hold their floor; solar fills the rest
        fuel=sum(unit_fuel(units.fam[u],units.kva[u],1.0,dem*units.kva[u]*0.8/r) for u in on)
        rows.append(dict(t=t.strftime('%Y-%m-%d %H:%M'),load=round(L,1),solar=round(L-dem,1),gen=round(dem,1),on=on,loading=round(dem/r,3),fuel=round(fuel,1)))
    return rows
A=dispatch(gen)                       # measured load & measured solar
B=dispatch(None,solar_pot=pd.Series(pot,index=hours))   # measured load, simulated solar
# reference: curves on actual unit running
D['fa']=[unit_fuel(fam_of(g,k),k,r,e) for g,k,r,e in zip(D.gen,D.kva,D.run,D.kwh_s)]
act=D.groupby('t').agg(fuel=('fa','sum')).reindex(hours).fillna(0)
acts={t.strftime('%Y-%m-%d %H:%M'):[{'g':g,'kw':round(e,1),'run':round(r,2)} for g,e,r in zip(x.gen,x.kwh_s,x.run)] for t,x in D.groupby('t')}
res=dict(project=proj,start=str(start.date()),days=days,start_pct=START,stop_pct=STOP,kwp=KWP,fleet=[dict(g=g,kva=int(units.kva[g]),family=units.fam[g]) for g in fleet],
  coef={f:dict(a=coefs(f)[0],b=coefs(f)[1]) for f in set(units.fam)},q=q,country=m,
  A=A,B=B,act_fuel=act.fuel.round(1).tolist(),act_units=acts,
  weekly=dict(fuel=float(wk.fuel.sum()),dg=float(wk.dg.sum()),load=float(wk.load.sum()),solar=float(wk.solar.sum()),days=int(wk.fuel.notna().sum())),
  portal=dict(dg=float(sd.dg_kwh.sum()),load=float(sd.load_kwh.sum()),solar=float(sd.solar_kwh.sum())))
json.dump(res,open(out,'w'))
fa=sum(A[i]['fuel'] for i in range(len(A))); fb=sum(B[i]['fuel'] for i in range(len(B))); ga=sum(A[i]['gen'] for i in range(len(A))); gb=sum(B[i]['gen'] for i in range(len(B)))
print(f"week {start.date()} +{days}d | load {load.sum():,.0f} kWh | measured solar {solar_meas.sum():,.0f} | simulated solar {sum(B[i]['solar'] for i in range(len(B))):,.0f}")
print(f"weekly report: fuel {res['weekly']['fuel']:,.0f} L / DG {res['weekly']['dg']:,.0f} kWh = {res['weekly']['fuel']/res['weekly']['dg']:.3f} L/kWh")
print(f"A measured load+solar, PMS dispatch: fuel {fa:,.0f} L / gen {ga:,.0f} = {fa/ga:.3f} L/kWh")
print(f"B measured load, simulated solar:    fuel {fb:,.0f} L / gen {gb:,.0f} = {fb/gb:.3f} L/kWh")
print(f"curves on actual running:            fuel {act.fuel.sum():,.0f} L / gen {gen.sum():,.0f} = {act.fuel.sum()/gen.sum():.3f} L/kWh")
import collections; print('units on, hours (A):',collections.Counter(len(r['on']) for r in A), ' actual:',collections.Counter(sum(1 for u in v if u['run']>0.5) for v in acts.values()))
