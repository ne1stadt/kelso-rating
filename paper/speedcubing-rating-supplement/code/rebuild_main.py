import sys; sys.path.insert(0,'.')
import pandas as pd
from core import *
W=pd.read_parquet('W_main.parquet'); R,rt=event_ratings(W); R.to_parquet('R_main.parquet')
info=pd.read_csv('persons.csv',usecols=['id','name','country']).drop_duplicates('id').set_index('id')
O=pd.Series(lse(R[EVENTS].values,400),index=R.index).sort_values(ascending=False)
O.to_frame('overall').join(R).join(info).to_parquet('O_main.parquet')
print('leaders',{NAMES[e]:round(R[e].max()) for e in EVENTS}); print('top10',[(info.loc[i,'name'],round(O[i])) for i in O.index[:10]])
