# One row per competitor x competition x event x round: average, best single, position, competition year.
import json, glob, re
import pandas as pd
EV={'333','222','444','555','666','777','333bf','333fm','333oh','clock','minx','pyram','skewb','sq1','444bf','555bf','333mbf'}
rows=[]
for f in sorted(glob.glob('data/wca/persons-page-*.json')):
    for p in json.load(open(f))['items']:
        pid=p['id']
        for comp,evs in (p.get('results') or {}).items():
            m=re.search(r'(\d{4})$',comp); y=int(m.group(1)) if m else 0
            for e,rounds in evs.items():
                if e not in EV: continue
                for r in rounds:
                    rows.append((pid,comp,y,e,r.get('round'),r.get('position'),r.get('average') or 0,r.get('best') or 0))
df=pd.DataFrame(rows,columns=['id','comp','year','event','round','pos','avg','single'])
df.to_parquet('rounds.parquet',index=False)
print(len(df), df.year.min(), df.year.max()); print(df.head())
