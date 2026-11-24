"""Archive final ESPN results alongside the last pre-event forecast for each bout."""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from identity import fighter_key

dist = Path(__file__).resolve().parents[1] / 'dist'
event = json.loads((dist / 'data.json').read_text())['event']
date = event['date'].replace('-', '')
feed = (json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else
        json.load(urlopen('https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates=' + date, timeout=25)))
path = dist / 'results.json'
archive = json.loads(path.read_text()) if path.exists() else {}
event_record = archive.setdefault(event['id'], {
    'name': event['event'],
    'date': event['date'],
    'firstBoutAt': event.get('firstBoutAt'),
    'bouts': {},
})
# Add timing metadata to older in-progress records without rewriting settled bouts.
event_record.setdefault('firstBoutAt', event.get('firstBoutAt'))
rows = event_record['bouts']
for card in feed['events']:
    cutoff = datetime.fromisoformat(card['date'].replace('Z', '+00:00'))
    forecasts = {}
    for snap in json.loads((dist / 'journal/index.json').read_text()):
        if snap['id'] != event['id'] or datetime.fromisoformat(snap['asOf'].replace('Z','+00:00')) >= cutoff:
            continue
        with (dist / snap['file']).open() as f:
            for row in csv.DictReader(f):
                pair = frozenset(fighter_key(row[k]) for k in ('fighter_a','fighter_b'))
                forecasts.setdefault(pair, row)
    for bout in card['competitions']:
        if not bout['status']['type']['completed']:
            continue
        fighters = bout['competitors']
        row = forecasts.get(frozenset(fighter_key(x['athlete']['displayName']) for x in fighters))
        if not row:
            continue
        a,b = row['fighter_a'],row['fighter_b']
        winners = [x['athlete']['displayName'] for x in fighters if x.get('winner')]
        winner = (a if fighter_key(winners[0]) == fighter_key(a) else b) if len(winners)==1 else None
        method = next((d['type']['text'].removeprefix('Unofficial Winner ') for d in bout.get('details',[]) if d['type']['text'].startswith('Unofficial Winner ')), '')
        rows[a+'|'+b] = dict(a=a,b=b,winner=winner,method={'Kotko':'KO/TKO'}.get(method,method), issued=row['issued'],
            tier='CL-1' if row['p_a'] else 'Limited history', **{k:float(row[k]) if row.get(k) else None for k in ('p_a','p_limited','p_distance','p_ko','p_submission')})
if rows:
    path.write_text(json.dumps(archive,indent=2)+'\n')
