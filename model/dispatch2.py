"""Dispatch v2: PMS start/stop hysteresis with a priority order.
State: k units online (in priority order among available). Each hour:
  while load/rated_k > START and units left: add next unit
  while k>1 and load/rated_k < STOP: remove last unit
Fuel per hour from curves. Compare with fuel from actual generator behaviour (dispatch-only error).
usage: dispatch2.py gen_hourly.csv.gz coef.json pms/pms_quarterly.csv outdir"""
import sys, json, numpy as np, pandas as pd, os
gh,cf,pq,out=sys.argv[1:5]; os.makedirs(out,exist_ok=True)
C=json.load(open(cf))
CL=[(0,150,'≤125 kVA'),(150,235,'200–220 kVA'),(235,275,'250 kVA'),(275,325,'300 kVA'),(325,400,'350 kVA'),(400,650,'500 kVA'),(650,900,'800 kVA'),(900,1400,'1000–1250 kVA')]
cls=lambda k:next(n for lo,hi,n in CL if lo<=k<hi); A=lambda k:C['rated_h|'+cls(k)]; B=lambda k:C['kwh|'+cls(k)]
D=pd.read_csv(gh,parse_dates=['t'])
D['fa']=[A(k)*k*0.8*r+B(k)*e for k,r,e in zip(D.kva,D.run,D.kwh)]
# priority: units ordered by share of hours running within the month (most-used first)
D['month']=D.t.dt.to_period('M').dt.to_timestamp()
use=D.groupby(['project','month','gen']).run.mean().rename('use').reset_index()
D=D.merge(use,on=['project','month','gen'])
P=pd.read_csv(pq)
def sim(g,start,stop):
    fuel=[];k=1;prev=None
    for t,h in g.groupby('t',sort=True):
        h=h.sort_values(['use','kva'],ascending=False)
        units=list(h.kva); load=h.kwh.sum()
        if load<=0: fuel.append((t,0.0,0)); continue
        k=min(max(k,1),len(units))
        while k<len(units) and load/sum(u*0.8 for u in units[:k])>start: k+=1
        while k>1 and load/sum(u*0.8 for u in units[:k])<stop and load/sum(u*0.8 for u in units[:k-1])<=start: k-=1
        on=units[:k]; rat=sum(u*0.8 for u in on); gen=load
        fuel.append((t,sum(A(u)*u*0.8+B(u)*gen*(u*0.8)/rat for u in on),k))
    return pd.DataFrame(fuel,columns=['t','fuel','k'])
rows=[]
for p,g in D.groupby('project'):
    pp=P[P.project==p]
    if pp.empty: continue
    g=g.copy(); g['q']=g.t.dt.to_period('Q').astype(str)
    site_start=np.nanmedian(pp.start_pct_p50); site_stop=np.nanmedian(pp.stop_pct_p50)
    for q,gq in g.groupby('q'):
        r=pp[pp.q==q]
        st=r.start_pct_p50.iloc[0] if len(r) and r.starts.iloc[0]>=10 else site_start
        sp=r.stop_pct_p50.iloc[0] if len(r) and r.stops.iloc[0]>=10 else site_stop
        if np.isnan(st) or np.isnan(sp): continue
        s=sim(gq,st,sp); s['month']=s.t.dt.to_period('M').dt.to_timestamp()
        m=s.groupby('month').fuel.sum().rename('fuel_sim').to_frame()
        m['fuel_act']=gq.groupby('month').fa.sum(); m['start']=st; m['stop']=sp; m['project']=p
        rows.append(m.reset_index())
M=pd.concat(rows); M.to_csv(f'{out}/dispatch2_month.csv',index=False)
e=M.fuel_sim/M.fuel_act-1; s=M.groupby('project').apply(lambda g:g.fuel_sim.sum()/g.fuel_act.sum()-1)
print(f'PMS start/stop model: n={len(M)} bias {e.median():+.1%} |err| med {e.abs().median():.1%} p90 {e.abs().quantile(.9):.1%} | site total |err| med {s.abs().median():.1%} worst {s.abs().max():.1%}')
print(s.round(3).sort_values().to_string())