"""v3 rating core.
Values: personal best per competitor x event (averages; singles for 3BLD/4BLD/5BLD; MBLD best single as 1/(points+fraction)).
All shares of a field come from Gaussian-kernel-continuized CDFs of log results (von Davier, Holland & Thayer 2004),
with Silverman's bandwidth and variance-preserving scaling. The same rule is used for the reference event and linked events.
"""
import numpy as np, pandas as pd
from scipy.stats import norm
EVENTS=['333','222','444','555','666','777','333bf','333fm','333oh','clock','minx','pyram','skewb','sq1','444bf','555bf','333mbf']
SINGLE_EVENTS={'333bf','444bf','555bf','333mbf'}
NAMES={'333':'3x3','222':'2x2','444':'4x4','555':'5x5','666':'6x6','777':'7x7','333bf':'3BLD','333fm':'FMC','333oh':'OH','clock':'Clock','minx':'Megaminx','pyram':'Pyraminx','skewb':'Skewb','sq1':'Square-1','444bf':'4BLD','555bf':'5BLD','333mbf':'MBLD'}
def mbf_value(v):
    v=np.asarray(v,dtype='int64'); dd=v//10_000_000; tt=(v//100)%100_000
    return 1.0/np.maximum((99-dd)+(3600-np.minimum(tt,3600))/3600.0,0.25)
_R=None
def rounds():
    global _R
    if _R is None: _R=pd.read_parquet('rounds.parquet')
    return _R
def build_values(years=None, stat='best', bld='single'):
    d=rounds()
    if years is not None: d=d[(d.year>=years[0])&(d.year<=years[1])]
    out={}
    for e in EVENTS:
        x=d[d.event==e]
        use_single = (e=='333mbf') or (bld=='single' and e in SINGLE_EVENTS)
        col='single' if use_single else 'avg'
        x=x[x[col]>0]
        if e=='333mbf':
            v=pd.Series(mbf_value(x[col].values),index=x.id.values)
        else:
            v=pd.Series(x[col].values.astype(float),index=x.id.values)
        g=v.groupby(level=0)
        out[e]=g.min() if stat=='best' else g.median()
    return pd.DataFrame(out)
class KCDF:
    """Kernel-continuized CDF of log values on a grid."""
    def __init__(self, vals, hmult=1.0, G=8192):
        z=np.log(np.asarray(vals,float)); n=len(z); mu=z.mean(); sd=z.std()
        iqr=np.subtract(*np.percentile(z,[75,25]))
        h=hmult*0.9*min(sd, iqr/1.34)*n**(-0.2)
        a=np.sqrt(sd**2/(sd**2+h**2)); zz=a*z+(1-a)*mu; s=a*h
        lo,hi=zz.min()-8*s, zz.max()+8*s
        grid=np.linspace(lo,hi,G); dx=grid[1]-grid[0]
        hist=np.bincount(np.clip(np.round((zz-lo)/dx).astype(int),0,G-1),minlength=G).astype(float)/n
        k=np.arange(-int(8*s/dx)-1,int(8*s/dx)+2)*dx
        pdf=np.convolve(hist,norm.pdf(k,scale=s)*dx,mode='same')
        cdf=np.cumsum(pdf); cdf=cdf/cdf[-1]
        # tails: exact Gaussian tail of the extreme kernels for precision far from the data
        self.grid, self.cdf, self.h, self.n = grid, np.maximum.accumulate(cdf), h, n
        self.zz, self.s = zz, s
    def F(self, v):
        z=np.log(np.asarray(v,float)); return np.interp(z,self.grid,self.cdf,left=0.0,right=1.0)
    def tail_F(self, v):
        """Exact continuized CDF for a few values (used for extreme results)."""
        z=np.log(np.atleast_1d(np.asarray(v,float)))
        return np.array([norm.cdf((zi-self.zz)/self.s).mean() for zi in z])
    def Q(self, u):
        u=np.asarray(u,float); return np.exp(np.interp(u,self.cdf,self.grid))
def elo_from_q(q, floor=True):
    q=np.clip(q,1e-12,1-1e-12); r=1200+400*np.log10(q/(1-q))
    return np.maximum(0,r) if floor else r
class Rater:
    def __init__(self, W, anchor='333', hmult=1.0):
        self.W=W; self.a=anchor
        self.ref=KCDF(W[anchor].dropna().values,hmult)
        self.links={}
        for e in EVENTS:
            if e==anchor or e not in W: continue
            g=W[[e,anchor]].dropna()
            self.links[e]=(KCDF(g[e].values,hmult),KCDF(g[anchor].values,hmult),len(g))
    def faster_share_ref(self, t):
        t=np.atleast_1d(np.asarray(t,float)); F=np.atleast_1d(self.ref.F(t))
        ext=F<1e-4   # use exact kernel sum in the extreme fast tail
        if ext.any(): F=F.copy(); F[ext]=self.ref.tail_F(t[ext])
        return F
    def q(self, e, x):
        x=np.atleast_1d(np.asarray(x,float))
        if e==self.a: return 1-self.faster_share_ref(x)
        Fe,F3,n=self.links[e]
        u=np.atleast_1d(Fe.F(x)); ext=u<1e-3
        if ext.any(): u=u.copy(); u[ext]=Fe.tail_F(x[ext])
        t3=F3.Q(u)
        N=self.ref.n   # evaluate the 3x3 equivalent as a new member of the reference field (half tie with itself)
        return 1-(N*self.faster_share_ref(t3)+0.5)/(N+1)
    def rate(self, e, x, floor=True): return elo_from_q(self.q(e,x),floor)
def event_ratings(W, rater=None, **kw):
    rt=rater or Rater(W,**kw); R=pd.DataFrame(index=W.index,dtype=float)
    for e in EVENTS:
        v=W[e].dropna(); R.loc[v.index,e]=rt.rate(e,v.values)
    return R, rt
def lse(R, K):
    M=np.asarray(R,float); M=np.where(np.isnan(M),-np.inf,M)
    m=np.max(M,axis=-1,keepdims=True); return (m[...,0]+K*np.log10(np.sum(10**((M-m)/K),axis=-1)))
def expmean(R, K):
    M=np.asarray(R,float); n=np.sum(~np.isnan(M),axis=-1); return lse(R,K)-K*np.log10(n)
