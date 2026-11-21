'use strict';
function winnerRead(f){
 const p=f.p??f.limited;
 if(p==null)return {label:'Unavailable',chance:null,tier:'No estimate'};
 const chance=Math.max(p,1-p);
 return {label:chance<.51?'Toss-up':(p>.5?f.a.name:f.b.name),chance,tier:f.p==null?'Low confidence · limited history':'CL-1'};
}
function cardHome(){
 const v=data.supplementValidation,rows=data.card,full=rows.filter(f=>f.p!=null).length;
 const finished=data.archive[data.event.id]?.bouts||{};
 const done=f=>Object.hasOwn(finished,f.a.name+'|'+f.b.name);
 if(rows.length && rows.every(done))return head('No remaining fights',data.event.event+' is complete.','Home')+'<button data-tab="results">View card results →</button>';
 const top='<div class="cardmast"><div><div class="cap">Card overview</div><h1>'+esc(data.event.event)+'</h1><p>'+esc(day(data.event.date)+' · '+data.event.venue)+'</p></div><div class="headcounts"><strong>'+full+'</strong> CL-1 picks <strong>'+(rows.length-full)+'</strong> limited-history reads</div></div>';
 function group(title,list,start){
  if(list.every(done))return '';
  return '<section class="stack"><h2>'+title+'</h2><div class="boutgrid">'+list.map((f,j)=>{
   if(done(f))return '';
   const w=winnerRead(f),p=f.props||{};
   const shadow=f.strikingShadow==null?'':'<p class="testcopy">Experimental · '+esc(f.strikingShadow>=.5?f.a.name:f.b.name)+' '+percent(Math.max(f.strikingShadow,1-f.strikingShadow))+' with opponent-adjusted recent striking</p>';
   return '<article class="panel boutcard"><span class="cap">'+esc(f.division)+' · '+esc(p.rounds??'—')+' rounds</span><h3><button class="textbtn" data-open="'+(start+j)+'">'+esc(f.a.name)+' <em>vs</em> '+esc(f.b.name)+'</button></h3><div class="pickread"><div><small>'+esc(w.tier)+'</small><b>'+esc(w.label)+'</b></div><strong>'+percent(w.chance)+'</strong></div><div class="outcomes">'+[['Distance',p.distance],['KO/TKO/DQ',p.ko],['Submission',p.submission]].map(([k,x])=>'<div><small>'+k+'</small><b>'+percent(x)+'</b></div>').join('')+'</div><small class="muted">'+f.a.total+' / '+f.b.total+' qualifying bouts, in listed order</small>'+shadow+'</article>';
  }).join('')+'</div></section>';
 }
 return top+group('Main card',rows.slice(0,data.event.mainCount),0)+group('Prelims',rows.slice(data.event.mainCount),data.event.mainCount)+'<details class="panel stack"><summary>How to read the estimates</summary><p class="testcopy">The limited-history model uses age, opponent-adjusted rating, recent form and experience. A missing age uses 30 as a neutral default. In '+v.limited.n+' held-out bouts outside CL-1 eligibility, it picked '+percent(v.limited.accuracy)+' correctly, with ties scored as half. A lean below 51% is displayed as a toss-up.</p><p class="testcopy">Submission estimates combine each fighter’s win chance with their chance of submitting this opponent if they win. Inputs include submission wins and losses, submission attempts and takedowns. Across '+v.submission.n+' held-out fights the fight-level submission Brier score was '+v.submission.brier.toFixed(3)+'. Distance, KO and submission are estimated separately and can total above or below 100%.</p></details>';
}
function resultsView(){
 return head('Results','Original forecasts, separate model records and explicit uncertainty.','Scorecard')+
 '<div class="panel stack"><h2>How this audit scores</h2><p>Winner picks use the original 51% cutoff. Toss-ups are excluded from pick accuracy, but remain in probability scoring. Coverage shows how often a settled forecast became a pick. No losses have been relabeled.</p><p class="testcopy">Finish forecasts below are probabilities, not forced selections. They come from separate models and are not a joint outcome distribution: do not add them together or interpret the largest as a validated method pick. Lower Brier scores are better; 0 is perfect.</p><p class="testcopy">This board covers archived matchups only. Pending counts do not include fights absent from the archive. Historical validation and its matched-book comparison remain in Model record.</p></div>'+
 Object.values(data.archive).sort((a,b)=>b.date.localeCompare(a.date)).map(card=>{
  const audit=LedgerAudit.summarize(Object.values(card.bouts));
  const stats='<div class="boutgrid">'+audit.groups.map(g=>'<article class="panel"><h3>'+esc(g.tier)+'</h3><p><b>'+g.right+' / '+g.picks+'</b> picks correct · '+percent(g.accuracy)+'</p><p>Coverage · '+percent(g.coverage)+' of '+g.n+' settled forecasts</p><p>'+g.tossups+' toss-ups · Brier '+(g.brier==null?'—':g.brier.toFixed(3))+'</p></article>').join('')+'</div>';
  const cards=audit.rows.map(r=>{
   const grade=r.correct===null?r.label:(r.correct?'Correct':'Wrong');
   const props=[['Distance','p_distance'],['KO/TKO','p_ko'],['Submission','p_submission']].map(([name,key])=>{
    const o=LedgerAudit.outcome(r,key);
    return '<p>'+name+' · issued '+percent(r[key])+' · '+(o?'Occurred: '+(o.actual?'Yes':'No')+' · Brier '+o.brier.toFixed(3):'Not scored')+'</p>';
   }).join('');
   return '<article class="panel"><small>'+esc(r.status+' · '+r.tier)+'</small><h3>'+esc(r.a)+' vs '+esc(r.b)+'</h3><p>'+esc(r.label)+' · '+esc(r.pick||r.label)+' '+percent(r.chance)+' · '+esc(grade)+'</p><b>Result · '+esc(r.winner||'No decisive winner')+' '+esc(r.method)+'</b>'+props+'<small>Forecast · '+esc(when(r.issued))+'</small></article>';
  }).join('');
  return '<section class="stack"><h2>'+esc(card.name)+'</h2><p>'+audit.pending+' pending · '+audit.voids+' void · '+audit.rows.filter(r=>r.status==='Settled'&&r.p===null).length+' settled without winner forecast</p>'+stats+'<div class="boutgrid">'+cards+'</div></section>';
 }).join('');
}
