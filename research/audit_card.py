"""Build one canonical post-card audit from the last saved pre-event snapshot."""
import csv
import json
import math
import sys
from datetime import datetime, time, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
event_id = sys.argv[1]
index = json.loads((DIST / "journal/index.json").read_text())
archive = json.loads((DIST / "results.json").read_text())[event_id]
cutoff = (
    datetime.fromisoformat(archive["firstBoutAt"].replace("Z", "+00:00"))
    if archive.get("firstBoutAt")
    else datetime.combine(datetime.fromisoformat(archive["date"]).date(), time.max, timezone.utc)
)
eligible = [
    row for row in index
    if row["id"] == event_id
    and datetime.fromisoformat(row["asOf"].replace("Z", "+00:00")) <= cutoff
]
snapshot = max(eligible, key=lambda row: row["asOf"])
with (DIST / snapshot["file"]).open() as handle:
    forecasts = {
        frozenset((row["fighter_a"], row["fighter_b"])): row
        for row in csv.DictReader(handle)
    }

def number(value):
    return float(value) if value not in (None, "") else None

outcomes = []
pending = []
void = []
for result in archive["bouts"].values():
    row = forecasts.get(frozenset((result["a"], result["b"])))
    if not row:
        pending.append({"matchup": [result["a"], result["b"]], "reason": "No saved forecast"})
        continue
    p_a = number(row["p_a"])
    limited = number(row["p_limited"])
    p = p_a if p_a is not None else limited
    tier = "CL-1" if p_a is not None else "Limited history"
    confidence = max(p, 1 - p) if p is not None else None
    pick = None if confidence is None or confidence < .51 else (
        row["fighter_a"] if p > .5 else row["fighter_b"]
    )
    if result.get("status") == "void" or not result.get("winner"):
        void.append({
            "matchup": [row["fighter_a"], row["fighter_b"]],
            "reason": result.get("method") or "No decisive result",
            "issued_probability": confidence,
            "tier": tier,
        })
        continue
    lines = [number(row["line_a"]), number(row["line_b"])]
    favorite = None
    if all(line is not None for line in lines):
        favorite = row["fighter_a"] if lines[0] < lines[1] else row["fighter_b"]
    outcomes.append({
        "matchup": [row["fighter_a"], row["fighter_b"]],
        "tier": tier,
        "pick": pick,
        "confidence": confidence,
        "winner": result["winner"],
        "method": result["method"],
        "favorite": favorite,
        "favorite_won": favorite == result["winner"] if favorite else None,
        "p_distance": number(row["p_distance"]),
        "p_ko": number(row["p_ko"]),
        "p_submission": number(row["p_submission"]),
    })

def tier_summary(name):
    settled = [row for row in outcomes if row["tier"] == name]
    picks = [row for row in settled if row["pick"]]
    return {
        "settled": len(settled),
        "picks": len(picks),
        "correct": sum(row["pick"] == row["winner"] for row in picks),
        "tossups": len(settled) - len(picks),
    }

def surprise(key, actual_method):
    rows = [
        row for row in outcomes
        if row[key] is not None and row["method"] == actual_method
    ]
    return min(rows, key=lambda row: row[key]) if rows else None

matched = [row for row in outcomes if row["favorite"]]

def probability_metrics(probabilities, actual):
    if not probabilities:
        return {"count": 0, "brier": None, "log_loss": None}
    clipped = [min(max(p, 1e-15), 1 - 1e-15) for p in probabilities]
    return {
        "count": len(actual),
        "brier": sum((p-y)**2 for p,y in zip(clipped, actual)) / len(actual),
        "log_loss": -sum(y*math.log(p)+(1-y)*math.log(1-p) for p,y in zip(clipped, actual)) / len(actual),
    }

# The challenger is scored only from an immutable snapshot recorded before the
# official first bout.  Missing snapshots stay missing; never reconstruct them.
shadow_files = []
for path in (DIST / "journal" / "challengers").glob(f"{event_id}-*.json"):
    snapshot_time = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    try:
        candidate = json.loads(path.read_text())
        snapshot_time = datetime.fromisoformat(candidate.get("recordedAt", "").replace("Z", "+00:00"))
    except (ValueError, TypeError, json.JSONDecodeError):
        continue
    if snapshot_time < cutoff:
        shadow_files.append((snapshot_time, path, candidate))
shadow_comparison = None
if shadow_files:
    _, shadow_path, shadow = max(shadow_files, key=lambda item: item[0])
    by_pair = {frozenset((row["a"], row["b"])): row for row in shadow["bouts"]}
    cl1, challenger, actual = [], [], []
    for row in outcomes:
        saved = by_pair.get(frozenset(row["matchup"]))
        if not saved or row["winner"] not in row["matchup"]:
            continue
        a = saved["a"]
        y = int(row["winner"] == a)
        cl1.append(float(saved["cl1"]))
        challenger.append(float(saved["shadow"]))
        actual.append(y)
    shadow_comparison = {
        "snapshot": str(shadow_path.relative_to(DIST)),
        "recorded_at": shadow.get("recordedAt"),
        "identical_decisive_bouts": len(actual),
        "CL-1": probability_metrics(cl1, actual),
        "Recent striking v1": probability_metrics(challenger, actual),
    }
audit = {
    "event": event_id,
    "snapshot": snapshot["file"],
    "snapshot_as_of": snapshot["asOf"],
    "scoring_rule": "Each matchup once from the last saved snapshot before the card; 50-51% is a toss-up.",
    "summary": {
        "CL-1": tier_summary("CL-1"),
        "Limited history": tier_summary("Limited history"),
        "same_book_favorites": {
            "matched": len(matched),
            "wins": sum(row["favorite_won"] for row in matched),
        },
        "pending": len(pending),
        "void": len(void),
    },
    "misses": [
        row for row in outcomes
        if row["pick"] and row["pick"] != row["winner"]
    ],
    "largest_finish_surprises": {
        "distance": surprise("p_distance", "Decision"),
        "KO/TKO": surprise("p_ko", "KO/TKO"),
        "submission": surprise("p_submission", "Submission"),
    },
    "challenger_comparison": shadow_comparison,
    "outcomes": outcomes,
    "pending": pending,
    "void": void,
    "verified_data_faults": archive.get("verified_data_faults", []),
}
(DIST / "journal" / f"{event_id}-audit.json").write_text(
    json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
)
print(json.dumps(audit["summary"], indent=2))
