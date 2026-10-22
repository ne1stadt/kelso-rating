# Table 8: top 20 with conversion (basic) and performance (percentile) bootstrap intervals.
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from core import *
O=pd.read_parquet('O_main.parquet')['overall']; R=pd.read_parquet('R_main.parquet')[EVENTS]
info=pd.read_csv('persons.csv',usecols=['id','country']).drop_duplicates('id').set_index('id')
ids=O.index[:5000]; th=O[ids].values
Bc=np.concatenate([np.load('bootA.npy'),np.load('bootB.npy')]); Bp=np.load('boot_perf.npy')
rk=lambda B:(-B).argsort(axis=1).argsort(axis=1)+1
rc,rp=rk(Bc),rk(Bp); qc=np.percentile(Bc,[2.5,97.5],axis=0); qp=np.percentile(Bp,[2.5,97.5],axis=0)
rows=[]
for k in range(20):
    i=ids[k]; ev=R.loc[i].dropna().sort_values(ascending=False)
    rows.append({'rank':k+1,'country':info.loc[i,'country'],'events':int(ev.size),'top2':', '.join('%s %d'%(NAMES[e],round(v)) for e,v in ev.head(2).items()),
      'rating':round(th[k]),'conv':[round(2*th[k]-qc[1,k]),round(2*th[k]-qc[0,k])],'perf':[round(qp[0,k]),round(qp[1,k])],
      'rank_conv':[float(np.percentile(rc[:,k],2.5)),float(np.percentile(rc[:,k],97.5))],'rank_perf':[float(np.percentile(rp[:,k],2.5)),float(np.percentile(rp[:,k],97.5))]})
json.dump(rows,open('table8.json','w'),indent=1,default=float); print(rows[:3])
