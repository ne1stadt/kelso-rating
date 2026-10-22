# Competitor-level bootstrap SEs for Table 4 (temporal design and leave-one-out), K in {400, 1300, mean}.
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.stats import spearmanr, rankdata
from core import *
def wspear(pred,targ,ev,w=None):
    rs=[];ns=[]
    for e in np.unique(ev):
        m=ev==e
        if m.sum()<50: continue
        a=pred[m];b=targ[m]; ok=~np.isnan(a)
        rs.append(spearmanr(a[ok],b[ok]).statistic); ns.append(ok.sum())
    return np.average(rs,weights=ns)
# temporal
Wp=build_values(years=(0,2024)); Rp,rt=event_ratings(Wp); post=build_values(years=(2025,2026))
T=[]
for e in EVENTS:
    ids=post[e].dropna().index; ids=ids[ids.isin(Rp.index)]; ids=ids[Rp.loc[ids,e].isna().values & (Rp.loc[ids].notna().sum(axis=1).values>0)]
    T.append(pd.DataFrame({'id':ids,'event':e,'T':rt.rate(e,post.loc[ids,e].values)}))
T=pd.concat(T,ignore_index=True)
lv={K:pd.Series(np.asarray(expmean(Rp[EVENTS].values,K)),index=Rp.index) for K in [400,1300]}
lv['mean']=pd.Series(np.nanmean(Rp[EVENTS].values,1),index=Rp.index)
P={k:v.reindex(T.id).values for k,v in lv.items()}; ev=T.event.values; tg=T['T'].values
ids=T.id.values; u,inv=np.unique(ids,return_inverse=True)
rng=np.random.default_rng(11); B=100; bs={k:[] for k in P}
point={k:wspear(P[k],tg,ev) for k in P}
order=np.argsort(inv); starts=np.searchsorted(inv[order],np.arange(len(u))); ends=np.append(starts[1:],len(inv))
for b in range(B):
    pick=rng.integers(0,len(u),len(u)); idx=np.concatenate([order[starts[c]:ends[c]] for c in pick])
    for k in P: bs[k].append(wspear(P[k][idx],tg[idx],ev[idx]))
out={'temporal':{str(k):{'r':round(point[k],4),'se':round(float(np.std(bs[k])),4)} for k in P},
     'temporal_diff_mean_minus_400':{'d':round(point['mean']-point[400],4),'se':round(float(np.std(np.array(bs['mean'])-np.array(bs[400]))),4)},
     'temporal_diff_1300_minus_400':{'d':round(point[1300]-point[400],4),'se':round(float(np.std(np.array(bs[1300])-np.array(bs[400]))),4)}}
print(out,flush=True)
json.dump(out,open('kse.json','w'),indent=1)
