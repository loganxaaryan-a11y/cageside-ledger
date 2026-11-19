'use strict';
// Historical reporting only. Preserve the original 51% winner-pick rule.
const LedgerAudit = (() => {
 const valid = p => typeof p === 'number' && Number.isFinite(p) && p >= 0 && p <= 1;
 function row(r) {
  const p = valid(r.p_a) ? r.p_a : valid(r.p_limited) ? r.p_limited : null;
  const tier = valid(r.p_a) ? 'CL-1' : 'Limited history';
  const decisive = r.winner === r.a || r.winner === r.b;
  const voided = /draw|no contest|cancel|void/i.test(r.method || '') || r.status === 'void';
  const status = voided ? 'Void' : decisive ? 'Settled' : 'Pending';
  const chance = p === null ? null : Math.max(p, 1-p);
  const pick = chance !== null && chance >= .51 ? (p > .5 ? r.a : r.b) : null;
  const label = p === null ? 'No forecast' : pick ? 'Issued pick' : 'Toss-up';
  const brier = status === 'Settled' && p !== null ? (p - Number(r.winner === r.a)) ** 2 : null;
  return {...r,p,tier,status,chance,pick,label,brier,correct:status === 'Settled' && pick ? pick === r.winner : null};
 }
 function summarize(input) {
  const rows = input.map(row);
  const groups = ['CL-1','Limited history'].map(tier => {
   const settled = rows.filter(r => r.tier === tier && r.status === 'Settled' && r.p !== null);
   const picks = settled.filter(r => r.pick);
   return {tier,n:settled.length,picks:picks.length,right:picks.filter(r=>r.correct).length,
    tossups:settled.length-picks.length,coverage:settled.length?picks.length/settled.length:null,
    accuracy:picks.length?picks.filter(r=>r.correct).length/picks.length:null,
    brier:settled.length?settled.reduce((s,r)=>s+r.brier,0)/settled.length:null};
  });
  return {rows,groups,pending:rows.filter(r=>r.status==='Pending').length,voids:rows.filter(r=>r.status==='Void').length};
 }
 function outcome(r,key) {
  if(!valid(r[key]))return null;
  const method=r.method||'';
  // Do not equate a technical decision with completing the scheduled duration.
  if(row(r).status!=='Settled' || !['Decision','KO/TKO','Submission'].includes(method))return null;
  const actual=Number(method === ({p_distance:'Decision',p_ko:'KO/TKO',p_submission:'Submission'})[key]);
  return {probability:r[key],actual,brier:(r[key]-actual)**2};
 }
 return {row,summarize,outcome};
})();
if(typeof module !== 'undefined')module.exports=LedgerAudit;
