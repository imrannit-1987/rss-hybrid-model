"""Workbook for fuel model v4. usage (from repo root): python3 model/fit_v4_workbook.py outputs/RSS_fuel_curves_v4.xlsx"""
import sys, pandas as pd, numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter as L
F='Arial'; H=Font(name=F,bold=True,color='FFFFFF'); HF=PatternFill('solid',fgColor='1F4E5F'); B=Font(name=F)
def sheet(wb,name,df,fmts,widths,note):
    ws=wb.create_sheet(name); ws['A1']=note; ws['A1'].font=Font(name=F,italic=True,size=10); r0=3
    for j,c in enumerate(df.columns,1):
        x=ws.cell(row=r0,column=j,value=c); x.font=H; x.fill=HF; x.alignment=Alignment(wrap_text=True,vertical='center')
    for i,row in enumerate(df.itertuples(index=False),r0+1):
        for j,v in enumerate(row,1):
            if isinstance(v,(float,np.floating)) and np.isnan(v): v=None
            c=ws.cell(row=i,column=j,value=v.item() if isinstance(v,np.generic) else v); c.font=B
            if df.columns[j-1] in fmts: c.number_format=fmts[df.columns[j-1]]
    for j,wd in enumerate(widths,1): ws.column_dimensions[L(j)].width=wd
    ws.freeze_panes=ws.cell(row=r0+1,column=2); return ws
wb=Workbook(); wb.remove(wb.active)
R=pd.read_csv('outputs/fit_v4/model_comparison_v4.csv').rename(columns={'model':'Model / test','n':'Site-months','med':'Month error (median)','p90':'Month error (90th pct)','within10':'Months within ±10%','bias':'Bias (median)','site_med':'Site total error (median)','site_p90':'Site total error (90th pct)','site_max':'Worst site','fleet':'Fleet total error'})
R=R[['Model / test','Site-months','Month error (median)','Month error (90th pct)','Months within ±10%','Bias (median)','Site total error (median)','Site total error (90th pct)','Worst site','Fleet total error']]
sim=[]
for v,f in (('v3 full simulation (solar > dispatch > curves)','outputs/sim/sim_all_monthly.csv'),('v4 full simulation (solar > dispatch > curves)','outputs/sim/sim_all_monthly_v4.csv')):
    d=pd.read_csv(f); d=d[d.flag.isna()|d.flag.isin(['ok',''])]; e=d.model_err; g=d.groupby('project'); st=g.model_fuel.sum()/g.act_fuel.sum()-1
    sim.append([v,len(d),e.abs().median(),e.abs().quantile(.9),(e.abs()<.1).mean(),e.median(),st.abs().median(),st.abs().quantile(.9),st.abs().max(),d.model_fuel.sum()/d.act_fuel.sum()-1])
R=pd.concat([R,pd.DataFrame(sim,columns=R.columns)],ignore_index=True)
ws=sheet(wb,'Summary',R,{c:'0.0%' for c in R.columns[2:]},[52,11,13,13,13,11,14,14,11,12],'Fuel model v4 vs v3, scored against MONTHLY report fuel (the final figure). Each site is predicted from curves fitted without it. "v3" rows = v3 method re-run on the same corrected data; the v3 full simulation row is the original v3.')
n=len(R)+5
for t in ['Training data: 2025 and 2026. Weekly-report rows with fuel scaled so each site-month matches its monthly report (1,156 weeks), plus the monthly rows. Same curve form as v3.',
          'Generator kWh corrected for locally-fed solar at Target, Galfar and Fame Fardani (see "Local solar" tab). AYTB Jubail left uncorrected: its meter gap does not vary with solar.',
          'Tested and rejected (no gain out of sample): cubic loading term, low-load hours, start counts, seasonal term, per-family loading term, pooling families toward a fleet curve.',
          'KENT is the only Scania DC13 site, so leaving it out leaves nothing to learn that engine from. Use the "excl. KENT" rows as the new-site benchmark.',
          'Time split: both versions over-predict 2026 by 2-4% when trained only on data to Dec 2025, i.e. the fleet ran slightly more efficiently in 2026.']:
    ws.cell(row=n,column=1,value=t).font=B; n+=1
C=pd.read_csv('outputs/fit_v4/fuel_curves_v4.csv'); C3=pd.read_csv('outputs/fit_v3/fuel_curves_v3.csv')
C=C.merge(C3[['family','country','L/kWh@35%']].rename(columns={'L/kWh@35%':'v3 L/kWh@35%'}),on=['family','country'],how='left'); C['change vs v3']=C['L/kWh@35%']/C['v3 L/kWh@35%']-1
C=C[['family','country','sites','rows','share_of_fleet_kwh','L/kWh@25%','L/kWh@35%','@35% p10','@35% p90','L/kWh@50%','L/kWh@75%','v3 L/kWh@35%','change vs v3','a_fixed','b_marginal','q_quadratic']].sort_values(['country','L/kWh@35%'])
C=C.rename(columns={'family':'Engine family','country':'Country','sites':'Sites','rows':'Data rows','share_of_fleet_kwh':'Share of fleet kWh','@35% p10':'@35% low (p10)','@35% p90':'@35% high (p90)','a_fixed':'a (L per rated kWh-hour)','b_marginal':'b (L/kWh)','q_quadratic':'q (L/kWh per unit loading)'})
f3={c:'0.000' for c in C.columns if 'L/kWh' in c or '@35' in c or c.startswith('b ') or c.startswith('q ')}; f3.update({'Share of fleet kWh':'0.0%','change vs v3':'+0.0%;-0.0%','a (L per rated kWh-hour)':'0.0000'})
sheet(wb,'Fuel curves v4',C,f3,[28,9,7,10,11,10,10,10,10,10,10,11,11,13,10,13],'L per generator kWh (site-meter basis, corrected for local solar where known) at a given unit loading = a/loading + b + q*loading. Country multiplier applied. Low/high = 10th-90th percentile from resampling sites.')
S=pd.read_csv('outputs/fit_v4/loso_sites_v4.csv').rename(columns={'project':'Site','months':'Months','act_L':'Monthly-report fuel (L)','pred_L':'Model fuel (L)','err_v4':'v4 error','err_v3':'v3 method error'})
sheet(wb,'Site check',S,{'Monthly-report fuel (L)':'#,##0','Model fuel (L)':'#,##0','v4 error':'+0.0%;-0.0%','v3 method error':'+0.0%;-0.0%'},[32,8,17,15,10,12],'Each site predicted from curves fitted without it, summed over all its months, against monthly-report fuel.')
K=pd.read_csv('outputs/local_solar_share.csv').rename(columns={'project':'Site','local_solar_share':'Estimated share of solar fed in locally'})
K['Status']='applied'; K=pd.concat([K,pd.DataFrame([['KSA - AYTB Jubail - C',np.nan,'not applied: counters sit ~5% above load-minus-solar regardless of sun (fixed meter offset)']],columns=K.columns)],ignore_index=True)
sheet(wb,'Local solar',K,{'Estimated share of solar fed in locally':'0%'},[30,22,90],'Where solar feeds in at a local board the load meter does not see it, so "load - solar" understates the generators. Corrected generator kWh = load - solar + share x solar. Share estimated from the generators\' own counters.')
wb.save(sys.argv[1])
