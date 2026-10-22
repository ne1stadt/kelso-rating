# Agreement of the overall rating with existing combined metrics, all competitors and top 1000 / top 100.
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.stats import spearmanr
from core import *
W=pd.read_parquet('W_main.parquet'); R=pd.read_parquet('R_main.parquet')[EVENTS]; O=pd.read_parquet('O_main.parquet')['overall']
W=W.loc[O.index]; R=R.loc[O.index]
k=pd.DataFrame({e:W[e].min()/W[e] for e in EVENTS}).fillna(0); kinch=100*k.mean(1)
rk=pd.DataFrame({e:W[e].rank(method='min').fillna(W[e].notna().sum()+1) for e in EVENTS}); sor=-rk.sum(1)
euc=pd.Series(np.sqrt((np.clip(R.fillna(0).values-1000,0,None)**2).sum(1)),index=R.index)
mean=R.mean(1); best=R.max(1)
M={'Kinch':kinch,'Sum of Ranks':sor,'Euclidean above 1000':euc,'Best event':best,'Mean of event ratings':mean}
res={}
t1000=O.index[:1000]; t100=set(O.index[:100])
for n,s in M.items():
    res[n]={'all':round(spearmanr(O,s).statistic,2),'top1000':round(spearmanr(O[t1000],s[t1000]).statistic,2),'top100_overlap':len(t100&set(s.sort_values(ascending=False).index[:100]))}
res['Kinch_vs_SoR']=round(spearmanr(kinch,sor).statistic,2)
lead=R.max(); res['lse_leaders']=int(round(lse(np.array([lead.values]),400)[0])); res['lse_leaders_noclock']=int(round(lse(np.array([lead.drop('clock').values]),400)[0]))
res['kinch_median']=round(float(kinch.median()),1)
print(res); json.dump(res,open('agree.json','w'),indent=1)
