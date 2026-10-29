"""Portal daily table -> site_day.csv (load, solar, dg, fuel, eff per project-day). usage: build_daily.py daily_all.csv site_day.csv"""
import sys, os, pandas as pd, numpy as np
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); from names import PORTAL_RENAME, SUM_SECTIONS
d=pd.read_csv(sys.argv[1],low_memory=False)
d['date']=pd.to_datetime(d.time,unit='ms').dt.normalize()
d['project']=d.ProjectName.map(lambda p:PORTAL_RENAME.get(p,p))
V=['Daily_ActiveEnergySumLoadMeter','Daily_ActiveEnergySumSolarMeter','Daily_ActiveEnergySumDGMeter','Daily_GeneratorKWhours','Daily_FuelConsumption','FuelEfficiency']
site=d[d.SiteName.isna()]
ctrl=d[d.SiteName.notna()&~d.SiteName.str.match(r'^(GS|CH)')]
def agg_of(x): return x.groupby(['project','ProjectName','date']).agg(load_kwh=('Daily_ActiveEnergySumLoadMeter','sum'),solar_kwh=('Daily_ActiveEnergySumSolarMeter','sum'),
    dg_kwh=('Daily_ActiveEnergySumDGMeter','sum'),gen_kwh=('Daily_GeneratorKWhours','sum'),fuel_l=('Daily_FuelConsumption','sum'),eff=('FuelEfficiency','max'),
    n_load=('Daily_ActiveEnergySumLoadMeter','count'),n_dg=('Daily_ActiveEnergySumDGMeter','count'),n_solar=('Daily_ActiveEnergySumSolarMeter','count'),n_gen=('Daily_GeneratorKWhours','count'),n_fuel=('Daily_FuelConsumption','count'))
A=agg_of(site); B=agg_of(ctrl)
for c,n in [('load_kwh','n_load'),('dg_kwh','n_dg'),('solar_kwh','n_solar'),('gen_kwh','n_gen'),('fuel_l','n_fuel')]:
    A.loc[A[n]==0,c]=np.nan; B.loc[B[n]==0,c]=np.nan
agg=A.combine_first(B).reset_index()   # site-level first, controller sums where missing
# combine renamed/sectioned portal projects
def comb(g):
    p=g.name
    f='sum' if p in SUM_SECTIONS else 'max'
    return g.groupby('date')[['load_kwh','solar_kwh','dg_kwh','gen_kwh','fuel_l','eff']].agg(f)
out=agg.groupby('project').apply(comb).reset_index()
# impossible values: negative or > 4x the 60-day rolling median
for c in ['load_kwh','solar_kwh','dg_kwh','gen_kwh','fuel_l']:
    out.loc[out[c]<0,c]=np.nan
    med=out.groupby('project')[c].transform(lambda s:s.rolling(60,min_periods=10,center=True).median())
    out.loc[(out[c]>4*med)&(med>0),c]=np.nan
out.to_csv(sys.argv[2],index=False); print(len(out),'site-days',out.project.nunique(),'projects')
