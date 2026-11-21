"""Append a pre-event snapshot and score prior records from verified UFCStats results."""
import csv, datetime as dt, hashlib, io, json, re, sys, unicodedata
from pathlib import Path
from identity import fighter_key as norm
from props import labels
ROOT=Path(__file__).resolve().parents[1]
dest=ROOT/'dist/journal'
dest.mkdir(exist_ok=True)
data=json.loads((ROOT/'dist/data.json').read_text())
e=data['event']
assert re.fullmatch('[a-z0-9-]+',e['id'])
def csvrows(path):
    with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def content(rows,fields):
    stream=io.StringIO()
    w=csv.DictWriter(stream,fieldnames=fields)
    w.writeheader();w.writerows(rows)
    return stream.getvalue()
def write_once(path,text):
    if path.exists():
        assert path.read_bytes()==text.encode(),f'Conflicting snapshot: {path.name}'
    else:path.write_bytes(text.encode())
index_path=dest/'index.json'
index=json.loads(index_path.read_text()) if index_path.exists() else []
def record(row):
    a,b=row['a'],row['b']
    props=row.get('props',{})
    quotes=e.get('propQuotes',{})
    prices=quotes.get('lines',{}).get(a['name']+'|'+b['name'],[None,None])
    ko_prices=quotes.get('fighterKO',{}).get(a['name']+'|'+b['name'],[None,None])
    return dict(supplement_model='Supplement-1',p_limited=row.get('limited'),p_submission=props.get('submission'),p_a_sub=props.get('subA'),p_b_sub=props.get('subB'),ko_a_price=ko_prices[0],ko_b_price=ko_prices[1],prop_model='Finish-1',p_distance=props.get('distance'),p_ko=props.get('ko'),p_a_ko=props.get('koA'),p_b_ko=props.get('koB'),scheduled_rounds=props.get('rounds'),distance_yes_price=prices[0],distance_no_price=prices[1],prop_price_source=quotes.get('source') if any(prices) else None,prop_price_observed=quotes.get('observed') if any(prices) else None,model=data['model'],issued=max(e['asOf'],e.get('propAsOf',e['asOf'])),event_date=e['date'],event_id=e['id'],fighter_a=a['name'],fighter_b=b['name'],p_a=row['p'],line_a=row['lines'][0],line_b=row['lines'][1],veteran_flag=row['vet'],book=e['oddsLabel'])
records=[record(r) for r in data['card']]
fingerprint=hashlib.sha256(json.dumps([{k:v for k,v in r.items() if k!='issued'} for r in records],sort_keys=True).encode()).hexdigest()
latest=next((x for x in index if x['id']==e['id']),None)
if not latest or latest['fingerprint']!=fingerprint:
    issued=records[0]['issued']
    stamp=dt.datetime.fromisoformat(issued).strftime('%Y%m%dT%H%M%S')
    path=dest/(e['id']+'-'+stamp+'.csv')
    write_once(path,content(records,list(records[0])))
    index.insert(0,dict(id=e['id'],event=e['event'],date=e['date'],asOf=issued,file='journal/'+path.name,count=len(records),issued=sum(r['p_a'] is not None for r in records),fingerprint=fingerprint))
if len(sys.argv)>1:
    inputs=Path(sys.argv[1])
    dates={r['EVENT'].strip():dt.datetime.strptime(r['DATE'],'%B %d, %Y').date().isoformat() for r in csvrows(inputs/'events.csv') if r.get('DATE')}
    results={}
    for r in csvrows(inputs/'greco.csv'):
        names=[norm(n) for n in r['BOUT'].split(' vs. ')]
        dtkey=dates.get(r['EVENT'].strip())
        if len(names)==2:results[dtkey,tuple(sorted(names))]=(names[0],r['OUTCOME'].strip(),r['URL'].strip(),labels(r),r['METHOD'].strip())
    for x in index:
        if x.get('result') or x['date']>=dt.datetime.now(dt.timezone.utc).date().isoformat(): continue
        output=[]
        for r in csvrows(ROOT/'dist'/x['file']):
            a,b=norm(r['fighter_a']),norm(r['fighter_b'])
            res=results.get((r['event_date'],tuple(sorted((a,b)))))
            if not res:continue
            first,outcome,url,lab,method=res
            y=int((outcome=='W/L')==(first==a)) if outcome in ('W/L','L/W') else None
            p=float(r['p_a']) if r['p_a'] else None
            output.append(dict(fighter_a=r['fighter_a'],fighter_b=r['fighter_b'],winner=(r['fighter_a'] if y else r['fighter_b']) if y is not None else outcome,p_a=p,brier=(p-y)**2 if y is not None and p is not None else None,source=url))
            if 'p_distance' in r:
                # Compare like-for-like when an announced round count changes.
                match_length=bool(lab and str(lab[0])==r.get('scheduled_rounds'))
                d=lab[1] if match_length else None
                k=lab[2] if match_length else None
                sub=int(method=='Submission') if match_length and y is not None else None
                for field,observed in [('limited',y),('submission',sub),('a_sub',None if sub is None else sub*y),('b_sub',None if sub is None else sub*(1-y)),('distance',d),('ko',k),('a_ko',None if k is None else int(bool(k and y==1))),('b_ko',None if k is None else int(bool(k and y==0)))]:
                    estimate=r.get('p_'+field)
                    output[-1]['actual_'+field]=observed
                    output[-1]['brier_'+field]=(float(estimate)-observed)**2 if estimate and observed is not None else None
        if output:
            buf=content(output,list(output[0]))
            suffix=hashlib.sha256(buf.encode()).hexdigest()[:10]
            path=dest/(Path(x['file']).stem+'-results-'+suffix+'.csv')
            write_once(path,buf)
            x['scored']='journal/'+path.name
            if len(output)==x['count']:x['result']=x['scored']
index_path.write_text(json.dumps(index,indent=2))

# Freeze the experimental and official probabilities together before fight day.
# Fall back to midnight UTC when the scheduled first bout time is unavailable.
def archive_striking_shadow():
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime.fromisoformat(e.get('firstBoutAt', e['date']+'T00:00:00+00:00'))
    if start.tzinfo is None or now >= start:
        return
    rows = [dict(a=f['a']['name'], b=f['b']['name'], cl1=f['p'], shadow=f['strikingShadow'])
            for f in data['card'] if f.get('strikingShadow') is not None]
    if not rows:
        return
    snapshot = dict(model='Recent striking v1', event=e['id'], eventDate=e['date'],
                    inputAsOf=e['asOf'], bouts=rows)
    key = hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()[:20]
    folder = dest/'challengers'
    folder.mkdir(exist_ok=True)
    path = folder/(e['id']+'-'+key+'.json')
    if not path.exists():
        import os, tempfile
        snapshot['recordedAt'] = now.isoformat()
        with tempfile.NamedTemporaryFile(mode='w',dir=folder) as f:
            json.dump(snapshot,f,indent=2)
            f.write('\n')
            f.flush()
            try:
                os.link(f.name,path)
            except FileExistsError:
                pass

archive_striking_shadow()
