import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from core import *
d=rounds(); out={}
# Exposure: PB optimism vs number of rounds (3x3 and 4x4): rating(PB) - rating(median of averages)
W=pd.read_parquet('W_main.parquet'); rt=Rater(W)
for e in ['333','444','pyram']:
    x=d[(d.event==e)&(d.avg>0)]; g=x.groupby('id').avg
    df=pd.DataFrame({'pb':g.min(),'med':g.median(),'n':g.size()})
    df['gap']=rt.rate(e,df.pb.values)-rt.rate(e,df.med.values)
    df['nb']=pd.cut(df.n,[0,1,3,7,15,31,63,10000],labels=['1','2-3','4-7','8-15','16-31','32-63','64+'])
    out[NAMES[e]]={k:round(float(v),1) for k,v in df.groupby('nb',observed=True).gap.median().items()}
    out[NAMES[e]+'_n']={k:int(v) for k,v in df.groupby('nb',observed=True).size().items()}
print('exposure',out,flush=True)
# Observed drift: conversions frozen at end-2024 vs refit at Oct 2026, for results unchanged since 2024
Wp=build_values(years=(0,2024)); rp=Rater(Wp)
dr={}
for e in EVENTS:
    same=Wp[e].dropna(); cur=W[e].reindex(same.index); same=same[cur.values==same.values]
    a=rp.rate(e,same.values); b=rt.rate(e,same.values); diff=b-a
    q=pd.Series(a,index=same.index)
    dr[NAMES[e]]={'n':int(len(same)),'median':round(float(np.median(diff)),1),'top1pct':round(float(np.median(diff[a>=np.quantile(a,0.99)])),1)}
print('drift',dr,flush=True)
json.dump({'exposure':out,'drift':dr},open('exposure_drift.json','w'),indent=1)
