"""Pre-fight diagnostics and frozen probability challengers. Never replace an issued pick."""
import datetime as dt
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit

from identity import fighter_key
from props import DIVISIONS, division, estimate, features, labels

HERE = Path(__file__).resolve().parent
FEATURES = ['opponent_adjusted_striking', 'recent_stoppages', 'layoff', 'wrestling_exposure']
WINDOWS = [('development', '2023', '2025'), ('later', '2025', '2026-11-01')]


class History:
    def __init__(self):
        self.record = Counter()
        self.last = []
        self.performances = []
        self.totals = Counter()

    def signals(self, opponent, day):
        recent = self.last[-3:]
        losses = sum(loss for _, loss, _ in recent)
        finishes = sum(win for _, _, win in opponent.last[-3:])
        gap = (day - recent[-1][0]).days if recent else 0
        # Ten minutes of shrinkage towards an average residual performance.
        tech = self.performances[-3:]
        adjusted = sum(x for x, _ in tech) / (10 + sum(m for _, m in tech))
        # Opponent's attempt rate, weighted up when defense has rarely been tested.
        pressure = 15 * opponent.totals['attempts'] / (15 + opponent.totals['minutes'])
        exposure = pressure / math.sqrt(1 + self.totals['faced'])
        return np.array([adjusted, losses * (1 + finishes / 3),
                         math.log1p(max(0, gap - 365) / 365), exposure])


def metrics(prob, actual):
    p, y = np.asarray(prob), np.asarray(actual)
    return dict(n=len(y), accuracy=float(np.mean((p >= .5) == y)),
                brier=float(np.mean((p-y)**2)),
                logloss=float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p))),
                mean_probability=float(p.mean()), observed=float(y.mean()))


def coefficient(p, x, y):
    offset = logit(p)
    def objective(w):
        logits = offset + x*w[0]
        return np.sum(np.logaddexp(0, logits)-y*logits) + .5*w[0]**2
    result = minimize(objective, [0.], method='BFGS', tol=1e-5)
    if not result.success:
        raise ValueError(result.message)
    return float(result.x[0])


def evaluate(rows, names):
    days = np.array([r[0] for r in rows])
    p = np.array([r[1] for r in rows])
    y = np.array([r[2] for r in rows])
    x = np.array([r[3] for r in rows])
    train = days < '2023'
    weights, report = {}, {}
    candidates = {'baseline': p}
    for i, name in enumerate(names):
        w = coefficient(p[train], x[train,i], y[train])
        weights[name] = w
        candidates[name] = expit(logit(p) + w*x[:,i])
    for window, start, stop in WINDOWS:
        mask = (days >= start) & (days < stop)
        report[window] = {name:metrics(v[mask], y[mask]) for name,v in candidates.items()}
    return weights, report


def replay(data, read, events, rounds, cutoff, ambiguous, baseline):
    # Baseline probabilities come directly from the frozen CL-1 engine.
    histories = defaultdict(History)
    winner, finish, ko_side = [], [], []
    past = defaultdict(list)
    seen = set()
    for row in read(data/'greco.csv'):
        day = events.get(row['EVENT'].strip())
        div = division(row['WEIGHTCLASS'])
        lab = labels(row)
        if not day or day >= cutoff or not lab or div not in DIVISIONS:
            continue
        names = tuple(map(fighter_key, row['BOUT'].split(' vs. ')))
        uid = row['URL'].strip()
        if len(set(names)) != 2 or ambiguous.intersection(names) or uid in seen:
            continue
        seen.add(uid)
        past[day].append((row,names,div,lab))
    frozen = json.loads((HERE/'prop-weights-v1.json').read_text())['models']
    for day, fights in sorted(past.items()):
        updates = []
        for row, names, div, (length, distance, k, won) in fights:
            a,b = (histories[n] for n in names)
            diff = a.signals(b,day) - b.signals(a,day)
            uid = row['URL'].strip().split('/')[-1]
            if uid in baseline:
                winner.append((day.isoformat(), baseline[uid], int(won), diff))
            if baseline and day.year >= 2005:
                sym, asym = features(a.record,b.record,div,length)
                rates = estimate(frozen,sym,asym)
                vulnerability = a.signals(b,day)[1] + b.signals(a,day)[1]
                finish.append((day.isoformat(),rates['ko'],k,[vulnerability]))
                if min(a.record['n'],b.record['n']) >= 2 and won != .5:
                    ko_side.append((day.isoformat(), rates['ko'], rates['koA']/rates['ko'], k, int(won), diff[1]))
            sides = [rounds[row['EVENT'].strip(),row['BOUT'].strip(),n] for n in names]
            mins, sec = map(int,row['TIME'].split(':'))
            duration = (int(row['ROUND'])-1)*5 + mins + sec/60
            stats = []
            if duration and all(len(s)==int(row['ROUND']) for s in sides):
                try:
                    for side in sides:
                        stats.append((sum(int(v['SIG.STR.'].split(' of ')[0]) for v in side),
                                      sum(int(v['TD'].split(' of ')[1]) for v in side)))
                except (ValueError, IndexError):
                    stats = []
            for i,(s,o,outcome) in enumerate(((a,b,won),(b,a,1-won))):
                totals, performance = Counter(), None
                if len(stats)==2:
                    landed, attempts = stats[i]
                    absorbed, faced = stats[1-i]
                    totals.update(landed=landed, absorbed=absorbed, minutes=duration, attempts=attempts, faced=faced)
                    if o.totals['minutes']:
                        allowed = (o.totals['absorbed']-o.totals['landed'])/o.totals['minutes']
                        performance = (landed-absorbed-allowed*duration,duration)
                # Narrow exposure signal; target retains Finish-1's KO/TKO/DQ definition.
                stoppage = row['METHOD'].strip()=='KO/TKO'
                updates.append((s, Counter(n=1,distance=distance,ko=k,ko_for=k*outcome,
                                           ko_against=k*(1-outcome),wins=outcome),
                                (day,stoppage and outcome==0,stoppage and outcome==1),totals,performance))
        for s,rec,last,totals,performance in updates:
            s.record.update(rec)
            s.last.append(last)
            s.totals.update(totals)
            if performance is not None:
                s.performances.append(performance)
    return histories, winner, finish, ko_side


def evaluate_ko_side(rows):
    """Fit the winning side on stoppages, then score the two joint KO probabilities on all eligible bouts."""
    train = [r for r in rows if r[0]<'2023' and r[3]]
    _, _, side, _, y, x = zip(*train)
    weight = coefficient(np.array(side), np.array(x), np.array(y))
    report = {}
    for period, start, stop in WINDOWS:
        subset = [r for r in rows if start<=r[0]<stop]
        _, total, side, k, y, x = map(np.array,zip(*subset))
        actual = np.r_[k*y,k*(1-y)]
        report[period] = {}
        for name, side_p in [('baseline',side),('recent_stoppages',expit(logit(side)+weight*x))]:
            report[period][name] = metrics(np.r_[total*side_p,total*(1-side_p)],actual)
    return weight, report


# Frozen on Nov 20, 2026, fitted to bouts completed before 2023.
STRIKING_WEIGHT = 0.06188950044655422


def add_shadow(card, data, read, events, rounds, cutoff, ambiguous, samples, predict, study=False):
    baseline = {r['fight_id']:predict(r['x']) for r in samples} if study else {}
    histories, winner, finish, side = replay(data, read, events, rounds, cutoff, ambiguous, baseline)
    for fight in card:
        if fight['p'] is None:
            continue
        a,b = (histories[fighter_key(fight[key]['name'])] for key in ('a','b'))
        difference = a.signals(b,cutoff)[0] - b.signals(a,cutoff)[0]
        fight['strikingShadow'] = float(expit(logit(fight['p']) + STRIKING_WEIGHT*difference))
    if study:
        weights, win_report = evaluate(winner, FEATURES)
        _, finish_report = evaluate(finish, ['recent_stoppages'])
        _, side_report = evaluate_ko_side(side)
        report = dict(train_before='2023-01-01',windows=WINDOWS,weights=weights,
                      winner=win_report,finish=finish_report,directional_finish=side_report)
        for name, lo, hi in WINDOWS:
            band = []
            for day,p,y,x in winner:
                if lo<=day<hi:
                    value = float(expit(logit(p)+STRIKING_WEIGHT*x[0]))
                    if .7 <= max(value,1-value) < .8:
                        band.append((max(value,1-value), (value>.5)==y))
            if band:
                ps, ys = zip(*band)
                report.setdefault('shadow_70_to_80',{})[name] = dict(n=len(ps),mean=float(np.mean(ps)),wins=sum(map(int,ys)))
        (HERE/'challenger-backtest.json').write_text(json.dumps(report,indent=2)+'\n')
