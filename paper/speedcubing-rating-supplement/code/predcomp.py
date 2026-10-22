# Temporal validation of overall metrics: <=2024 metric predicts rating in an event first taken up in 2025-26.
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.stats import spearmanr
from core import *
Wp=build_values(years=(0,2024)); Rp,rt=event_ratings(Wp); post=build_values(years=(2025,2026))
T=[]
for e in EVENTS:
    ids=post[e].dropna().index; ids=ids[ids.isin(Rp.index)]; ids=ids[Rp.loc[ids,e].isna().values & (Rp.loc[ids].notna().sum(axis=1).values>0)]
    T.append(pd.DataFrame({'id':ids,'event':e,'T':rt.rate(e,post.loc[ids,e].values)}))
T=pd.concat(T); E=Rp[EVENTS]
k=pd.DataFrame(index=Wp.index)
for e in EVENTS:
    wr=Wp[e].min(); k[e]=wr/Wp[e]
rk=pd.DataFrame(index=Wp.index)
for e in EVENTS:
    s=Wp[e].dropna(); rk[e]=s.rank(method='min').reindex(Wp.index).fillna(len(s)+1)
preds={'This rating (K = 400)':pd.Series(lse(E.values,400),index=E.index),'Best event':E.max(axis=1),'Mean of event ratings':E.mean(axis=1),
       'Kinch':100*k.fillna(0).mean(axis=1),'Sum of Ranks':-rk.sum(axis=1),
       'Euclidean above F':pd.Series(np.sqrt((np.clip(np.nan_to_num(E.values,nan=0)-1000,0,None)**2).sum(1)),index=E.index)}
res={}
for n_,s in preds.items():
    rows=[(spearmanr(s.reindex(g.id).values,g['T']).statistic,len(g)) for e,g in T.groupby('event') if len(g)>=50]
    r=np.array(rows); res[n_]=round(float(np.average(r[:,0],weights=r[:,1])),3)
print(len(T),res); json.dump({'n':int(len(T)),'competitors':int(T.id.nunique()),'res':res},open('predcomp.json','w'),indent=1)
