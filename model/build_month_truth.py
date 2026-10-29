"""Monthly report actuals (mapped to portal names, JCD sheets summed) + portal monthly DG for a cross-check. usage: build_month_truth.py monthly_all.csv site_day.csv out.csv"""
import sys, os, pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); from names import MONTHLY
M=pd.read_csv(sys.argv[1],parse_dates=['month']); M['project']=M.sheet.map(MONTHLY); M=M[M.project.notna()]
T=M.groupby(['project','month']).agg(fuel=('act_fuel','sum'),dg=('act_dg','sum'),load=('act_load','sum'),solar=('act_solar','sum'),kwp=('act_kwp','sum'),kva=('act_kva','sum'),n=('act_fuel','count'),cfg=('dg_config','first')).reset_index()
T=T[(T.n>0)&(T.fuel>0)&(T.dg>0)]
sd=pd.read_csv(sys.argv[2],parse_dates=['date']); sd['month']=sd.date.dt.to_period('M').dt.to_timestamp()
pm=sd.groupby(['project','month']).agg(dg_portal=('dg_kwh','sum'),days=('dg_kwh','count')).reset_index()
T=T.merge(pm,on=['project','month'],how='left'); T.to_csv(sys.argv[3],index=False)
r=T.dg/T.dg_portal; print(len(T),'site-months; report/portal DG within 10%:',round(r.between(.9,1.1).mean(),2))
