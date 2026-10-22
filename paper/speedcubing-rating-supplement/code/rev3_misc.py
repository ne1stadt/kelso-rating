import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.stats import spearmanr, pearsonr, norm, rankdata
from core import *
W=pd.read_parquet('W_main.parquet'); R=pd.read_parquet('R_main.parquet')[EVENTS]; O=pd.read_parquet('O_main.parquet')['overall']
R=R.loc[O.index]; W=W.loc[O.index]; rt=Rater(W); out={}
# 1 Pearson correlations in common groups (log results and normal scores)
pc={}
for e in EVENTS[1:]:
    g=W[[e,'333']].dropna(); a,b=np.log(g[e].values),np.log(g['333'].values)
    ns=lambda x: norm.ppf((rankdata(x)-0.5)/len(x))
    pc[NAMES[e]]={'pearson_log':round(pearsonr(a,b)[0],2),'pearson_ns':round(pearsonr(ns(a),ns(b))[0],2),'spearman':round(spearmanr(a,b).statistic,2)}
out['corr']=pc; print(pc)
# 2 own kernel mass at the 3x3 leader
k=rt.ref; z=np.log(W['333'].dropna().values); mu,sd=z.mean(),z.std(); a=np.sqrt(sd**2/(sd**2+k.h**2)); zl=z.min()
out['own_mass_leader']=round(float(norm.cdf((1-a)*(zl-mu)/(a*k.h))),3); out['h_over_sd']=round(float(k.h/sd),3)
# 3 floor
Rr=pd.DataFrame(index=W.index,dtype=float)
for e in EVENTS:
    v=W[e].dropna(); Rr.loc[v.index,e]=rt.rate(e,v.values,floor=False)
Rr=Rr[EVENTS]
nz=int((R==0).sum().sum()); tot=int(R.notna().sum().sum())
O_nf=pd.Series(lse(Rr.values,400),index=Rr.index); diff=(O_nf.clip(lower=-1e9)-O)
out['floor']={'event_ratings_at_0':nz,'event_ratings':tot,'competitors_changed_gt1':int((diff.abs()>1).sum()),'max_rating_affected':float(O[diff.abs()>1].max())}
# 4 adjacent gaps
top=O.iloc[:101].values; out['adjacent_gap_top100_median']=round(float(np.median(-np.diff(top))),1)
out['sd_event_ratings']={NAMES[e]:round(float(R[e].std()),0) for e in EVENTS}
# 5 two-parameter rule M_K + gamma log10 n
n=R.notna().sum(1).values; M=R.values
def two(Mx,nx,K=1300,g=400): return expmean(Mx,K)+g*np.log10(nx)
T=two(M,n); lowered=0; drops=[]
idx=np.where(n>=2)[0]
for i in idx:
    row=M[i].copy(); j=np.nanargmin(row); r2=row.copy(); r2[j]=np.nan
    without=two(r2[None,:],np.array([n[i]-1]))[0]
    if without>T[i]: lowered+=1; drops.append(without-T[i])
Ts=pd.Series(T,index=R.index)
out['two_param']={'K':1300,'gamma':400,'competitors_2plus':int(len(idx)),'weakest_event_lowers':int(lowered),'share':round(lowered/len(idx),3),'median_loss':round(float(np.median(drops)),1),
  'rho_top1000':round(spearmanr(O.iloc[:1000],Ts[O.index[:1000]]).statistic,3),'top20':len(set(O.index[:20])&set(Ts.sort_values(ascending=False).index[:20]))}
print(out['two_param'])
# 6 incentive: gain for top-1000 from one more event
med={e:float(np.nanmedian(R[e])) for e in EVENTS}; p90={e:float(np.nanquantile(R[e],0.9)) for e in EVENTS}
G={'median':[],'p90':[],'zero':[]}
for i in O.index[:1000]:
    r=O[i]
    for e in EVENTS:
        if np.isnan(R.at[i,e]):
            for lab,val in [('median',med[e]),('p90',p90[e]),('zero',0.0)]:
                G[lab].append(400*np.log10(1+10**((val-r)/400)))
out['incentive_top1000']={lab:{'median':round(float(np.median(v)),2),'max':round(float(np.max(v)),1),'n':len(v)} for lab,v in G.items()}
out['missing_events_top1000_median']=float(np.median(17-R.loc[O.index[:1000]].notna().sum(1)))
print(out['incentive_top1000'])
# 7 effective number of events
C=np.eye(17)
for a_ in range(17):
    for b_ in range(a_+1,17):
        g=R[[EVENTS[a_],EVENTS[b_]]].dropna()
        C[a_,b_]=C[b_,a_]=spearmanr(g.iloc[:,0],g.iloc[:,1]).statistic if len(g)>50 else 0
has=R.notna().values.astype(float); neff=(has.sum(1)**2)/np.einsum('ij,jk,ik->i',has,C,has)
Oe=pd.Series(expmean(M,400)+400*np.log10(neff),index=R.index)
out['neff']={'corr_matrix_min':round(float(C[C<0.999].min()),2),'corr_matrix_max':round(float(C[C<0.999].max()),2),'neff_17':round(float((17**2)/C.sum()),2),
  'top100_n_median':float(np.median(has[:100].sum(1))),'top100_neff_median':round(float(np.median(neff[:100])),2),
  'rho_top1000':round(spearmanr(O.iloc[:1000],Oe[O.index[:1000]]).statistic,3),'top20':len(set(O.index[:20])&set(Oe.sort_values(ascending=False).index[:20])),
  'breadth_top100_median':round(float(np.median((O-R.max(1)).iloc[:100])),1),'breadth_neff_top100_median':round(float(np.median((Oe-R.max(1))[O.index[:100]])),1)}
print(out['neff'])
pd.DataFrame(C,index=[NAMES[e] for e in EVENTS],columns=[NAMES[e] for e in EVENTS]).round(2).to_csv('event_corr.csv')
Oe.to_frame('neff').join(Ts.to_frame('two')).to_parquet('alt_rules.parquet')
# 8 profile percentiles
for v in [1227,1800,2258,3056,2970]: out.setdefault('profile_pct',{})[v]=round(float((O<v).mean()*100),1)
# 9 relative improvement grid
out['tenpct']={t:int(round(rt.rate('333',[t*90])[0]-rt.rate('333',[t*100])[0])) for t in [90,60,45,30,25,20,15,12,10,9,8,7,6,5]}
out['ladder']={t:int(round(rt.rate('333',[t*100])[0])) for t in [90,60,45,30,25,20,15,12,10,9,8,7,6,5]}
print(out['profile_pct'],out['tenpct'])
json.dump(out,open('rev3_misc.json','w'),indent=1,default=str)
