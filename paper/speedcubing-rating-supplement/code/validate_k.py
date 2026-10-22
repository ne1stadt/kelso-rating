# Choose K for the level term M_K (exponential mean) by how well it predicts a competitor's held-out events.
# (1) leave-one-event-out on all-time data; (2) temporal: <=2024 ratings predict events first taken up in 2025-26.
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.stats import spearmanr
from core import *
R=pd.read_parquet('R_main.parquet')[EVENTS]
Ks=[25,50,100,150,200,300,400,500,600,800,1000,1300,1700,2200,3000,5000,1e9]
def loeo(R, Ks, min_events=2):
    M=R.values; has=~np.isnan(M); n=has.sum(1)
    keep=n>=min_events; M=M[keep]; has=has[keep]; n=n[keep]
    res={}
    for K in Ks:
        if K>=1e8:
            S=np.nansum(M,1)
            rows=[]
            for j,e in enumerate(EVENTS):
                m=has[:,j]; pred=(S[m]-M[m,j])/(n[m]-1); rows.append((spearmanr(pred,M[m,j]).statistic,m.sum()))
        else:
            mx=np.nanmax(M,1)
            E=np.where(has,10**((M-mx[:,None])/K),0); S=E.sum(1)
            rows=[]
            for j,e in enumerate(EVENTS):
                m=has[:,j]; rest=S[m]-E[m,j]; ok=rest>0
                pred=mx[m][ok]+K*np.log10(rest[ok]/(n[m][ok]-1))
                rows.append((spearmanr(pred,M[m,j][ok]).statistic,ok.sum()))
        r=np.array(rows); res[K]=float(np.average(r[:,0],weights=r[:,1]))
    # baselines
    base={}
    for name in ['max','median']:
        rows=[]
        for j,e in enumerate(EVENTS):
            m=has[:,j]; O=M[m].copy(); O[:,j]=np.nan
            pred=np.nanmax(O,1) if name=='max' else np.nanmedian(O,1)
            rows.append((spearmanr(pred,M[m,j]).statistic,m.sum()))
        r=np.array(rows); base[name]=float(np.average(r[:,0],weights=r[:,1]))
    return res,base,int(keep.sum())
res,base,n=loeo(R,Ks)
print('LOEO competitors',n); print({('mean' if k>1e8 else int(k)):round(v,4) for k,v in res.items()}, {k:round(v,4) for k,v in base.items()})
# per-event-group stability: optimum K among competitors with >=4 events
res4,base4,n4=loeo(R,Ks,4); print('>=4 events',n4,{('mean' if k>1e8 else int(k)):round(v,4) for k,v in res4.items()})
# temporal
Wp=build_values(years=(0,2024)); Rp,rt=event_ratings(Wp)
d=rounds(); post=build_values(years=(2025,2026))
T=[]
for e in EVENTS:
    ids=post[e].dropna().index; ids=ids[ids.isin(Rp.index)]; ids=ids[Rp.loc[ids,e].isna().values & (Rp.loc[ids].notna().sum(axis=1).values>0)]
    T.append(pd.DataFrame({'id':ids,'event':e,'T':rt.rate(e,post.loc[ids,e].values)}))
T=pd.concat(T)
tres={}
for K in Ks:
    lvl=pd.Series(np.asarray(expmean(Rp[EVENTS].values,K) if K<1e8 else np.nanmean(Rp[EVENTS].values,1)),index=Rp.index)
    rows=[(spearmanr(lvl.reindex(g.id).values,g['T']).statistic,len(g)) for e,g in T.groupby('event') if len(g)>=50]
    r=np.array(rows); tres[K]=float(np.average(r[:,0],weights=r[:,1]))
print('temporal pairs',len(T),{('mean' if k>1e8 else int(k)):round(v,4) for k,v in tres.items()})
json.dump({'loeo':{str(k):v for k,v in res.items()},'loeo_base':base,'loeo_n':n,'loeo4':{str(k):v for k,v in res4.items()},'temporal':{str(k):v for k,v in tres.items()},'temporal_n':int(len(T))},open('kfit.json','w'),indent=1)
