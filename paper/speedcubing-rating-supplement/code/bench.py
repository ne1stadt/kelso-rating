import sys, time; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from core import *
t=time.time(); d=rounds(); t_load=time.time()-t
t=time.time(); W=build_values(); t_W=time.time()-t
t=time.time(); rt=Rater(W); t_fit=time.time()-t
t=time.time(); R,_=event_ratings(W,rater=rt); t_rate=time.time()-t
t=time.time(); O=lse(R[EVENTS].values,400); t_lse=time.time()-t
# incremental: one competition's results (a large 2026 competition)
c=d[d.year==2026].groupby('comp').size().sort_values().index[-1]; x=d[d.comp==c]
n_res=len(x); ids=x.id.unique()
t=time.time()
for _ in range(20):
    Wn=W.loc[W.index.intersection(ids)].copy()
    for e in EVENTS:
        v=Wn[e].dropna()
        if len(v): rt.rate(e,v.values)
    lse(Wn.values,400)
t_inc=(time.time()-t)/20
import os
out={'cpu':os.popen("lscpu | grep 'Model name'").read().strip(),'cores_used':1,'rows_rounds':int(len(d)),'competitors':int(len(W)),
 'build_personal_bests_s':round(t_W,1),'fit_17_distributions_16_links_s':round(t_fit,1),'rate_all_s':round(t_rate,1),'aggregate_all_s':round(t_lse,2),
 'incremental_competition':{'comp':c,'results':int(n_res),'competitors':int(len(ids)),'seconds':round(t_inc,3)}}
print(out); json.dump(out,open('bench.json','w'),indent=1)
