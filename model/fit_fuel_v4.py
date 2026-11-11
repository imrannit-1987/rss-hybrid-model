"""Fuel-curve fit v4: same curve form as v3. Truth = MONTHLY reports (final call). Training rows = weekly rows whose fuel has been
reconciled to the monthly report for that site-month, plus the monthly rows themselves. Scored leave-one-site-out on monthly rows.
usage: fit_fuel_v4.py fuel_dataset_v4_week_rec.csv fuel_dataset_v4_month.csv outdir"""
import sys, os, json, numpy as np, pandas as pd, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0,os.path.dirname(__file__)); from fuelfit4 import Model, loso, score, families
Wr=pd.read_csv(sys.argv[1],parse_dates=['week']).set_index(['project','week']).rename_axis(['project','t']); M=pd.read_csv(sys.argv[2],parse_dates=['month']).set_index(['project','month']).rename_axis(['project','t']); out=sys.argv[3]; os.makedirs(out,exist_ok=True)
W=pd.concat([Wr,M]).fillna(0)      # training set
mk=lambda:Model()
cv4=loso(mk,W,M); cv3=loso(mk,M,M)
nok=lambda cv:cv[~cv.project.str.contains('KENT')]
rows=[dict(model='v3 (monthly rows only)',**score(cv3)),dict(model='v4 (weekly rows reconciled to monthly + monthly rows)',**score(cv4)),dict(model='v3 excl. KENT',**score(nok(cv3))),dict(model='v4 excl. KENT',**score(nok(cv4)))]
tr=W[W.index.get_level_values(1)<'2026-01-01']; te=M[M.index.get_level_values(1)>='2026-01-01']; tr3=M[M.index.get_level_values(1)<'2026-01-01']
for nm,t in (('v3 time split (train to Dec 2025, test 2026)',tr3),('v4 time split (train to Dec 2025, test 2026)',tr)):
    rows.append(dict(model=nm,**score(pd.DataFrame({'project':te.index.get_level_values(0),'fuel':te.fuel.values,'pred':mk().fit(t).predict(te).values}))))
R=pd.DataFrame(rows).set_index('model'); R.to_csv(f'{out}/model_comparison_v4.csv'); pd.set_option('display.width',250)
print(R.drop(columns='n').map(lambda v:f'{v:.1%}').assign(n=R.n).to_string())
g=cv4.groupby('project'); S=pd.DataFrame({'months':g.size(),'act_L':g.fuel.sum(),'pred_L':g.pred.sum()}); S['err_v4']=S.pred_L/S.act_L-1
g3=cv3.groupby('project'); S['err_v3']=g3.pred.sum()/g3.fuel.sum()-1; S.round(3).sort_values('err_v4').to_csv(f'{out}/loso_sites_v4.csv')
cv4.to_csv(f'{out}/loso_months_v4.csv',index=False)
# 4) final fit + bootstrap by site
m=mk().fit(W); nf=len(m.fam); q=float(m.coef[2*nf+2])
C={f'rated_h|{f}':float(m.coef[i]) for i,f in enumerate(m.fam)}; C.update({f'kwh|{f}':float(m.coef[nf+i]) for i,f in enumerate(m.fam)})
C.update({'rated_h|*':float(m.coef[2*nf]),'kwh|*':float(m.coef[2*nf+1]),'kwh_l|*':q,'country|KSA':m.m['KSA'],'country|UAE':m.m['UAE'],'_basis':'site DG-meter kWh; monthly-report fuel (weekly rows reconciled)','_n_rows':len(W)})
json.dump(C,open(f'{out}/coef_v4.json','w'),indent=1,ensure_ascii=False)
rng=np.random.default_rng(1); sites=list(W.index.get_level_values(0).unique()); B=[]
for i in range(150):
    pick=rng.choice(sites,len(sites),replace=True); bd=pd.concat([W.loc[[p]].rename(index=lambda x:f'{x}#{j}',level=0) for j,p in enumerate(pick)])
    try: B.append(mk().fit(bd))
    except Exception: pass
fam_all=families(W); tot=W[[f'kwh|{k}' for k in fam_all]].sum().sum(); rows=[]
for f in m.fam:
    n=int((W[f'rated_h|{f}']>0).sum()); ns=int((W[f'rated_h|{f}']>0).groupby(level=0).any().sum())
    for cty in ('UAE','KSA'):
        r=dict(family=f,country=cty,rows=n,sites=ns,share_of_fleet_kwh=W[f'kwh|{f}'].sum()/tot,a_fixed=C[f'rated_h|{f}']*m.m[cty],b_marginal=C[f'kwh|{f}']*m.m[cty],q_quadratic=q*m.m[cty])
        for l in (.25,.35,.5,.75):
            r[f'L/kWh@{int(l*100)}%']=m.curve(f,l,cty); e=np.array([b.curve(f,l,cty) for b in B if f in b.fam])
            if len(e)>20: r[f'@{int(l*100)}% p10']=np.quantile(e,.1); r[f'@{int(l*100)}% p90']=np.quantile(e,.9)
        rows.append(r)
CV=pd.DataFrame(rows); CV.to_csv(f'{out}/fuel_curves_v4.csv',index=False)
print(S.round(3).sort_values('err_v4').to_string())
print(CV[CV.country=='UAE'][['family','sites','rows','share_of_fleet_kwh','L/kWh@25%','L/kWh@35%','@35% p10','@35% p90','L/kWh@50%','L/kWh@75%']].sort_values('L/kWh@35%').round(3).to_string(index=False))
print('country:',round(m.m['KSA'],3),round(m.m['UAE'],3),' fleet prior a0,b0,q:',np.round(m.coef[2*nf:2*nf+3],4))
# 5) leave-one-site-out coefficient sets in the v3 JSON layout (for sim_all.py)
def as_json(mm):
    k=len(mm.fam); c={f'rated_h|{f}':float(mm.coef[i]) for i,f in enumerate(mm.fam)}; c.update({f'kwh|{f}':float(mm.coef[k+i]) for i,f in enumerate(mm.fam)})
    c.update({'rated_h|*':float(mm.coef[2*k]),'kwh|*':float(mm.coef[2*k+1]),'kwh_l|*':float(mm.coef[2*k+2]),'country|KSA':mm.m['KSA'],'country|UAE':mm.m['UAE']})
    allf=set(fam_all)|set(pd.read_csv(os.path.join(os.path.dirname(sys.argv[1]),'gen_families.csv')).family.dropna())|{f'unlisted {n}' for n in ['≤125 kVA','200–220 kVA','250 kVA','300 kVA','350 kVA','500 kVA','800 kVA','1000–1250 kVA']}
    c['_fold']={f:(f if f in mm.fam else '*') for f in allf}; return c
full=as_json(m); json.dump(full,open(f'{out}/coef_v4.json','w'),indent=1,ensure_ascii=False)
json.dump({p:as_json(mk().fit(W.drop(index=p,level=0))) for p in sites},open(f'{out}/loso_coefs_v4.json','w'),ensure_ascii=False)
