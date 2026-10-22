# Performance (round-level) bootstrap: resample each competitor's own round results with replacement and take the best,
# conversions held fixed; rate the top 5,000.
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from core import *
W=pd.read_parquet('W_main.parquet'); O=pd.read_parquet('O_main.parquet')['overall']; R=pd.read_parquet('R_main.parquet')[EVENTS]
rt=Rater(W); top=O.index[:5000]; pos={i:k for k,i in enumerate(top)}
d=rounds(); single=d.event.isin(['333bf','444bf','555bf','333mbf'])
d=d.assign(val=np.where(single,d.single,d.avg)); d=d[(d.val>0)&d.id.isin(top)]
blocks={}
for e in EVENTS:
    x=d[d.event==e].sort_values('id'); v=x.val.values.astype(float)
    if e=='333mbf': v=mbf_value(x.val.values)
    ids=x.id.values; first=np.r_[True,ids[1:]!=ids[:-1]]; st=np.where(first)[0]; k=np.diff(np.append(st,len(ids)))
    blocks[e]=(np.array([pos[i] for i in ids[st]]),st,k,v)
rng=np.random.default_rng(5); B=400; out=np.zeros((B,len(top)),np.float32)
for b in range(B):
    M=np.full((len(top),len(EVENTS)),np.nan)
    for j,e in enumerate(EVENTS):
        p,st,k,v=blocks[e]
        draw=st.repeat(k)+np.floor(rng.random(k.sum())*k.repeat(k)).astype(int)
        mins=np.minimum.reduceat(v[draw],np.r_[0,np.cumsum(k)[:-1]])
        M[p,j]=rt.rate(e,mins)
    out[b]=lse(M,400)
np.save('boot_perf.npy',out); print('done')
