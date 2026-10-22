# Person-level joint bootstrap: resample competitors (with all their results), refit every kernel distribution and linking
# (a smoothed bootstrap), and rate the original top 5,000 with the refitted conversions. A rated competitor drawn k times
# is evaluated against the resampled field without their own k copies, as a new member (half-tie rule of Section 3.2);
# for k = 1 this is the main-analysis rule.
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, time
from core import *
seed=int(sys.argv[1]); B=int(sys.argv[2]); outf=sys.argv[3]
W=pd.read_parquet('W_main.parquet'); O=pd.read_parquet('O_main.parquet')['overall']
top=O.index[:5000]; Wt=W.loc[top]; pos=W.index.get_indexer(top)
rng=np.random.default_rng(seed)
out=np.zeros((B,len(top)),dtype=np.float32); t=time.time()
for b in range(B):
    idx=rng.integers(0,len(W),len(W)); k=np.bincount(idx,minlength=len(W))[pos]
    Wb=W.iloc[idx]; Wb.index=pd.RangeIndex(len(Wb))
    rt=Rater(Wb); M=np.full((len(top),len(EVENTS)),np.nan)
    for j,e in enumerate(EVENTS):
        v=Wt[e].values; m=~np.isnan(v)
        if not m.any(): continue
        if e=='333':
            N=rt.ref.n; kk=k[m]*1.0
            F=np.atleast_1d(rt.faster_share_ref(v[m]))
            q=1-(N*F-0.5*kk+0.5)/(N-kk+1)
            M[m,j]=elo_from_q(q)
        else:
            M[m,j]=rt.rate(e,v[m])
    out[b]=lse(M,400)
    if b%20==0: print(b,round(time.time()-t),flush=True)
np.save(outf,out); print('done',round(time.time()-t))
