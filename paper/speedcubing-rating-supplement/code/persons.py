# Competitor identifiers and countries from the mirrored WCA export (persons-page-*.json).
import json, glob, pandas as pd
rows=[(p['id'],p['name'],p['country']) for f in sorted(glob.glob('data/wca/persons-page-*.json')) for p in json.load(open(f))['items']]
pd.DataFrame(rows,columns=['id','name','country']).to_csv('persons.csv',index=False)
