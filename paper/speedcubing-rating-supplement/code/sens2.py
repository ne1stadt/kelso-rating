# Sensitivity, revised: one top-weighted criterion (rank-biased overlap) for every variant, plus new variants.
import sys, os, time; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.stats import spearmanr
from core import *
W=pd.read_parquet('W_main.parquet'); R=pd.read_parquet('R_main.parquet')[EVENTS]; O=pd.read_parquet('O_main.parquet')['overall']
rt=Rater(W)
def rbo(a,b,p=0.99,depth=1000):
    A=list(a.sort_values(ascending=False).index[:depth]); B=list(b.sort_values(ascending=False).index[:depth])
    sa,sb=set(),set(); ov=0; s=0
    for d in range(1,depth+1):
        x,y=A[d-1],B[d-1]
        if x==y: ov+=1
        else: ov+=(x in sb)+(y in sa)
        sa.add(x); sb.add(y); s+=p**(d-1)*ov/d
    return (1-p)*s + p**depth*ov/depth
res={}; V={}
def compare(Ox,label,extra=None):
    com=O.index.intersection(Ox.index); a=O[com]; b=Ox[com]
    t1000=a.sort_values(ascending=False).index[:1000]
    t20=set(a.sort_values(ascending=False).index[:20]); t20x=set(b.sort_values(ascending=False).index[:20])
    d={'n':int(len(com)),'rho_all':round(spearmanr(a,b).statistic,3),'rho_top1000':round(spearmanr(a[t1000],b[t1000]).statistic,3),
       'top20':len(t20&t20x),'rbo':round(rbo(a,b),3),'median':int(Ox.median()),'top20_mean_abs_change':round(float((b[list(t20)]-a[list(t20)]).abs().mean()),1)}
    if extra: d.update(extra)
    res[label]=d; V[label]=Ox; print(label,d,flush=True)
L=lambda Rx: pd.Series(lse(Rx[EVENTS].values,400),index=Rx.index)
for a in ['222','444']:
    Rx,_=event_ratings(W,anchor=a); compare(L(Rx),'anchor_'+a)
for hm in [0.5,2.0]:
    Rh,_=event_ratings(W,hmult=hm); compare(L(Rh),'bandwidth_x%s'%hm,{'leaders':{NAMES[e]:int(Rh[e].max()) for e in ['333','222','555bf']}})
Wm=build_values(bld='mean'); Rm,_=event_ratings(Wm); compare(L(Rm),'bld_means')
for K in [300,500,600,1300]:
    compare(pd.Series(lse(R.values,K),index=R.index),'K_%d'%K)
Ww=build_values(years=(2025,2026)); Rw,_=event_ratings(Ww); compare(L(Rw),'window_2025_26')
Wd=build_values(stat='median'); Rd,_=event_ratings(Wd); compare(L(Rd),'median_of_results')
# no floor
Rr=pd.DataFrame(index=W.index,dtype=float)
for e in EVENTS:
    v=W[e].dropna(); Rr.loc[v.index,e]=rt.rate(e,v.values,floor=False)
compare(L(Rr),'no_floor')
# exposure-adjusted: subtract c_e*log2(k), c_e from PB-minus-median gaps
d=rounds(); single=d.event.isin(['333bf','444bf','555bf','333mbf'])
d=d.assign(val=np.where(single,d.single,d.avg)); d=d[d.val>0]
cex={}; Ra=R.copy()
for e in EVENTS:
    x=d[d.event==e]
    v=x.val.values.astype(float)
    if e=='333mbf': v=mbf_value(x.val.values)
    s=pd.Series(v,index=x.id.values); g=s.groupby(level=0)
    df=pd.DataFrame({'pb':g.min(),'med':g.median(),'k':g.size()})
    df=df.loc[df.index.intersection(R[e].dropna().index)]
    gap=rt.rate(e,df.pb.values)-rt.rate(e,df.med.values); lk=np.log2(df.k.values)
    c=float(np.sum(gap*lk)/np.sum(lk*lk)); cex[NAMES[e]]=round(c,1)
    Ra.loc[df.index,e]=R.loc[df.index,e]-c*lk
compare(L(Ra.clip(lower=0)),'exposure_adjusted',{'c_per_doubling':cex})
# event scale rescaled by 400/s_e
if os.path.exists('h2h2.json'):
    S=json.load(open('h2h2.json'))['s_event']; Rs=R.copy()
    for e in EVENTS: Rs[e]=1200+(R[e]-1200)*400/S[NAMES[e]]['s']
    compare(L(Rs.clip(lower=0)),'rescaled_400_over_s',{'leaders':{NAMES[e]:int(Rs[e].max()) for e in EVENTS}})
A=pd.read_parquet('alt_rules.parquet')
compare(A['neff'],'neff_rule'); compare(A['two'],'two_param_K1300_g400')
json.dump(res,open('sens2.json','w'),indent=1,ensure_ascii=False)
pd.DataFrame(V).to_parquet('sens2_variants.parquet')
