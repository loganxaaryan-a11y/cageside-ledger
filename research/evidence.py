"""Import public fight archives and join source observations to an official card."""
import argparse, csv, datetime as dt, gzip, hashlib, io, json, math, os, subprocess, tempfile, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from identity import fighter_key

ROOT=Path(__file__).resolve().parents[1]
BAIR='https://raw.githubusercontent.com/nlbair/ufc-data/main/data/'
ALMANAC='https://raw.githubusercontent.com/Sam-Armstrong/UFC-Almanac/main/data/'
KAGGLE='https://www.kaggle.com/api/v1/datasets/download/'
URLS={'wide':BAIR+'ufc_all_fights_wide.csv','judges':BAIR+'ufc_judge_rounds.csv','almanac':ALMANAC+'FighterData.csv','almanacResults':ALMANAC+'FightResults.csv','almanacStats':ALMANAC+'FightStats.csv','daily2':KAGGLE+'jerzyszocik/ufc-betting-odds-daily-dataset','master2':KAGGLE+'valihameed/ufc-stats','gap':'https://theoddsgap.com/api/odds-history.csv?sport=mma_mixed_martial_arts'}
MEMBERS={'daily2':'UFC_betting_odds.csv','master2':'ufc-master.csv'}
REQUIRED={'wide':'fight_id f1_name f2_name f1_close_prob_novig event_date','judges':'fight_id primary_name judge_name round','almanac':'Name Wins Losses Height Reach','almanacResults':'Date Result Method','almanacStats':'Name Date Time Knockdowns','daily2':'event_date adding_date source fighter_1 fighter_2 odds_1 odds_2','master2':'RedFighter BlueFighter RedOdds BlueOdds Date','gap':'close_ts earliest_ts close_american_odds market book game_id'}
def name(s):
    k=fighter_key(s)
    return {'seokhyunko':'seokhyeonko','gabriellourenco':'gabriellorenco'}.get(k,k)
def pair(a,b):return tuple(sorted((name(a),name(b))))
def records(p,k):
    raw=p.read_bytes()
    if k in MEMBERS:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:raw=z.read(MEMBERS[k])
    rd=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not set(REQUIRED[k].split()).issubset(rd.fieldnames or []):raise ValueError(k+' schema mismatch')
    rows=list(rd)
    if not rows or not rd.fieldnames or len(rd.fieldnames)<3:raise ValueError('Empty or invalid '+k)
    return rows
def run(cache,download):
    event=json.loads((ROOT/'research/event.json').read_text())
    with (ROOT/'research/card.csv').open() as f: card=list(csv.DictReader(f))
    today=dt.date.fromisoformat(event['date']);now=dt.datetime.now(dt.timezone.utc)
    byname={name(r[col]):r[col] for r in card for col in ('fighter_a','fighter_b')}
    pairs={pair(r['fighter_a'],r['fighter_b']):r for r in card}
    ids={};stats={}; fighters=defaultdict(dict); books=defaultdict(dict); gap=[]; judge_count=Counter()
    for k,url in URLS.items():
        path=cache/k
        if download:
            stage=path.with_suffix('.part')
            subprocess.run(['curl','-fLsS','--retry','1','--connect-timeout','12','--max-time','120',url,'-o',str(stage)],check=True)
            rows=records(stage,k);os.replace(stage,path)
        else:rows=records(path,k)
        stats[k]=dict(count=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),url=url)
        if k=='wide':
            for r in rows:
                a,b=name(r['f1_name']),name(r['f2_name'])
                if r['event_date']>=event['date']:continue
                p=r['f1_close_prob_novig']
                if p and 0<float(p)<1:ids[r['fight_id']]=[r['event_date'],a,b,float(p)]
                for ix,n in [(1,a),(2,b)]:
                    if n not in byname:continue
                    profile=fighters[byname[n]];prior=profile.get('bair')
                    if not prior or prior['date']<r['event_date']:
                        profile['bair']=dict(date=r['event_date'],rank=r[f'f{ix}_rank'] or None,board=r[f'f{ix}_rank_board_date'],opponent=r[f'f{3-ix}_name'])
        if k=='judges':
            for r in rows:
                if r['event_date']<event['date']:
                    for field in ('primary_name','opponent_name'):judge_count[name(r[field])]+=1
        if k=='almanac':
            for r in rows:
                n=name(r['Name'])
                if n in byname:fighters[byname[n]]['tape']={col:r[col] for col in ['Height','Reach','Wins','Losses']}
        if k=='master2':
            stats[k]['through']=max(r['Date'] for r in rows)
            for r in rows:
                if r['Date']>=event['date']:continue
                for side,other in [('Red','Blue'),('Blue','Red')]:
                    n=name(r[side+'Fighter'])
                    if n not in byname:continue
                    profile=fighters[byname[n]];prior=profile.get('master')
                    if not prior or prior['date']<r['Date']:profile['master']=dict(date=r['Date'],opponent=r[other+'Fighter'],price=r[side+'Odds'])
        if k=='daily2':
            for r in rows:
                if r['event_date'] not in (event['date'],(today+dt.timedelta(days=1)).isoformat()):continue
                key=pair(r['fighter_1'],r['fighter_2']);bout=pairs.get(key)
                if not bout or not r['source']:continue
                try:
                    ts=dt.datetime.fromisoformat(r['adding_date'].replace('Z','+00:00'))
                    if ts.tzinfo is None or ts>now:continue
                    vals=[float(r[c]) for c in ('odds_1','odds_2')]
                    if not all(math.isfinite(v) and v>1 for v in vals):continue
                except ValueError:continue
                if name(bout['fighter_a'])!=name(r['fighter_1']):vals.reverse()
                prices=books[bout['fighter_a']+'|'+bout['fighter_b']]
                bk=(r['source'],r['region']);prev=prices.get(bk)
                if not prev or ts.isoformat()>prev['at']:prices[bk]=dict(book=bk[0],region=bk[1],at=ts.isoformat(),prices=vals)
        if k=='gap':
            for r in rows:
                if r['market']=='ml' and r['close_ts'] and r['close_american_odds'] and r['earliest_american_odds']:
                    gap.append({key:r[key] for key in ['away','home','side','book','earliest_american_odds','close_american_odds','close_ts','commence_time']})
    for n,label in byname.items():fighters[label]['judgeRows']=judge_count[n]
    output=dict(event=event['id'],sources=stats,fighters=fighters,books={k:sorted(src.values(),key=lambda x:(x['book'],x['region'])) for k,src in books.items()},gap=gap,closingCount=len(ids))
    (ROOT/'research/inputs/closing-market.json.gz').write_bytes(gzip.compress(json.dumps(ids,separators=(',',':')).encode(),mtime=0))
    with (ROOT/'dist/closing-sample.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['away','home','side','book','earliest_american_odds','close_american_odds','close_ts','commence_time']);w.writeheader();w.writerows(gap)
    (ROOT/'dist/evidence.json').write_text(json.dumps(output,allow_nan=False,separators=(',',':')))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('cache',type=Path);ap.add_argument('--cached',action='store_true')
    args=ap.parse_args();args.cache.mkdir(parents=True,exist_ok=True);run(args.cache,not args.cached)
