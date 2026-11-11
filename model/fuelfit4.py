"""Fuel model v4 fitter: per-family (a,b) partially pooled toward a fleet curve, shared loading terms, optional extras,
country (and optional seasonal) multipliers. Relative-error Huber NNLS. Works on weekly and/or monthly rows."""
import numpy as np, pandas as pd
from scipy.optimize import nnls
A_REF,B_REF=0.03,0.22
def families(X): return sorted({c.split('|')[1] for c in X.columns if c.startswith('rated_h|')})
class Model:
    def __init__(s,lam=1e-4,extras=('kwh_l',),country=True,season=False,huber=True,qfam=0,gamma=False,scale_known=True):
        s.lam,s.extras,s.country,s.season,s.huber,s.qfam,s.gamma,s.scale_known=lam,tuple(extras),country,season,huber,qfam,gamma,scale_known; s.g=0.0; s.scale_ref=1.0
    def _design(s,d):
        cols=[d[f'rated_h|{f}'].values for f in s.fam]+[d[f'kwh|{f}'].values for f in s.fam]
        tot=lambda k:sum(d[f'{k}|{f}'].values for f in s.allfam if f'{k}|{f}' in d)
        # families not seen in training: use fleet prior (a0,b0)
        unseen=[f for f in s.allfam_of(d) if f not in s.fam]
        cols+= [sum((d[f'rated_h|{f}'].values for f in unseen),np.zeros(len(d))), sum((d[f'kwh|{f}'].values for f in unseen),np.zeros(len(d)))]
        cols+=[tot(k) for k in s.extras]
        cols+=[d[f'kwh_l|{f}'].values-0*1 for f in s.qf]   # family-specific quadratic deviation (added on top of shared q)
        return np.column_stack(cols)
    def allfam_of(s,d): return families(d)
    def _mult(s,d):
        m=np.ones(len(d))
        if s.country:
            c=d.index.get_level_values(0).str[:3]; m*=np.where(c=='KSA',s.m['KSA'],s.m['UAE'])
        if s.season:
            mo=pd.DatetimeIndex(d.index.get_level_values(1)).month.values; cty=d.index.get_level_values(0).str[:3]
            ph=np.cos(2*np.pi*(mo-7.5)/12); m*=np.exp(np.where(cty=='KSA',s.s['KSA'],s.s['UAE'])*ph)
        if s.gamma and 'scale' in d:
            sc=d['scale'].values if (s.scale_known or s._fitting) else np.full(len(d),s.scale_ref)
            m*=(sc/s.scale_ref)**(-s.g)
        return m
    def fit(s,d,w=None):
        s.allfam=families(d); s.fam=[f for f in s.allfam if (d[f'rated_h|{f}']>0).sum()>=3]
        s.m={'KSA':1.0,'UAE':1.0}; s.s={'KSA':0.0,'UAE':0.0}
        s.qf=[f for f in s.fam if s.qfam and (d[f'rated_h|{f}']>0).sum()>=s.qfam and (d[f'rated_h|{f}']>0).groupby(level=0).any().sum()>=4]
        s.scale_ref=float(np.median(d['scale'])) if 'scale' in d else 1.0
        s._fitting=True
        w0=np.ones(len(d)) if w is None else np.asarray(w,float)
        nf=len(s.fam); A=s._design(d); y=d.fuel.values; n=len(d); p=A.shape[1]
        # ridge rows pulling each family's a,b toward fleet a0,b0 (the two "unseen" columns hold a0,b0)
        R=np.zeros((2*nf,p)); ia0,ib0=2*nf,2*nf+1
        nobs=np.array([(d[f'rated_h|{f}']>0).sum() for f in s.fam])
        for i in range(nf):
            R[i,i]=1/A_REF; R[i,ia0]=-1/A_REF; R[nf+i,nf+i]=1/B_REF; R[nf+i,ib0]=-1/B_REF
        R*=np.sqrt(s.lam*np.median(nobs))
        def solve(W,yy):
            M=np.vstack([A*(W/yy)[:,None],R]); t=np.concatenate([W,np.zeros(2*nf)]); return nnls(M,t,maxiter=20000)[0]
        W=w0.copy()
        for it in range(8):
            yy=y/s._mult(d); s.coef=solve(W,yy)
            r=np.log(np.clip(A@s.coef,1e-9,None)*s._mult(d)/y)
            if s.huber:
                sc=1.345*np.median(np.abs(r))/0.6745+1e-9; W=w0*np.where(np.abs(r)<=sc,1,sc/np.abs(r))
            base=np.log(y/np.clip(A@s.coef,1e-9,None)); cty=d.index.get_level_values(0).str[:3]
            if s.season:
                mo=pd.DatetimeIndex(d.index.get_level_values(1)).month.values; ph=np.cos(2*np.pi*(mo-7.5)/12)
            for c in ('KSA','UAE'):
                k=(cty==c)
                if k.sum()<5: continue
                if s.season:
                    G=np.column_stack([np.ones(k.sum()),ph[k]]); sw=np.sqrt(W[k]); be=np.linalg.lstsq(G*sw[:,None],base[k]*sw,rcond=None)[0]
                    if s.country: s.m[c]=float(np.exp(be[0]))
                    s.s[c]=float(be[1])
                elif s.country: s.m[c]=float(np.exp(np.average(base[k],weights=W[k])))
            if s.gamma:
                r2=np.log(y/(np.clip(A@s.coef,1e-9,None)*s._mult(d))); x=-np.log(d['scale'].values/s.scale_ref); k=np.isfinite(x)
                s.g=float(np.clip(s.g+np.sum(W[k]*x[k]*r2[k])/max(np.sum(W[k]*x[k]**2),1e-9),-0.5,1.5))
        s._fitting=False
        return s
    def predict(s,d): return pd.Series(s._design(d)@s.coef*s._mult(d),index=d.index)
    def curve(s,f,l,cty='UAE'):
        nf=len(s.fam); a,b=(s.coef[s.fam.index(f)],s.coef[nf+s.fam.index(f)]) if f in s.fam else (s.coef[2*nf],s.coef[2*nf+1])
        ex=dict(zip(s.extras,s.coef[2*nf+2:])); qd=s.coef[2*nf+2+len(s.extras)+s.qf.index(f)] if f in s.qf else 0.0; v=a/l+b+(ex.get('kwh_l',0)+qd)*l+ex.get('kwh_l2',0)*l*l
        return v*s.m[cty]
def loso(make,train,test=None):
    """leave-one-site-out: fit on train rows of other sites, predict held-out site's rows in test (default: train)."""
    test=train if test is None else test; rows=[]
    for p in test.index.get_level_values(0).unique():
        tr=train.drop(index=p,level=0,errors='ignore'); te=test.loc[[p]]
        rows.append(pd.DataFrame({'project':p,'t':te.index.get_level_values(1),'fuel':te.fuel.values,'pred':make().fit(tr).predict(te).values}))
    return pd.concat(rows)
def score(cv):
    e=cv.pred/cv.fuel-1; g=cv.groupby('project'); st=g.pred.sum()/g.fuel.sum()-1
    return dict(n=len(cv),med=e.abs().median(),p90=e.abs().quantile(.9),within10=(e.abs()<.1).mean(),bias=e.median(),site_med=st.abs().median(),site_p90=st.abs().quantile(.9),site_max=st.abs().max(),fleet=cv.pred.sum()/cv.fuel.sum()-1)
