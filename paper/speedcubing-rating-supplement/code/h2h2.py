# Head-to-head validation, revised: pooled and per-event scale with competition-clustered bootstrap CIs, homogeneity,
# alternative links (lapse-logistic, probit), proper scores, calibration CIs, exposure covariate, Plackett-Luce on full orders.
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.optimize import minimize_scalar, minimize
from scipy.stats import norm, chi2
from core import *
LN=np.log(10)
Wp=build_values(years=(0,2024)); Rp,rt=event_ratings(Wp)
d=rounds()
# exposure: rounds with a valid result up to 2024, per competitor and event
valid=np.where(d.event.isin(['333bf','444bf','555bf','333mbf']),d.single>0,d.avg>0)
pre=d[(d.year<=2024)&valid]; K=pre.groupby(['id','event']).size()
post=d[(d.year>=2025)&(d.pos>0)].copy()
post['R']=[np.nan]*len(post)
ev_codes=post.event.values
Rv=np.full(len(post),np.nan)
for e in EVENTS:
    m=ev_codes==e; Rv[m]=Rp[e].reindex(post.id.values[m]).values
post['R']=Rv
post=post[~np.isnan(post.R)]
post['k']=K.reindex(pd.MultiIndex.from_arrays([post.id.values,post.event.values])).fillna(0).values+0.0
post['lk']=np.log2(np.maximum(post.k,1))
post['rid']=post.groupby(['comp','event','round']).ngroup()
n_rounds_all=d[(d.year>=2025)].groupby(['comp','event','round']).ngroups
rng=np.random.default_rng(1); rows=[]
for rid,g in post.groupby('rid',sort=False):
    k=len(g)
    if k<2: continue
    pos=g.pos.values; npair=min(40,k*(k-1)//2)
    i=rng.integers(0,k,npair*2); j=rng.integers(0,k,npair*2); ok=(i!=j)&(pos[i]!=pos[j]); i,j=i[ok][:npair],j[ok][:npair]
    if len(i)==0: continue
    rows.append(pd.DataFrame({'rid':rid,'comp':g.comp.values[0],'event':g.event.values[0],'d':g.R.values[i]-g.R.values[j],'dl':g.lk.values[i]-g.lk.values[j],'win':(pos[i]<pos[j]).astype(float)}))
P=pd.concat(rows,ignore_index=True); P.to_parquet('h2h2_pairs.parquet')
out={'pairs':int(len(P)),'rounds_with_pairs':int(P.rid.nunique()),'rounds_2025_26_all':int(n_rounds_all),'competitions':int(P.comp.nunique())}
print(out,flush=True)
def nll_logit(s,dd,w): p=1/(1+10**(-dd/s)); p=np.clip(p,1e-12,1-1e-12); return -np.sum(w*np.log(p)+(1-w)*np.log(1-p))
def fit_s(dd,w): return minimize_scalar(nll_logit,bounds=(50,3000),method='bounded',args=(dd,w)).x
dd,w=P.d.values,P.win.values
s_all=fit_s(dd,w); out['s_all']=round(s_all,1)
# alternative links
def nll_lapse(par):
    s,eps=par; p=eps/2+(1-eps)/(1+10**(-dd/s)); p=np.clip(p,1e-12,1-1e-12); return -np.sum(w*np.log(p)+(1-w)*np.log(1-p))
rl=minimize(nll_lapse,[376,0.02],bounds=[(50,3000),(0,0.5)]); s_l,eps=rl.x
def nll_probit(sig): p=np.clip(norm.cdf(dd/sig),1e-12,1-1e-12); return -np.sum(w*np.log(p)+(1-w)*np.log(1-p))
sp=minimize_scalar(nll_probit,bounds=(50,3000),method='bounded').x
def scores(p): p=np.clip(p,1e-12,1-1e-12); return {'logloss':round(float(-np.mean(w*np.log(p)+(1-w)*np.log(1-p))),4),'brier':round(float(np.mean((p-w)**2)),4)}
out['links']={'elo400':scores(1/(1+10**(-dd/400))),'logistic':dict(s=round(s_all,1),**scores(1/(1+10**(-dd/s_all)))),
 'lapse':dict(s=round(s_l,1),eps=round(eps,4),**scores(eps/2+(1-eps)/(1+10**(-dd/s_l)))),'probit':dict(sigma=round(sp,1),**scores(norm.cdf(dd/sp))),'base':scores(np.full(len(w),w.mean()))}
print(out['links'],flush=True)
# calibration bins with Wilson CIs
bins=[0,50,100,200,300,400,600,800,1200,5000]; ad=np.abs(dd); ww=np.where(dd>=0,w,1-w); cal=[]
for a,b in zip(bins[:-1],bins[1:]):
    m=(ad>=a)&(ad<b); n=m.sum(); ph=ww[m].mean(); z=1.96
    den=1+z*z/n; c=(ph+z*z/(2*n))/den; hw=z*np.sqrt(ph*(1-ph)/n+z*z/(4*n*n))/den; mid=ad[m].mean()
    cal.append({'lo':a,'hi':b,'mid':round(float(mid),1),'n':int(n),'obs':round(float(ph),4),'lo95':round(float(c-hw),4),'hi95':round(float(c+hw),4),
      'elo400':round(float(1/(1+10**(-mid/400))),4),'fit':round(float(1/(1+10**(-mid/s_all))),4),'lapse':round(float(eps/2+(1-eps)/(1+10**(-mid/s_l))),4)})
out['calibration']=cal
# per-event s, LR homogeneity, competition-cluster bootstrap
per={}; ll_sep=0
for e,g in P.groupby('event'):
    se=fit_s(g.d.values,g.win.values); per[e]=se; ll_sep+=nll_logit(se,g.d.values,g.win.values)
LR=2*(nll_logit(s_all,dd,w)-ll_sep); out['homogeneity']={'LR':round(float(LR),1),'df':len(per)-1,'p_naive':float(chi2.sf(LR,len(per)-1))}
comps=P.comp.unique(); cidx=pd.factorize(P.comp)[0]; order=np.argsort(cidx); starts=np.searchsorted(cidx[order],np.arange(len(comps)))
ends=np.append(starts[1:],len(P)); evc=P.event.values
Bs={e:[] for e in per}; Ball=[]
brng=np.random.default_rng(7)
for b in range(100):
    if b%10==0: print('boot',b,flush=True)
    pick=brng.integers(0,len(comps),len(comps))
    idx=np.concatenate([order[starts[c]:ends[c]] for c in pick])
    Ball.append(fit_s(dd[idx],w[idx]))
    ev=evc[idx]
    for e in per:
        m=ev==e; Bs[e].append(fit_s(dd[idx][m],w[idx][m]))
out['s_all_ci']=[round(float(np.percentile(Ball,2.5)),1),round(float(np.percentile(Ball,97.5)),1)]
out['s_event']={NAMES[e]:{'s':round(per[e],1),'lo':round(float(np.percentile(Bs[e],2.5)),1),'hi':round(float(np.percentile(Bs[e],97.5)),1),'pairs':int((evc==e).sum())} for e in per}
print(out['s_all'],out['s_all_ci'],out['homogeneity'],flush=True)
# exposure covariate in the pairwise logistic: logit = ln10*d/s + beta*dlog2k
dl=P.dl.values
def nll_exp(par):
    s,beta=par; z=LN*dd/s+beta*dl; p=np.clip(1/(1+np.exp(-z)),1e-12,1-1e-12); return -np.sum(w*np.log(p)+(1-w)*np.log(1-p))
re_=minimize(nll_exp,[376,0.0],method='Nelder-Mead'); s_x,beta=re_.x
out['exposure_pairs']={'s':round(s_x,1),'beta':round(beta,4),'points_per_doubling':round(float(beta*s_x/LN),1)}
print(out['exposure_pairs'],flush=True)
# Plackett-Luce on full finishing orders (ties broken at random), strength = ln10*R/s + beta*log2 k
Q=post[post.groupby('rid').R.transform('size')>=2].copy()
Q['u']=np.random.default_rng(3).random(len(Q))
Q=Q.sort_values(['rid','pos','u'],ascending=[True,False,True])   # worst first within round -> cumulative sum gives risk sets
rid=Q.rid.values; R=Q.R.values; lk=Q.lk.values
first=np.r_[True,rid[1:]!=rid[:-1]]; gstart=np.maximum.accumulate(np.where(first,np.arange(len(rid)),0))
def nll_pl(par):
    s,beta=par; th=LN*R/s+beta*lk; m=pd.Series(th).groupby(rid).transform('max').values
    ex=np.exp(th-m); cs=np.cumsum(ex); base=np.where(gstart>0,cs[gstart-1],0.0); risk=cs-base   # sum over self and all worse-placed
    # last element of each round (winner) has the full set; each position j uses the set of itself and all worse
    return -np.sum(th-m-np.log(risk)) 
rp=minimize(nll_pl,[376,0.0],method='Nelder-Mead',options={'xatol':0.5,'fatol':1}); s_pl,b_pl=rp.x
rp0=minimize_scalar(lambda s: nll_pl([s,0.0]),bounds=(50,3000),method='bounded')
out['plackett_luce']={'rounds':int(Q.rid.nunique()),'competitor_rounds':int(len(Q)),'s_no_exposure':round(rp0.x,1),'s':round(s_pl,1),'beta':round(b_pl,4),'points_per_doubling':round(float(b_pl*s_pl/LN),1),'LR_exposure':round(float(2*(rp0.fun-rp.fun)),1)}
print(out['plackett_luce'],flush=True)
json.dump(out,open('h2h2.json','w'),indent=1)
