# Cageside Ledger: verified project context

Read this before changing models, scoring, data refreshes or the public-facing explanation.
Reviewed November 14, 2026 (America/Toronto), against source commit
`69c9c409ed27e1c7f06b2adc6ffa5d6387adb277` and published Site version 16.
This document reconstructs the checked-in implementation, not every prior conversation.

## Product and owner intent

Private UFC research dashboard: upcoming fights, winner and finish probabilities,
fighter styles and histories, market comparisons, candidate parlays, original forecast
journal, settled results, and transparent model performance. Existing work should be
continued, not rebuilt. Preserve owner-only access and original forecast records.

The owner wants genuine predictive improvements: allow no pick, coin toss and weak
lean labels; do not force a winner or method. Report pick accuracy with coverage and
skipped fights separately. Keep probability scoring across all eligible forecasts.
Never relabel historical losses using thresholds selected after the outcomes.
The owner has authorized further improvements, but this review changes documentation
only. The three parlays discussed in chat were ad hoc candidates, NOT an established,
backtested portfolio strategy. A suggested minimum price was judgment, not a fitted rule.

## Architecture and source map

- `research/model.py`: chronological UFCStats reconstruction, frozen CL-1 winner model,
  historical market comparisons and two exploratory strategy cohorts.
- `research/weights-v1.json`, `report-v1.json`: frozen winner coefficients and original
  historical report. The saved report is intentionally reused; it is not recomputed
  merely by running the refresh command.
- `research/props.py`, `prop-weights-v1.json`: Finish-1 distance and KO/TKO/DQ models.
- `research/limited.py`, `supplement-v1.json`: Supplement-1 sparse-history winner and
  conditional-submission estimates.
- `research/event.json`, `card.csv`: verified current event metadata and matchups,
  bookmaker moneylines, scheduled rounds and scouting context.
- `research/journal.py`, `dist/journal/`: immutable pre-fight snapshots, deduplication,
  separate result CSVs and index. Scouting does not enter CL-1 features.
- `research/results_board.py`, `dist/results.json`: ESPN final-result archive joined
  to the latest available forecast issued before the event cutoff.
- `research/evidence.py`, `dist/evidence.json`: supplemental archives and dated market
  evidence, separate from predictor inputs.
- `dist/audit.js`, `tests/audit.cjs`: historical pick scoring, coverage, tiers,
  pending/void status and probability scoring.
- `dist/card-home.js`, `app.js`, `parlay.js`, `source-ui.js`: dashboard views.
- `service/worker.mjs`: serves bundled assets and authenticated provider connections.
- `service/build.py`: embeds current dist assets into `dist/server/index.js`.
- `.openai/hosting.json`: existing project and R2 BUCKET binding. Preserve these.
- `research/REFRESH.md`: existing refresh procedure; read alongside this document.

## CL-1 winner model

Logistic regression, C=1, no intercept; side-A minus side-B features guarantee
complementary winner probabilities. Ten features: Elo/100, age/5, age above 32/5,
log experience, last-three win rate, significant-strike differential per minute,
takedowns/15, submission attempts/15, knockdowns/15, and takedown attempts adjusted
by opponent takedown defense (0.6 defense fallback if missing).
Elo begins at 1500, K=32. Fighter history updates are delayed until every bout on
the same date has been evaluated. Current card excludes event-day history.

Eligibility: both fighters have known age, >=2 qualifying UFC bouts, >=10 measured
minutes. Standard three/five-round decisive bouts only; ambiguous identities,
draws and no contests are excluded from CL-1. Complete round sheets supply rates.
Training examples begin in 2005 and end before 2023; later bouts are chronological
holdout observations, with earlier test-period results allowed into later histories.
This is frozen-coefficient chronological evaluation, not repeated walk-forward fitting.
Current odds, judge scores and supplemental scouting are not CL-1 predictors.

## Original strategy hypotheses and verified outcomes

1. **Veteran decline / younger opponent:** veteran age >=35, >=5-year age gap,
   veteran lost >=2 of last 3 and younger fighter won >=2 of last 3; both need >=3
   bouts and known ages. Evaluate the younger side. Saved matched cohort: 65/86
   wins (75.58%), mean no-vig market probability 70.64%, mean quoted break-even
   73.67%. Exploratory association, not proof of promotion intent or profitability.
   Mean break-even versus win rate is not a realized-return backtest.
2. **Long-odds / apparent mispricing:** American price >=+200, CL-1 probability
   40–60%, model exceeds same-book no-vig market by >=8 percentage points.
   Saved cohort: 33/150 wins (22%), mean market probability 26.04%, mean quoted
   break-even 27.16%. This screen did not demonstrate reliable predictive advantage.
3. **General winner forecasting:** original frozen report: 3,350 training bouts,
   1,234 test bouts, 63.45% accuracy, Brier .22478. Same 875 archived-odds fights:
   model 65.49% / Brier .21934; market 70.17% / .19927.
4. **Independent closing comparison:** exact fight ID, date and fighter orientation
   matches to Bair closing no-vig probabilities. 1,199 fights: CL-1 63.97%, market
   70.35%; Brier .22389 versus .20305. Closing odds are benchmark-only, not features.

Historical quote timing is incomplete. Do not call any model/market gap a validated
tradable edge. There is no checked-in realized-return or combined-parlay backtest.

## Finish-1 and Supplement-1

Finish-1 uses smoothed prior distance, KO occurrence, KO wins/losses, wins and sample
size, division and scheduled rounds. It trains before 2023 and freezes coefficients.
Distance means reaching the scheduled final bell, not simply a decision label.
KO grouping includes doctor stoppages and disqualifications; settlement must match
the sportsbook. Named-fighter KO divides the fight KO probability using a side model.
Named KO probabilities are withheld if either fighter has fewer than two prior bouts.

Saved held-out report, 1,941 fights: distance Brier .23660 versus division/length
baseline .24493; KO .20902 versus .21728. Named-KO Brier .12515 versus .12971 across
2,546 side outcomes (1,273 fights). Its 84.45% binary accuracy includes correctly
predicting that a named fighter does NOT win by KO; it is not an 84% KO-pick hit rate.

Supplement-1 supplies separately labeled sparse-history winner estimates using Elo,
age (30 fallback), smoothed recent form and experience. Saved validation: 733 fights,
60.30% accuracy, Brier .23511. Conditional submission models use prior submission
wins/losses, submission attempts, takedowns, rounds and women's-division indicator;
multiply each conditional estimate by that fighter's winner probability. Fight-level
submission Brier .14346 over 1,972 fights. High binary accuracy is not a submission
selection hit rate.

Distance, KO and submission are independent estimates, NOT a coherent mutually
exclusive distribution; their sum can differ from 100%. Do not normalize them
silently or use their largest value as a validated method pick.

## Scoring and uncertainty: implemented versus requested

Current winner cutoff is max(p,1-p) >=51%; below that is a toss-up. CL-1 and limited
history stay separate. Toss-ups excluded from pick accuracy remain in Brier scoring;
coverage reports how many settled forecasts became picks. Missing forecasts,
pending results and voids are explicit. Last source commit added this audit and tests.
Archived Vegas 124: CL-1 4/5; limited history 6/8 with one toss-up. This is a small
forward record, not the historical model validation sample.

Not found in current source or its file history: a prospective higher-confidence
selection policy, threshold-sweep experiment reports, separately validated winner
and method abstention rules, or a profitable parlay strategy. Do not claim the
owner's request to backtest these new ideas was completed based on the audit alone.

## Data and operational boundaries

Core pinned inputs: UFCStats Greco mirror (events, outcomes, rounds and bios),
TidyTuesday historical odds; gzip seeds and decompressed SHA-256 manifest are in
`research/inputs`. Identity normalization includes Jose Souza/Jose Henrique alias.
Supplemental sources: Bair UFC Data, UFC-Almanac, daily-odds and UFC Master Kaggle
archives, Odds Gap samples. Rankings, reach, judging rows and market observations
are displayed as evidence; importing them does not mean the model uses them.

Worker has provider adapters for UFCalendar, FighterAPI, The Odds API, Unofficial
UFC API and an existing Apify dataset. Credentials are AES-GCM encrypted in R2;
owner identity is checked server-side. Inspect live connection state before claiming
any provider is connected. This review did not inspect owner-only provider payloads.
Provider refresh stores responses; no code path automatically feeds those payloads
into CL-1 or rebuilds the card. Site service access does not supply visitor identity.
Never print credentials, relax permissions, or embed keys in assets.

Observed hosted schedule `Analyze upcoming UFC cards` (09:00 and 15:00 Toronto)
was paused at review time. Current saved forecast is Nov 14 09:00 Toronto, stats
through Nov 7; live event settlement was ahead of the published archive.
Home hides archived finished bouts, but Parlay Lab still enumerates the whole card.
One leg per fight is enforced; combined chance multiplies leg probabilities under
independence. Missing prop prices remain missing. Repeated legs across different
tickets create shared exposure, not independent bets.

## Verification performed in this review

- Existing audit test command passed (`node tests/audit.cjs`).
- All five decompressed input hashes matched the checked-in manifest.
- Ran model.py in an isolated scratch copy with pinned inputs and frozen weights.
  Entire card, closingTest and supplementValidation matched published data exactly.
  report and propValidation also matched, but those fields reuse frozen reports;
  equality alone does not independently reproduce their historical metrics.
- Independently recomputed winner matched-odds scores and both strategy cohorts:
  exact agreement with saved values above. Fresh full-test score is 63.519% across
  1,239 bouts versus frozen report's 1,234: five eligible Nov 7 bouts were added.
  This does not invalidate the older frozen report; label its date coverage clearly.
- No model weights, forecasts, result archive, privacy or production deployment
  changed during this review. Documentation is the only repository change.

## Recommended next work, not completed experiments

1. Create an explicit offline experiment runner from chronological per-bout rows.
   Preserve baseline coefficients and historical scoring. Pick thresholds using an
   earlier validation interval; evaluate once on later unseen dates. Previously
   inspected history is not a pristine new holdout. Keep a prospective journal too.
2. Compare winner thresholds and independent method-selection policies with accuracy,
   coverage, sample counts, uncertainty intervals, Brier/log loss and market baseline
   on identical eligible cohorts. Do not optimize accuracy alone by discarding losses.
3. Only test returns when timestamped executable same-book prices and settlement
   rules are available. Include stakes, voids, drawdown, repeated exposure and
   uncertainty. Separate hit probability from positive expected value.
4. Repair finished-fight filtering across every selection view and verify freshness.
   Reconcile REFRESH.md's advance-after-event-start instruction with its live-result
   update requirement. Do not resume a paused schedule without checking user intent.
5. Audit method coherence and settlement consistency before introducing a joint
   finish model. The browser audit skips technical decisions and special KO labels;
   journal.py uses the richer original UFCStats labels. Align behavior explicitly.
6. Audit result corrections: journal.py skips fully scored entries while the board
   can overwrite corrections. Retain original settlements plus correction provenance.

Resume from this document, inspect git status and source HEAD, and refresh hosted
state before making claims about current live predictions or API connections.
