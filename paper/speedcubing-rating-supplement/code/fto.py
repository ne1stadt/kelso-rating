import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from core import *
W=pd.read_parquet('W_main.parquet'); R=pd.read_parquet('R_main.parquet')[EVENTS]; rt=Rater(W)
rng=np.random.default_rng(5); out=[]
for proxy in ['minx','sq1']:
    pool=W[[proxy,'333']].dropna().index; truth=pd.Series(rt.rate(proxy,W.loc[pool,proxy].values),index=pool)
    ov=lse(R.loc[pool,[e for e in EVENTS if e!=proxy]].values,400)
    for rule,s in [('uniform',None),('s=800',800),('s=400',400)]:
        w=np.ones(len(pool)) if s is None else 10**((ov-np.median(ov))/s); w=w/w.sum()
        for m in [50,100,250,500,1000,2500,5000]:
            rm=[]
            for rep in range(100):
                ids=pool[rng.choice(len(pool),size=m,replace=False,p=w)]
                g=W.loc[ids,[proxy,'333']]; Fe=KCDF(g[proxy].values); F3=KCDF(g['333'].values)
                est=elo_from_q(1-(rt.ref.n*rt.faster_share_ref(F3.Q(Fe.F(g[proxy].values)))+0.5)/(rt.ref.n+1))
                rm.append(np.sqrt(np.mean((est-truth.loc[ids].values)**2)))
            out.append({'proxy':NAMES[proxy],'rule':rule,'n':m,'rmse':round(float(np.mean(rm)),1),'mcse':round(float(np.std(rm)/10),1)})
D=pd.DataFrame(out); print(D.pivot_table(index=['proxy','n'],columns='rule',values='rmse').to_string()); print('max mcse',D.mcse.max())
D.to_csv('fto.csv',index=False)
