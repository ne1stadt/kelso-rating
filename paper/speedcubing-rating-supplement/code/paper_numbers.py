import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, json
from scipy.stats import spearmanr, skew
import pycountry_convert as pc
from core import *
W=pd.read_parquet('W_main.parquet'); R=pd.read_parquet('R_main.parquet')[EVENTS]; OM=pd.read_parquet('O_main.parquet'); O=OM['overall']
info=pd.read_csv('persons.csv',usecols=['id','name','country']).drop_duplicates('id').set_index('id')
nm=info['name'].str.split(' [(]').str[0]
rt=Rater(W); out={}; rng=np.random.default_rng(3)
# ---- field sizes and median 3x3 of each field (Fig 1)
out['fields']=[{'event':NAMES[e],'n':int(W[e].notna().sum()),'med333':round(float(W.loc[W[e].notna(),'333'].median()/100),2)} for e in EVENTS]
# ---- diagnostics per event
def conv(Fe_vals,F3_vals,x):
    Fe=KCDF(Fe_vals); F3=KCDF(F3_vals); u=Fe.F(x); return elo_from_q(1-(rt.ref.n*rt.faster_share_ref(F3.Q(u))+0.5)/(rt.ref.n+1))
def cont(c):
    try: return {'AS':'Asia','EU':'Europe','NA':'Americas','SA':'Americas'}.get(pc.country_alpha2_to_continent_code(c),'Other')
    except Exception: return 'Other'
region=info['country'].map({c:cont(c) for c in info['country'].dropna().unique()})
diag=[]
for e in EVENTS:
    if e=='333': continue
    g=W[[e,'333']].dropna(); ev=g[e].values; th=g['333'].values; n=len(g)
    rho=spearmanr(ev,th).statistic
    x1=np.quantile(ev,0.01); base1=conv(ev,th,[x1])[0]
    le,l3=np.log(ev),np.log(th); lin=elo_from_q(1-(rt.ref.n*rt.faster_share_ref(np.exp(l3.mean()+l3.std()*(np.log(x1)-le.mean())/le.std()))+0.5)/(rt.ref.n+1))[0]
    bs=[conv(ev[i],th[i],[x1])[0] for i in [rng.integers(0,n,n) for _ in range(300)]]
    xs=np.quantile(W[e].dropna().values,np.linspace(0.01,0.99,99)); base=conv(ev,th,xs)
    def remsd(lab):
        tot=0
        for L in np.unique(lab):
            m=lab==L
            if m.sum()<30: continue
            tot=tot+m.mean()*(conv(ev[m],th[m],xs)-base)**2
        return float(np.sqrt(np.mean(tot)))
    yy=g.index.str[:4].astype(int).values; lc=np.where(yy<=2017,'a','b'); lr=region.reindex(g.index).fillna('Other').values
    diag.append({'event':NAMES[e],'n':n,'rho':round(rho,2),'skew_e':round(float(skew(np.log(ev))),2),'skew_3':round(float(skew(np.log(th))),2),
        'lin_minus_eq':int(round(float(lin)-base1)),'se_top1':int(round(np.std(bs))),'remsd_c':int(round(remsd(lc))),'remsd_c_rand':int(round(np.mean([remsd(rng.permutation(lc)) for _ in range(10)]))),
        'remsd_r':int(round(remsd(lr))),'remsd_r_rand':int(round(np.mean([remsd(rng.permutation(lr)) for _ in range(10)])))})
    print(diag[-1],flush=True)
out['diag']=diag
# ---- distribution of overall (survival rows) and levels
out['pct']={str(p):int(round(O.quantile(p))) for p in [0.01,0.05,0.1,0.2,0.5,0.75,0.9,0.99,0.999,0.9999]}
out['counts']={'n':int(len(O)),'ge2500':int((O>=2500).sum()),'ge3000':int((O>=3000).sum()),'zero':int((O<=0.5).sum()),'max':int(round(O.max()))}
out['surv']=[{'lo':lo,'share':float((O>=lo).mean())} for lo in range(0,3700,100)]
# ---- top 20
t=[]
for k,i in enumerate(O.index[:20]):
    ev=R.loc[i].dropna().sort_values(ascending=False)
    t.append([k+1,nm.get(i,i),info.loc[i,'country'],int(round(O[i])),int(ev.size),', '.join('%s %d'%(NAMES[e],round(v)) for e,v in ev.head(2).items())])
out['top20']=t
# ---- example profiles
prof={'Starting':{'333':45,'222':15,'pyram':20},'Intermediate':{'333':20,'222':7,'pyram':8,'skewb':9,'444':90,'333oh':40},'Advanced':{'333':10,'222':3.5,'pyram':4.5,'skewb':5,'444':40,'555':80,'333oh':16,'333bf':60}}
ex=[]
for k,p in prof.items():
    rs={e:float(rt.rate(e,[v*100])[0]) for e,v in p.items()}
    ex.append({'level':k,'events':{NAMES[e]:[v,int(round(rs[e]))] for e,v in p.items()},'single':int(round(rs['333'])),'best':int(round(max(rs.values()))),'overall':int(round(lse(np.array([list(rs.values())]),400)[0]))})
rk=O.rank(ascending=False,method='min'); cnt=R.notna().sum(axis=1)
for cond,lab in [(cnt<=5,'few'),(cnt>=14,'many')]:
    c=rk[cond&(rk<=100)].sort_values(ascending=False); i=c.index[0]; ev=R.loc[i].dropna().sort_values(ascending=False)
    ex.append({'level':'top100_'+lab,'name':nm.get(i,i),'rank':int(rk[i]),'n':int(ev.size),'events':{NAMES[e]:int(round(v)) for e,v in ev.head(4).items()},'best':int(round(ev.iloc[0])),'overall':int(round(O[i]))})
out['examples']=ex
# ---- theoretical max: add a competitor slightly better than every WR
W2=W.copy(); W2.loc['SUPER']=[W[e].min()*0.999 for e in W.columns]; rt2=Rater(W2)
rs=[float(rt2.rate(e,[W2.loc['SUPER',e]])[0]) for e in EVENTS]
out['super']={'events':{NAMES[e]:int(round(r)) for e,r in zip(EVENTS,rs)},'overall':int(round(lse(np.array([rs]),400)[0])),'no_clock':int(round(lse(np.array([[r for e,r in zip(EVENTS,rs) if e!='clock']]),400)[0]))}
# ---- leaders, ceilings, own-field ceilings, specialist rank
ceil=[]
for e in EVENTS:
    v=W[e].dropna().values; r=R[e].dropna().values; n=len(v)
    own=KCDF(v); lead=v.min(); ownr=float(np.atleast_1d(elo_from_q(1-own.tail_F([lead])[0]))[0])
    ceil.append({'event':NAMES[e],'n':n,'slowest':int(round(r.min())),'median':int(round(np.median(r))),'leader':int(round(r.max())),'own':int(round(ownr)),'rank_if_only':int((O>r.max()).sum()+1)})
out['ceilings']=ceil
# ---- marginal value (3x3 only)
out['minus3']=[{'from':t_,'to':t_-3,'r0':int(round(rt.rate('333',[t_*100])[0])),'r1':int(round(rt.rate('333',[(t_-3)*100])[0]))} for t_ in [60,45,30,25,20,15,12,10,9,8]]
out['tenpct']={t_:int(round(rt.rate('333',[t_*90])[0]-rt.rate('333',[t_*100])[0])) for t_ in [60,30,20,10,8,6]}
out['ladder']={t_:int(round(rt.rate('333',[t_*100])[0])) for t_ in [60,30,20,15,10,7,5]}
# ---- breadth increments at K=400
out['breadth']={'two_equal':round(400*np.log10(2)),'seventeen':round(400*np.log10(17)),'second':{x:int(round(lse(np.array([[2000,x]]),400)[0]-2000)) for x in [2000,1600,1200,800]}}
r12=float(rt.rate('333',[1200])[0]); r3b=float(rt.rate('333bf',[18000])[0]); out['bld_example']=[int(round(r12)),int(round(r3b)),int(round(lse(np.array([[r12,r3b]]),400)[0]))]
# ---- Clock removal
O2=pd.Series(lse(R.drop(columns=['clock']).values,400),index=R.index); d=O2-O; rk2=O2.rank(ascending=False,method='min')
t100=rk[rk<=100].index; t1000=rk[rk<=1000].index
out['clock']={'n':int(R['clock'].notna().sum()),'only':int(((cnt==1)&R['clock'].notna()).sum()),'mean_top100':round(float(d[t100].mean()),1),'max_top100':round(float(d[t100].min()),1),'best_top1000':int((R.loc[t1000].idxmax(axis=1)=='clock').sum())}
dd=d[t1000].sort_values().head(5); out['clock_losers']=[[nm.get(i,i),int(round(R.loc[i,'clock'])),int(round(dd[i])),int(rk[i]),int(rk2[i])] for i in dd.index]
json.dump(out,open('paper_numbers.json','w'),indent=1,ensure_ascii=False,default=str)
print(json.dumps({k:out[k] for k in ['pct','counts','examples','super','ceilings','minus3','tenpct','ladder','breadth','bld_example','clock','clock_losers']},ensure_ascii=False,default=str))
