"""Hourly per-generator kWh and run fraction from cumulative counters -> parquet-like CSV (gzip).
usage: gen_hourly.py <hourly_dir> <out.csv.gz>"""
import sys, os, glob, re, pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from names import PORTAL_RENAME
hdir,out=sys.argv[1:3]; res=[]
for f in sorted(glob.glob(os.path.join(hdir,'h_*.csv'))):
    h=pd.read_csv(f,low_memory=False,usecols=lambda c:c in('time','ProjectName','SiteName','GeneratorKWhours','Engineruntime'))
    h=h[h.SiteName.fillna('').str.match(r'^(GS|CH)')]
    if h.empty: continue
    h['t']=pd.to_datetime(h.time,unit='ms',utc=True).dt.tz_convert('Asia/Dubai').dt.tz_localize(None)
    for (proj,gen),g in h.groupby(['ProjectName','SiteName']):
        k=re.findall(r'-(\d+)-',gen)
        if not k: continue
        kva=int(k[0]); g=g.drop_duplicates('t').set_index('t').sort_index()
        dt=g.index.to_series().diff().dt.total_seconds()/3600
        kwh=g.GeneratorKWhours.diff(); run=g.Engineruntime.diff()
        good=(dt>0.8)&(dt<1.25)&(kwh>=0)&(kwh<=kva*0.8*1.15*dt)&(run>=0)&(run<=1.05*dt)
        d=pd.DataFrame({'kwh':(kwh/dt).where(good),'run':(run/dt).where(good)})   # per-hour equivalents
        d.index=d.index.floor('h'); d=d[~d.index.duplicated()]
        d['project']=PORTAL_RENAME.get(proj,proj); d['gen']=gen; d['kva']=kva
        res.append(d.dropna().reset_index())
D=pd.concat(res,ignore_index=True)
D.to_csv(out,index=False,compression='gzip')
print(f"{len(D):,} generator-hours | {D.gen.nunique()} gens | {D.project.nunique()} sites | running hours {int((D.run>0.5).sum()):,}")