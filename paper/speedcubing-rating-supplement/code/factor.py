# One-factor latent-trait model of normal scores across all 17 events (all common groups at once, entry assumed MAR),
# fitted by EM; compared with the 3x3-anchored rating.
import sys, time; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.stats import norm, rankdata, spearmanr
from core import *
W=pd.read_parquet('W_main.parquet'); O=pd.read_parquet('O_main.parquet')['overall']; R=pd.read_parquet('R_main.parquet')[EVENTS]
W=W.loc[O.index]; R=R.loc[O.index]
t0=time.time()
Z=np.full(W.shape,np.nan)
for j,e in enumerate(EVENTS):
    v=W[e].values; m=~np.isnan(v); Z[m,j]=-norm.ppf((rankdata(v[m])-0.5)/m.sum())   # higher = better within the event's own field
M=~np.isnan(Z); Zf=np.where(M,Z,0)
mu=np.zeros(17); lam=np.full(17,0.5); psi=np.ones(17)
for it in range(200):
    prec=1+(M*(lam**2/psi)).sum(1); mean=((Zf-mu)*M*(lam/psi)).sum(1)/prec; var=1/prec
    Eth=mean[:,None]; Eth2=(mean**2+var)[:,None]
    n=M.sum(0); s1=(M*Eth).sum(0); s2=(M*Eth2).sum(0); sz=(Zf*M).sum(0); szt=(Zf*M*Eth).sum(0)
    # solve [n s1; s1 s2][mu lam] = [sz szt]
    det=n*s2-s1*s1; mu_n=(s2*sz-s1*szt)/det; lam_n=(n*szt-s1*sz)/det
    res=((Zf-mu_n)**2*M).sum(0)-2*lam_n*((Zf-mu_n)*M*Eth).sum(0)+lam_n**2*s2
    psi_n=np.maximum(res/n,1e-3)
    ch=np.max(np.abs(lam_n-lam)); mu,lam,psi=mu_n,lam_n,psi_n
    if ch<1e-6: break
prec=1+(M*(lam**2/psi)).sum(1); th=pd.Series(((Zf-mu)*M*(lam/psi)).sum(1)/prec,index=O.index); sdth=np.sqrt(1/prec)
t_fit=time.time()-t0
mean=R.mean(1); best=R.max(1)
def cmp(x):
    t=O.index[:1000]; return {'rho_all':round(spearmanr(O,x).statistic,3),'rho_top1000':round(spearmanr(O[t],x[t]).statistic,3),'top20':len(set(O.index[:20])&set(x.sort_values(ascending=False).index[:20])),'top100':len(set(O.index[:100])&set(x.sort_values(ascending=False).index[:100]))}
out={'iterations':it+1,'seconds':round(t_fit,1),'loadings':{NAMES[e]:round(float(l),3) for e,l in zip(EVENTS,lam)},'uniqueness':{NAMES[e]:round(float(p),3) for e,p in zip(EVENTS,psi)},
     'theta_vs_rating':cmp(th),'mean_vs_rating':cmp(mean),'theta_vs_mean_top1000':round(spearmanr(th[O.index[:1000]],mean[O.index[:1000]]).statistic,3)}
# latent placement of each event's leading result: theta implied by that result alone, as a percentile of all competitors
lead=[]
for j,e in enumerate(EVENTS):
    zmax=np.nanmax(Z[:,j]); thl=(lam[j]*(zmax-mu[j])/psi[j])/(1+lam[j]**2/psi[j])
    q=norm.cdf(thl); lead.append({'event':NAMES[e],'theta':round(float(thl),2),'rating_equiv':int(round(1200+400*np.log10(q/(1-q)))),'linked_leader':int(round(R[e].max()))})
out['leaders_latent']=sorted(lead,key=lambda r:-r['theta'])
out['rho_leader_orders']=round(spearmanr([r['theta'] for r in lead],[r['linked_leader'] for r in lead]).statistic,3)
th.to_frame('theta').to_parquet('theta.parquet')
print(json.dumps(out,indent=1)); json.dump(out,open('factor.json','w'),indent=1)
