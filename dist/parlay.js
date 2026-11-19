'use strict';
const draftKey='cageside-parlay-draft-v1';
let slip={}, restoredEvent='',marketType='distance', ranking='chance';
function availableMarkets(f) {
 const koPrice=data.event.propQuotes?.fighterKO?.[cardKey(f)]||[];
 const p=f.props, quote=data.event.propQuotes?.lines?.[f.a.name+'|'+f.b.name]||[];
 const win=f.p??f.limited;
 const list=[['winA',f.a.name+' wins',win,f.lines[0]],['winB',f.b.name+' wins',win==null?null:1-win,f.lines[1]]];
 if(p) list.push(['sub','Either fighter by submission',p.submission],['subA',f.a.name+' by submission',p.subA],['subB',f.b.name+' by submission',p.subB],['distance','Goes the distance',p.distance,quote[0]],['early','Ends early',1-p.distance,quote[1]],['ko','Either fighter by KO/TKO/DQ',p.ko],['koA',f.a.name+' by KO/TKO/DQ',p.koA,koPrice[0]],['koB',f.b.name+' by KO/TKO/DQ',p.koB,koPrice[1]]);
 return list.filter(v=>v[2]!=null);
}
function cardKey(f){return f.a.name+'|'+f.b.name}
function restoreDraft(){
 if(restoredEvent===data.event.id)return;
 restoredEvent=data.event.id;slip={};
 try{const saved=JSON.parse(localStorage.getItem(draftKey));if(saved?.event===data.event.id&&saved.legs&&typeof saved.legs==='object')slip=saved.legs}catch{}
}
function saveDraft(){try{localStorage.setItem(draftKey,JSON.stringify({event:data.event.id,legs:slip}))}catch{}}
const fairOdds=p=>p==null?'—':p<=.5?'+'+Math.round((1-p)/p*100):'−'+Math.round(p/(1-p)*100);
const opt=(value,label,current)=>'<option value="'+esc(value)+'" '+(value===current?'selected':'')+'>'+esc(label)+'</option>';
function chosenLegs(){
 const legs=[];
 data.card.forEach((f,i)=>{const saved=slip[cardKey(f)];if(!saved)return;
 const market=availableMarkets(f).find(v=>v[0]===saved.key);if(market)legs.push({i,f,market,price:saved.custom??market[3]??null,custom:saved.custom!=null})});
 return legs;
}
function slipStats(){
 const legs=chosenLegs(),p=legs.reduce((v,x)=>v*x.market[2],1);
 const decimal=legs.every(x=>Number.isFinite(x.price)&&Math.abs(x.price)>=100)?legs.reduce((v,x)=>v/implied(x.price),1):null;
 return '<div class="slipstats"><div><span>All legs hit</span><strong>'+percent(legs.length?p:null)+'</strong></div><div><span>Model fair line</span><strong>'+(legs.length?fairOdds(p):'—')+'</strong></div><div><span>Price break-even</span><strong>'+percent(legs.length&&decimal?1/decimal:null)+'</strong></div></div><p class="testcopy">'+(legs.length>1?'Assumes independent fights. A book may quote a different combined price. ':legs.length===1?'Add a different fight to compare a parlay. ':'Select a leg from the board. ')+(legs.some(x=>!Number.isFinite(x.price))?'Add the missing prices to calculate break-even.':'')+'</p>';
}
function slipPanel(){
 const legs=chosenLegs();
 return '<aside class="panel draft"><div class="sectionhead"><h2>Your parlay</h2><span class="tag">'+legs.length+' '+(legs.length===1?'leg':'legs')+'</span></div>'+legs.map(({i,f,market,price,custom})=>'<div class="leg"><div><strong>'+esc(market[1])+'</strong><small>'+esc(short(f.a.name)+' vs '+short(f.b.name))+' · '+percent(market[2])+(f.p==null?' · Low confidence':'')+'</small></div><button class="remove" aria-label="Remove '+esc(market[1])+'" data-drop="'+i+'">×</button><label>American odds <input type="number" step="1" inputmode="text" data-line="'+i+'" value="'+esc(price??'')+'" placeholder="e.g. -150"></label><small class="legnote">'+(custom?'Your price':price!=null?'Saved book price':'Price unavailable')+'</small></div>').join('')+'<div id="totals" aria-live="polite">'+slipStats()+'</div></aside>';
}
function parlay(){
 restoreDraft();
 const categories={submission:['sub'],namedSub:['subA','subB'],distance:['distance'],early:['early'],ko:['ko'],fighter:['koA','koB'],win:['winA','winB']};
 const rows=data.card.flatMap((f,i)=>availableMarkets(f).filter(m=>categories[marketType].includes(m[0])).map(m=>({f,i,m,gap:m[3]!=null?m[2]-implied(m[3]):null})));
 rows.sort((a,b)=>ranking==='gap'?(b.gap??-2)-(a.gap??-2):b.m[2]-a.m[2]);
 const report=data.propValidation?.report;
 const validation=report?'<details class="panel stack"><summary>How accurate are these forecasts?</summary><p class="testcopy">Tested on '+report.distance.n.toLocaleString()+' later fights, '+day(data.propValidation.start)+' to '+day(data.propValidation.end)+'. The benchmark is the historical rate for the same division and scheduled length. Lower Brier scores are better.</p><table><thead><tr><th>Outcome</th><th>Model Brier</th><th>Baseline</th></tr></thead><tbody>'+[['Distance','distance'],['Either fighter KO/TKO/DQ','ko'],['Named fighter KO/TKO/DQ','koSide']].map(([l,k])=>'<tr><td>'+l+'</td><td>'+report[k].brier.toFixed(3)+'</td><td>'+report[k].baseline.toFixed(3)+'</td></tr>').join('')+'</tbody></table><p class="testcopy">Named-fighter KO scoring uses '+report.koSide.n.toLocaleString()+' fighter outcomes across '+(report.koSide.n/2).toLocaleString()+' fights. Models use prior finish histories, division and scheduled rounds. Distance means reaching the final scheduled bell. The KO group includes doctor stoppages and disqualifications. No contests are excluded. No historical sportsbook prop-price or combined-ticket profitability test has been run.</p></details>':'';
 const src=data.event.propQuotes;
 return head('Parlay lab',data.event.event+' · '+day(data.event.date),'Fight markets')+'<div class="lab"><section class="panel"><div class="sectionhead"><h2>Leg board</h2><span class="tiny">'+data.card.length+' BOUTS</span></div><div class="labfilters"><label>Market <select id="legmarket">'+[['distance','Goes the distance'],['early','Ends early'],['ko','Either fighter by KO/TKO/DQ'],['fighter','Fighter by KO/TKO/DQ'],['submission','Either fighter by submission'],['namedSub','Fighter by submission'],['win','Fight winner']].map(([k,l])=>opt(k,l,marketType)).join('')+'</select></label><label>Sort <select id="legrank">'+opt('chance','Highest probability',ranking)+opt('gap','Model minus break-even',ranking)+'</select></label></div><div class="boardrows">'+rows.map(({f,i,m,gap})=>{
 const selected=slip[cardKey(f)]?.key===m[0],thin=f.props?.thin||f.p==null;
 return '<div class="propitem"><div><b>'+esc(['win','fighter','namedSub'].includes(marketType)?m[1]:short(f.a.name)+' vs '+short(f.b.name))+'</b><small>'+esc(['win','fighter','namedSub'].includes(marketType)?short(f.a.name)+' vs '+short(f.b.name):f.division)+' · '+(f.props?.rounds??'?')+' rounds'+(thin?' · Thin history':'')+'</small><small>'+ (m[3]!=null?'Quote '+odds(m[3])+' · break-even '+percent(implied(m[3]))+(gap!=null?' · '+(gap>=0?'+':'')+(gap*100).toFixed(1)+' pp':''):'Book price unavailable')+'</small></div><div class="probn"><b>'+percent(m[2])+'</b><small>fair '+fairOdds(m[2])+'</small></div><button class="pickleg '+(selected?'on':'')+'" data-leg="'+i+'" data-key="'+m[0]+'" aria-label="'+esc((selected?'Remove ':'Add ')+m[1]+' for '+f.a.name+' vs '+f.b.name)+'">'+(selected?'✓':'＋')+'</button></div>'}).join('')+'</div></section>'+slipPanel()+'</div><p class="labhint">One leg per fight. Picking another outcome from the same bout replaces the earlier selection. Thin histories draw more heavily on division and round-length patterns. Gaps compare the model with the quoted price’s break-even probability.</p>'+(src?'<p class="labhint">Prop prices observed '+when(src.observed)+' · <a href="'+safeUrl(src.source)+'" target="_blank" rel="noreferrer">'+esc(src.book)+'</a>. Moneylines use the separate card snapshot. Enter matching prices from your book for a ticket comparison.</p>':'')+validation;
}
document.addEventListener('change',e=>{
 if(e.target.id==='legmarket'){marketType=e.target.value;render()}
 if(e.target.id==='legrank'){ranking=e.target.value;render()}
});
document.addEventListener('input',e=>{
 const el=e.target;if(el.dataset.line==null)return;
 const f=data.card[Number(el.dataset.line)],s=slip[cardKey(f)],val=el.value.trim();
 const valid=val!==''&&Number.isSafeInteger(Number(val))&&Math.abs(Number(val))>=100;
 // An empty or invalid edit must never silently reuse a saved book quote.
 s.custom=valid?Number(val):'';
 el.setAttribute('aria-invalid',String(!valid&&val!==''));saveDraft();
 el.closest('.leg').querySelector('.legnote').textContent=valid?'Your price':val?'Use +100 or higher, or −100 or lower.':'Enter a book price';
 $('#totals').innerHTML=slipStats();
});
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b||!data)return;
 if(b.dataset.leg!=null){const f=data.card[Number(b.dataset.leg)],key=cardKey(f);if(slip[key]?.key===b.dataset.key)delete slip[key];else slip[key]={key:b.dataset.key};saveDraft();render()}
 if(b.dataset.drop!=null){delete slip[cardKey(data.card[Number(b.dataset.drop)])];saveDraft();render()}
});
