"""Fuel-curve fit v3: kVA classes vs engine families, with country multiplier, Huber, shared quadratic; LOSO + time split.
usage: fit_fuel_v3.py fuel_dataset_v3.csv outdir"""
import sys, os, json, numpy as np, pandas as pd
from scipy.optimize import nnls
X=pd.read_csv(sys.argv[1],parse_dates=['month']).set_index(['project','month']); out=sys.argv[2]; os.makedirs(out,exist_ok=True)
ALL=sorted({c.split('|')[1] for c in X.columns if c.startswith('rated_h|')})
KCLS=[c for c in ALL if c.startswith('K:')]; FAM=[c for c in ALL if not c.startswith('K:')]
MINM=4
def mid_kva(c):
    import re; m=re.findall(r'(\d+)',c); return float(m[-1]) if m else 500
def fit_linear(df,classes,quad=True,huber=True):
    cls=[c for c in classes if (df[f'rated_h|{c}']>0).sum()>=MINM]
    # classes with too few months: fold into the nearest-kVA class present (by name number)
    fold={c:(c if c in cls else min(cls,key=lambda x:abs(mid_kva(x)-mid_kva(c)))) for c in classes}
    def design(d):
        d2={}
        for c in cls:
            for f in ('rated_h','kwh','kwh_l'):
                d2[f'{f}|{c}']=sum(d[f'{f}|{k}'] for k in classes if fold[k]==c)
        A=np.column_stack([d2[f'rated_h|{c}'] for c in cls]+[d2[f'kwh|{c}'] for c in cls]+([sum(d2[f'kwh_l|{c}'] for c in cls)] if quad else []))
        return A
    cols=[f'rated_h|{c}' for c in cls]+[f'kwh|{c}' for c in cls]+(['kwh_l|*'] if quad else [])
    A=design(df); y=df.fuel.values; W=np.ones(len(df))
    solve=lambda W:nnls(A*(W/y)[:,None],W)[0]
    coef=solve(W)
    if huber:
        for _ in range(5):
            r=(A@coef)/y-1; s=1.345*np.median(np.abs(r))/0.6745+1e-9
            coef=solve(W*np.where(np.abs(r)<=s,1,s/np.abs(r)))
    cf=dict(zip(cols,coef)); cf['_fold']=fold
    return (lambda d:pd.Series(design(d)@coef,index=d.index)),cf
def fit_country(df,base):
    pred,cf=base(df); m={'KSA':1.0,'UAE':1.0}
    for _ in range(6):
        cty=df.index.get_level_values(0).str[:3]; mv=np.array([m[c] for c in cty])
        r=np.log(df.fuel.values/(pred(df).values*mv)); m={c:float(np.exp(np.median(r[cty==c])))*m[c] for c in m}
        df2=df.copy(); df2['fuel']=df.fuel.values/np.array([m[c] for c in cty]); pred,cf=base(df2)
    cf=dict(cf); cf.update({'country|KSA':m['KSA'],'country|UAE':m['UAE']})
    return (lambda d:pred(d)*np.array([m[c] for c in d.index.get_level_values(0).str[:3]])),cf
def evaluate(name,fitter,df):
    rows=[]
    for p in df.index.get_level_values(0).unique():
        tr=df.drop(index=p,level=0); te=df.loc[[p]]; pr=fitter(tr)[0](te)
        rows.append(pd.DataFrame({'project':p,'month':te.index.get_level_values(1),'fuel':te.fuel.values,'pred':pr.values}))
    cv=pd.concat(rows); e=cv.pred/cv.fuel-1; st=cv.groupby('project').apply(lambda g:g.pred.sum()/g.fuel.sum()-1)
    tr=df[df.index.get_level_values(1)<'2026-01-01']; te=df[df.index.get_level_values(1)>='2026-01-01']; et=fitter(tr)[0](te)/te.fuel-1
    ins=fitter(df)[0](df)/df.fuel-1
    return dict(model=name,n=len(df),insample=ins.abs().median(),loso_month=e.abs().median(),loso_month_p90=e.abs().quantile(.9),bias=e.median(),
                loso_site=st.abs().median(),loso_site_p90=st.abs().quantile(.9),loso_site_worst=st.abs().max(),time_split=et.abs().median(),time_bias=et.median()),cv,st
MODELS=[
 ('kVA classes, no country',lambda d:fit_linear(d,KCLS)),
 ('kVA classes + country',lambda d:fit_country(d,lambda e:fit_linear(e,KCLS))),
 ('engine families, no country',lambda d:fit_linear(d,FAM)),
 ('engine families + country',lambda d:fit_country(d,lambda e:fit_linear(e,FAM))),
]
res=[];keep={}
for name,f in MODELS:
    r,cv,st=evaluate(name,f,X); res.append(r); keep[name]=(cv,st)
R=pd.DataFrame(res); pd.set_option('display.width',250)
print(R.set_index('model').map(lambda v:f'{v:.1%}' if isinstance(v,float) else v).to_string())
R.to_csv(f'{out}/model_comparison.csv',index=False)
for name,(cv,st) in keep.items(): st.rename('loso_err').to_csv(f'{out}/loso_site_{name.replace(" ","_").replace(",","")}.csv')
json.dump({k:v for k,v in keep.items() and {}.items()},open(os.devnull,'w'))

# ---------- final: engine families + country ----------
FINAL=lambda d:fit_country(d,lambda e:fit_linear(e,FAM))
pred,cf=FINAL(X); q=cf['kwh_l|*']
json.dump({k:(v if k!='_fold' else v) for k,v in cf.items()},open(f'{out}/coef_v3.json','w'),indent=1)
loso={p:{k:v for k,v in FINAL(X.drop(index=p,level=0))[1].items()} for p in X.index.get_level_values(0).unique()}
json.dump(loso,open(f'{out}/loso_coefs_v3.json','w'))
rng=np.random.default_rng(1); sites=list(X.index.get_level_values(0).unique()); B=[]
for i in range(120):
    pick=rng.choice(sites,len(sites),replace=True)
    bd=pd.concat([X.loc[[p]].rename(index=lambda x:f'{x}#{j}',level=0) for j,p in enumerate(pick)])
    try: B.append({k:v for k,v in FINAL(bd)[1].items() if k!='_fold'})
    except Exception: pass
B=pd.DataFrame(B)
rows=[]
for c in FAM:
    a=cf.get(f'rated_h|{c}'); b=cf.get(f'kwh|{c}')
    if a is None: continue
    kwh=X[f'kwh|{c}'].sum(); n=int((X[f'rated_h|{c}']>0).sum()); ns=int((X[f'rated_h|{c}']>0).groupby(level=0).any().sum())
    for cty in ('UAE','KSA'):
        m=cf[f'country|{cty}']; r=dict(family=c,country=cty,site_months=n,sites=ns,share_of_fleet_kwh=kwh/X[[f'kwh|{k}' for k in FAM]].sum().sum(),a_fixed=a*m,b_marginal=b*m,q_quadratic=q*m)
        for l in (.25,.35,.5,.75):
            r[f'L/kWh@{int(l*100)}%']=(b+a/l+q*l)*m
            if f'rated_h|{c}' in B:
                e=(B[f'kwh|{c}']+B[f'rated_h|{c}']/l+B['kwh_l|*']*l)*B[f'country|{cty}']; r[f'@{int(l*100)}% p10']=e.quantile(.1); r[f'@{int(l*100)}% p90']=e.quantile(.9)
        rows.append(r)
C=pd.DataFrame(rows); C.to_csv(f'{out}/fuel_curves_v3.csv',index=False)
cv,st=keep['engine families + country']
S=cv.groupby('project').apply(lambda g:pd.Series({'months':len(g),'act_L':g.fuel.sum(),'pred_L':g.pred.sum()})); S['err']=S.pred_L/S.act_L-1
S.round(3).sort_values('err').to_csv(f'{out}/loso_sites_v3.csv'); print(S.round(3).sort_values('err').to_string())
print(C[C.country=='UAE'][['family','sites','site_months','share_of_fleet_kwh','L/kWh@25%','L/kWh@35%','@35% p10','@35% p90','L/kWh@50%','L/kWh@75%']].sort_values('L/kWh@35%').round(3).to_string(index=False))
print('country:',round(cf['country|KSA'],3),round(cf['country|UAE'],3))
