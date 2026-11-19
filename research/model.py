"""Build from the five pinned input CSVs in the directory supplied on the command line."""
import gzip
import csv, datetime as dt, hashlib, json, math, re, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from identity import fighter_key as norm
from props import build_props
from limited import winner_inputs, submission_inputs, supplement
import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(sys.argv[1])
def rows(path):
    with path.open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))
def clock(value):
    m,s = value.split(':')
    return int(m)*60+int(s)
def prob(line):
    return 100/(100+line) if line>0 else -line/(100-line)
def pair(value):
    return list(map(int,value.strip().split(' of ')))
def now_age(dob, date):
    return date.year-dob.year-((date.month,date.day)<(dob.month,dob.day))
def mean(x):
    return float(np.mean(x)) if len(x) else None

event=json.loads((ROOT/"research/event.json").read_text())
cutoff=dt.date.fromisoformat(event["date"])
events = {v['EVENT'].strip():dt.datetime.strptime(v['DATE'],'%B %d, %Y').date() for v in rows(DATA/'events.csv') if v.get('DATE')}
profiles={}
ambiguous=set()
for v in rows(DATA/'bios.csv'):
    k=norm(v['FIGHTER'])
    if k in profiles and profiles[k]['URL']!=v['URL']: ambiguous.add(k)
    profiles[k]=v
rounds=defaultdict(list)
for v in rows(DATA/'rounds.csv'):
    rounds[v['EVENT'].strip(),v['BOUT'].strip(),norm(v['FIGHTER'])].append(v)
odds={}
for r in rows(DATA/'tidy.csv'):
    if r['winner'] not in ('Red','Blue'): continue
    try: a,b=float(r['r_odds']),float(r['b_odds'])
    except ValueError: continue
    if not all(math.isfinite(i) and abs(i)>=100 for i in (a,b)): continue
    k,l=norm(r['r_fighter']),norm(r['b_fighter'])
    odds[r['date'],k,l]=[a,b]; odds[r['date'],l,k]=[b,a]
class Fighter:
    def __init__(self):
        self.elo=1500
        self.hist=[]
        self.stats=Counter()
    def snapshot(self,name,date):
        k=norm(name); bio=profiles.get(k,{})
        try: age=now_age(dt.datetime.strptime(bio['DOB'],'%b %d, %Y').date(),date)
        except (ValueError,KeyError): age=None
        s=self.stats; mins=s['secs']/60
        def rate(key,mult=1): return round(s[key]*mult/mins,2) if mins else None
        def pct(key,attempts): return round(s[key]/s[attempts],4) if s[attempts] else None
        return dict(name=name,age=age,stance=bio.get('STANCE') or 'Unknown',elo=round(self.elo,2),history=self.hist[-5:],
            total=len(self.hist),minutes=round(mins,1),sl=rate('sl'),sa=rate('sa'),td=rate('td',15),tda=rate('tda',15),
            tdd=pct('stuff','opp_tda'),sub=rate('sub',15),dist=pct('distance','sl'),kd=rate('kd',15),
            division=self.hist[-1]['division'] if self.hist else None)
fighters=defaultdict(Fighter)
def setup(a,b):
    if a['age'] is None or b['age'] is None or min(a['total'],b['total'])<3: return False
    return a['age']>=35 and a['age']-b['age']>=5 and sum(h['win']==0 for h in a['history'][-3:])>=2 and sum(h['win']==1 for h in b['history'][-3:])>=2
def eligible(a,b):
    return all(s['total']>=2 and s['minutes']>=10 and s['age'] is not None for s in (a,b))
def features(a,b):
    def values(s,opp):
        return np.array([s['elo']/100,s['age']/5,max(0,s['age']-32)/5, math.log1p(s['total']),
        np.mean([r['win'] for r in s['history'][-3:]]), s['sl']-s['sa'], s['td'], s['sub'], s['kd'],
        s['tda']*(1-(opp['tdd'] if opp['tdd'] is not None else .6))])
    return values(a,b)-values(b,a)
bouts_by_day=defaultdict(list)
for v in rows(DATA/'greco.csv'):
    day=events.get(v['EVENT'].strip())
    if day and v['OUTCOME'].strip() in ('W/L','L/W') and v['TIME FORMAT'].strip() in ('3 Rnd (5-5-5)','5 Rnd (5-5-5-5-5)') and day<cutoff:
        bouts_by_day[day].append(v)
samples=[]; supplement_rows=[]; seen=set()
for day,bouts in sorted(bouts_by_day.items()):
    updates=[]
    for v in bouts:
        if v['URL'] in seen: continue
        seen.add(v['URL'])
        name1,name2=map(str.strip,v['BOUT'].split(' vs. '))
        k,l=norm(name1),norm(name2)
        if k in ambiguous or l in ambiguous or k==l: continue
        a,b=fighters[k].snapshot(name1,day),fighters[l].snapshot(name2,day)
        y=int(v['OUTCOME'].strip()=='W/L')
        if day.year>=2005:
            args=[v['WEIGHTCLASS'],int(v['TIME FORMAT'].strip()[0])]
            supplement_rows.append(dict(id=v['URL'].strip().rsplit('/',1)[-1],day=day.isoformat(),x=winner_inputs(a,b),sa=submission_inputs(a,b,*args),sb=submission_inputs(b,a,*args),y=y,sub=int(v['METHOD'].strip()=='Submission')))
        if eligible(a,b) and day.year>=2005:
            samples.append(dict(fight_id=v["URL"].strip().rsplit("/",1)[-1],keys=(k,l),day=day.isoformat(),x=features(a,b),y=y,odds=odds.get((day.isoformat(),k,l)),vet=1 if setup(a,b) else 2 if setup(b,a) else 0))
        ev=v['EVENT'].strip(); bout=v['BOUT'].strip()
        dur=(int(v['ROUND'])-1)*300+clock(v['TIME'].strip())
        sides=[rounds[ev,bout,key] for key in (k,l)]; stats=[Counter(),Counter()]
        if dur and all(len(side)==int(v['ROUND']) for side in sides):
            try:
                for i,side in enumerate(sides):
                    s=stats[i]
                    for row in side:
                        sl,_=pair(row['SIG.STR.']); td,att=pair(row['TD']); ds,_=pair(row['DISTANCE'])
                        s.update(sl=sl,td=td,tda=att,sub=int(float(row['SUB.ATT'])),kd=int(float(row['KD'])),distance=ds)
                    s['secs']=dur
                for i in (0,1):
                    o=stats[1-i]; stats[i].update(sa=o['sl'],opp_tda=o['tda'],stuff=o['tda']-o['td'])
            except (ValueError,TypeError): stats=[Counter(),Counter()]
        delta=32*(y-1/(1+10**((b['elo']-a['elo'])/400)))
        for key,opp,win,change,st in [(k,name2,y,delta,stats[0]),(l,name1,1-y,-delta,stats[1])]:
            updates.append((key,change,st,dict(date=day.isoformat(),opponent=opp,win=win,method=v['METHOD'].strip(),division=v['WEIGHTCLASS'].replace(' Bout','').strip(),url=v['URL'].strip().replace('http:','https:'))))
    for key,change,st,h in updates:
        f=fighters[key];f.elo+=change;f.stats.update(st);f.hist.append(h)
train=[r for r in samples if r['day']<'2023-01-01']
test=[r for r in samples if r['day']>='2023-01-01']
model=LogisticRegression(C=1,fit_intercept=False,max_iter=1000).fit(np.stack([r['x'] for r in train]),[r['y'] for r in train])
weights_path=ROOT/'research/weights-v1.json'
if weights_path.exists():
    model.coef_[0]=np.array(json.loads(weights_path.read_text()))
else:
    weights_path.write_text(json.dumps(model.coef_[0].tolist()))
def predict(x):return float(model.predict_proba([x])[0,1])
def scores(p,y):
    p=np.array(p);y=np.array(y)
    return dict(n=len(y),accuracy=mean(np.where(p==.5,.5,(p>.5)==y)),brier=mean((p-y)**2),logloss=mean(-y*np.log(p)-(1-y)*np.log(1-p)))
for r in test:
    r['p']=predict(r['x'])
    if r['odds']:
        a,b=map(prob,r['odds']); r['m']=a/(a+b)
matched=[r for r in test if 'm' in r]
def score(rows,key):return scores([r[key] for r in rows],[r['y'] for r in rows])
def cohort(rows,rule):
    results=[]
    for r in rows:
        idx=rule(r)
        if idx is None: continue
        results.append((r['y'] if idx==0 else 1-r['y'],r['m'] if idx==0 else 1-r['m'],prob(r['odds'][idx])))
    return dict(n=len(results),wins=sum(i[0] for i in results),actual=mean([i[0] for i in results]),market=mean([i[1] for i in results]),breakEven=mean([i[2] for i in results]))
def underdog(r):
    for i,(p,m,line) in enumerate(zip((r['p'],1-r['p']),(r['m'],1-r['m']),r['odds'])):
        if line>=200 and .4<=p<=.6 and p-m>=.08: return i
    return None
cal=[]
for lo,hi in [(0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,1.001)]:
    group=[r for r in test if lo<=max(r['p'],1-r['p'])<hi]
    cal.append(dict(lo=lo,hi=min(hi,1),n=len(group),forecast=mean([max(r['p'],1-r['p']) for r in group]),actual=mean([int((r['p']>.5)==r['y']) for r in group])))
report=dict(train=len(train),test=score(test,'p'),paired=score(matched,'p'),market=score(matched,'m'),years=[test[0]['day'],test[-1]['day']],pairedEnd=matched[-1]['day'],vet=cohort(matched,lambda r: 1 if r['vet']==1 else 0 if r['vet']==2 else None),longshot=cohort(matched,underdog),cal=cal)
card=[]
for i,r in enumerate(rows(ROOT/'research/card.csv')):
    a,b=[fighters[norm(n)].snapshot(n,cutoff) for n in (r['fighter_a'],r['fighter_b'])]
    card.append(dict(a=a,b=b,division=r['division'],lines=[int(r[c]) if r[c] else None for c in ('odds_a','odds_b')],p=predict(features(a,b)) if eligible(a,b) else None,vet=setup(a,b) or setup(b,a),divisionChange=any(s['division'] and r['division'].lower()!=s['division'].lower() for s in (a,b))))
report_path=ROOT/'research/report-v1.json'
if report_path.exists():
    report=json.loads(report_path.read_text())
else:
    report_path.write_text(json.dumps(report,indent=2))
out=dict(report=report,card=card,event=event,model='CL-1',statsThrough=max(bouts_by_day).isoformat())
out['propValidation']=build_props(DATA,events,cutoff,card,rows(ROOT/'research/card.csv'),ambiguous)
out['supplementValidation']=supplement(supplement_rows,card,{r['fight_id']:r['p'] for r in test})
closing_path=ROOT/'research/inputs/closing-market.json.gz'
if closing_path.exists():
    with gzip.open(closing_path,'rt') as f: closes=json.load(f)
    matched_close=[]
    for r in test:
        row=closes.get(r['fight_id'])
        if not row or r['day']!=row[0]:continue
        if r['keys']==(row[1],row[2]):closing=row[3]
        elif r['keys']==(row[2],row[1]):closing=1-row[3]
        else:continue
        matched_close.append(dict(**r,closing=closing))
    if matched_close:
        out['closingTest']={'model':score(matched_close,'p'),'market':score(matched_close,'closing'),
                            'start':matched_close[0]['day'],'end':matched_close[-1]['day']}
(ROOT/'dist/data.json').write_text(json.dumps(out,allow_nan=False,separators=(',',':')))
print(json.dumps(report,indent=2))
for r in card:print(r['a']['name'],r['b']['name'],r['p'],r['a']['total'],r['b']['total'],r['vet'])
