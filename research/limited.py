"""Supplement CL-1 with sparse-history winner estimates and conditional submissions."""
from pathlib import Path
import json, math
import numpy as np
from sklearn.linear_model import LogisticRegression
def winner_inputs(a,b):
    def side(s):
        recent=s['history']
        return np.array([(s['elo']-1500)/100, (s['age'] or 30)/5,
                         (sum(h['win'] for h in recent)+2)/(len(recent)+4), math.log1p(s['total'])])
    return list(side(a)-side(b))

def submission_inputs(a,b,division,rounds):
    def rate(s,win):
        history=s['history']
        return (sum(h['win']==win and h['method']=='Submission' for h in history)+1)/(len(history)+5)
    return [rate(a,1),rate(b,0),(a['sub'] or 0)*a['minutes']/(a['minutes']+30),
            (a['td'] or 0)*a['minutes']/(a['minutes']+30),
            int(rounds==5),int('women' in division.lower())]

def supplement(rows,card,cl_test):
    path=Path(__file__).with_name('supplement-v1.json')
    if path.exists(): params=json.loads(path.read_text())
    else:
        train=[r for r in rows if r['day']<'2023']
        def fit(x,y,intercept):
            m=LogisticRegression(fit_intercept=intercept,max_iter=1000).fit(x,y)
            return [m.coef_[0].tolist(),float(m.intercept_[0])]
        params={'winner':fit([r['x'] for r in train],[r['y'] for r in train],False),
                'sub':fit([r['sa'] if r['y'] else r['sb'] for r in train],[r['sub'] for r in train],True)}
        path.write_text(json.dumps(params,indent=2))
    def predict(k,x):
        coef,intercept=params[k]
        return 1/(1+math.exp(-float(np.dot(coef,x)+intercept)))
    def forecasts(x,sa,sb,cl):
        win=predict('winner',x) if cl is None else cl
        return win, win*predict('sub',sa),(1-win)*predict('sub',sb)
    scores={'limited':[],'submission':[]}
    for r in rows:
        if r['day']<'2023':continue
        cl=cl_test.get(r['id'])
        win,a,b=forecasts(r['x'],r['sa'],r['sb'],cl)
        if cl is None:scores['limited'].append((win,r['y']))
        scores['submission'].append((a+b,r['sub']))
    for f in card:
        p=f.get('props')
        if not p:continue
        a,b=f['a'],f['b']; args=[f['division'],p['rounds']]
        w,sa,sb=forecasts(winner_inputs(a,b),submission_inputs(a,b,*args),submission_inputs(b,a,*args),f['p'])
        f['limited']=w if f['p'] is None else None
        p.update(subA=sa,subB=sb,submission=sa+sb)
    def summarize(pairs):
        p,y=np.array(pairs).T
        return dict(n=len(y),brier=float(np.mean((p-y)**2)),accuracy=float(np.mean(np.where(p==.5,.5,(p>.5)==y))))
    return {k:summarize(v) for k,v in scores.items()}
