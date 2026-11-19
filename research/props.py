"""Time-ordered full-distance and KO/TKO/DQ models for standard UFC bouts."""
from collections import defaultdict, Counter
from pathlib import Path
import csv
import json
import math
import numpy as np
from sklearn.linear_model import LogisticRegression
from identity import fighter_key

DIVISIONS = ('flyweight','bantamweight','featherweight','lightweight','welterweight','middleweight','light heavyweight','heavyweight',"women's strawweight","women's flyweight","women's bantamweight","women's featherweight")
WEIGHTS = Path(__file__).with_name('prop-weights-v1.json')
def division(text):
    return text.lower().replace('ufc interim ','').replace('ufc ','').replace(' title bout','').replace(' bout','').strip()

def labels(row):
    fmt = row['TIME FORMAT'].strip()
    scheduled = {'3 Rnd (5-5-5)':3, '5 Rnd (5-5-5-5-5)':5}.get(fmt)
    method = row['METHOD'].strip()
    outcome = row['OUTCOME'].strip()
    if not scheduled or outcome not in ('W/L','L/W','D/D') or method in ('Overturned','Other','Could Not Continue'):
        return None
    distance = int(int(row['ROUND']) == scheduled and row['TIME'].strip()=='5:00')
    ko = int(method in ('KO/TKO',"TKO - Doctor's Stoppage",'DQ'))
    return scheduled,distance,ko,(.5 if outcome=='D/D' else int(outcome=='W/L'))

def features(a,b,div,length):
    def summarize(s):
        n=s['n']
        return np.array([(s['distance']+2)/(n+4),(s['ko']+1.4)/(n+4),
                         (s['ko_for']+.7)/(n+4),(s['ko_against']+.7)/(n+4),
                         (s['wins']+2)/(n+4),math.log1p(n)/3])
    x,y=summarize(a),summarize(b)
    context=[float(div==d) for d in DIVISIONS]+[int(length==5)]
    symmetric=context+list((x+y)/2)+list(abs(x-y))
    return symmetric, list(x-y)

def fit_model(examples,key,label,intercept):
    lr=LogisticRegression(C=1,max_iter=1000,fit_intercept=intercept)
    lr.fit([r[key] for r in examples],[r[label] for r in examples])
    return {'coef':lr.coef_[0].tolist(),'intercept':float(lr.intercept_[0])}
def predict(model,x):
    return 1/(1+math.exp(-float(np.dot(model['coef'],x)+model['intercept'])))
def estimate(models,x,asym):
    k=predict(models['ko'],x)
    a=k*predict(models['side'],asym)
    return {'distance':predict(models['distance'],x),'ko':k,'koA':a,'koB':k-a}

def build_props(data_dir,events,cutoff,card,cardrows,ambiguous):
    histories=defaultdict(Counter)
    days=defaultdict(list)
    seen=set()
    with (data_dir/'greco.csv').open() as file:
        for row in csv.DictReader(file):
            day=events.get(row['EVENT'].strip()); div=division(row['WEIGHTCLASS'])
            lab=labels(row)
            if not day or day>=cutoff or not lab or div not in DIVISIONS or row['URL'] in seen:continue
            seen.add(row['URL'])
            a,b=map(fighter_key,row['BOUT'].split(' vs. '))
            if a in ambiguous or b in ambiguous or a==b:continue
            days[day].append((a,b,div,lab))
    examples=[]
    for day,bouts in sorted(days.items()):
        updates=[]
        for a,b,div,(length,d,k,won) in bouts:
            sa,sb=histories[a],histories[b]
            x,asym=features(sa,sb,div,length)
            if day.year>=2005:
                examples.append(dict(date=day.isoformat(),x=x,side=asym,div=div,length=length,distance=d,ko=k,won=int(won),thin=min(sa['n'],sb['n'])<2))
            updates.extend([(a,Counter(n=1,distance=d,ko=k,ko_for=k*won,ko_against=k*(1-won),wins=won)),
                            (b,Counter(n=1,distance=d,ko=k,ko_for=k*(1-won),ko_against=k*won,wins=1-won))])
        for name,change in updates: histories[name].update(change)
    train=[r for r in examples if r['date']<'2023']
    if WEIGHTS.exists():
        frozen=json.loads(WEIGHTS.read_text());models=frozen['models']
    else:
        models={key:fit_model(train,'x',key,True) for key in ['distance','ko']}
        models['side']=fit_model([r for r in train if r['ko']],'side','won',False)
        test=[r for r in examples if r['date']>='2023']
        cell=defaultdict(list)
        for r in train:cell[r['div'],r['length']].append(r)
        report={}
        for label in ('distance','ko','koSide'):
            errors=[];base=[];hits=[];thin=[]
            for r in test:
                peers=cell[r['div'],r['length']]
                key='ko' if label=='koSide' else label
                baseline=(sum(v[key] for v in peers)+2)/(len(peers)+4)
                preds=estimate(models,r['x'],r['side'])
                if label=='koSide' and r['thin']:continue
                pairs=[(preds['koA'],r['ko']*r['won']),(preds['koB'],r['ko']*(1-r['won']))] if label=='koSide' else [(preds[key],r[key])]
                for prob,actual in pairs:
                    errors.append((prob-actual)**2);base.append(((baseline/2 if label=='koSide' else baseline)-actual)**2)
                    hits.append((prob>=.5)==actual)
                    if r['thin']:thin.append(errors[-1])
            report[label]=dict(n=len(errors),brier=float(np.mean(errors)),baseline=float(np.mean(base)),accuracy=float(np.mean(hits)),thinBrier=float(np.mean(thin)) if thin else None,thinN=len(thin))
        frozen=dict(models=models,report=report,start=test[0]['date'],end=test[-1]['date'])
        WEIGHTS.write_text(json.dumps(frozen,indent=2))
    for f,row in zip(card,cardrows):
        a,b=[histories[fighter_key(s['name'])] for s in (f['a'],f['b'])]
        length=int(row['scheduled_rounds']) if row.get('scheduled_rounds') else None
        div=division(f['division'])
        if length not in (3,5) or div not in DIVISIONS:continue
        x,asym=features(a,b,div,length)
        rates=estimate(models,x,asym)
        thin=min(a['n'],b['n'])<2
        if thin:rates['koA']=rates['koB']=None
        f['props']=dict(**rates,rounds=length,thin=thin,bouts=[a['n'],b['n']])
    return {k:frozen[k] for k in ['report','start','end']}
