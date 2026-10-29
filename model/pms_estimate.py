"""Estimate PMS start/stop loading thresholds per site and quarter from 1-minute transitions.
usage: pms_estimate.py raw_dir outdir"""
import sys, os, glob, re, pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from names import PORTAL_RENAME
raw,out=sys.argv[1:3]; os.makedirs(out,exist_ok=True)
jobs=pd.read_csv(os.path.join(raw,'..','jobs.tsv'),sep='\t',header=None,names=['key','project','f','t']).set_index('key')
ev=[]
for f in sorted(glob.glob(os.path.join(raw,'*.csv'))):
    key=os.path.basename(f)[:-4]; d=pd.read_csv(f)
    if d.empty: continue
    proj=PORTAL_RENAME.get(jobs.loc[key,'project'],jobs.loc[key,'project'])
    d['t']=pd.to_datetime(d.t,unit='ms')+pd.Timedelta(hours=4)
    d=d.sort_values('t').reset_index(drop=True)
    d['ok']=(d.n_rep==d.rep1)
    d['dn']=d.n_on-d.n1
    nxt=d.shift(-1)
    quick=(nxt.t-d.t<=pd.Timedelta(minutes=10))&(nxt.dn==-d.dn)
    swap=quick&(nxt.on_list.fillna('')!=d.l1.fillna(''))      # different unit left -> changeover, not load driven
    flap=quick&~swap
    d['swap']=swap|swap.shift(1,fill_value=False)
    d['flap']=flap
    d['post']=d.kw_after/d.rated_on.replace(0,np.nan)
    d['project']=proj
    ev.append(d)
E=pd.concat(ev,ignore_index=True)
E['q']=E.t.dt.to_period('Q').astype(str)
E['kind']=np.select([(E.dn==1)&(E.n1>=1),(E.dn==-1)&(E.n_on>=1)],['start','stop'],'other')
V=E[E.ok&~E.swap&(E.kind!='other')]
V.to_csv(os.path.join(out,'pms_events.csv.gz'),index=False,compression='gzip')
days=E.groupby(['project','q']).t.agg(lambda s:s.dt.normalize().nunique()).rename('days')
def agg(g):
    s=g[g.kind=='start']; p=g[g.kind=='stop']
    return pd.Series({'starts':len(s),'start_pct_p50':s.ld_max5.median(),'start_pct_p25':s.ld_max5.quantile(.25),'start_pct_p75':s.ld_max5.quantile(.75),
        'stops':len(p),'stop_pct_p50':p.ld_avg5.median(),'stop_pct_p25':p.ld_avg5.quantile(.25),'stop_pct_p75':p.ld_avg5.quantile(.75),
        'after_stop_loading_p50':p.post.median(),'flapping_starts':int(s.flap.sum()),
        'changeovers':0})
Q=V.groupby(['project','q']).apply(agg).join(days)
Q['changeovers']=E[E.swap&(E.dn==1)].groupby(['project','q']).size().reindex(Q.index).fillna(0)
Q['flaps_per_day']=Q.flapping_starts/Q.days
Q.reset_index().to_csv(os.path.join(out,'pms_quarterly.csv'),index=False)
S=V.groupby('project').apply(agg)
S.reset_index().to_csv(os.path.join(out,'pms_site.csv'),index=False)
pd.set_option('display.width',250)
print(S[['starts','start_pct_p50','start_pct_p25','start_pct_p75','stops','stop_pct_p50','after_stop_loading_p50','flapping_starts']].round(2).to_string())