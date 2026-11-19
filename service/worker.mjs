const families=['ufcalendar','fighterapi','theodds','apify','unofficial'];
const enc=new TextEncoder();
const hex=b=>Array.from(new Uint8Array(b),v=>v.toString(16).padStart(2,'0')).join('');
const unhex=s=>Uint8Array.from(s.match(/../g),v=>parseInt(v,16));
const send=(obj,status=200)=>Response.json(obj,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
async function aes(env){
 return crypto.subtle.importKey('raw',unhex(env.PROVIDER_VAULT_KEY),{name:'AES-GCM'},false,['encrypt','decrypt']);
}
async function seal(env,path,value){
 const iv=crypto.getRandomValues(new Uint8Array(12));
 const encrypted=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:enc.encode(path)},await aes(env),enc.encode(JSON.stringify(value)));
 return JSON.stringify([hex(iv),hex(encrypted)]);
}
async function readSecret(env,path){
 const obj=await env.BUCKET.get(path);if(!obj)return null;
 const [iv,bytes]=await obj.json();
 const raw=await crypto.subtle.decrypt({name:'AES-GCM',iv:unhex(iv),additionalData:enc.encode(path)},await aes(env),unhex(bytes));
 return JSON.parse(new TextDecoder().decode(raw));
}
async function upstream(provider,secret,card){
 const {key,dataset}=secret;let url,options={};
 if(provider==='ufcalendar'){
  url='https://api.ufcalendar.com/v1/events?org=ufc&from='+card.event.date+'&limit=5';
  options.headers={Authorization:'Bearer '+key};
 }else if(provider==='fighterapi'){
  url='https://mcp.fighterapi.com/v1/get_schedule';
  options={method:'POST',headers:{'x-api-key':key,'Content-Type':'application/json'},body:JSON.stringify({days:30,league:"mma"})};
 }else if(provider==='theodds'){
  url='https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds?regions=us&markets=h2h&oddsFormat=american&apiKey='+encodeURIComponent(key);
 }else if(provider==='unofficial'){
  url='https://ufc-api.on-forge.com/v1/events?status=upcoming&per_page=5';
  options.headers={Authorization:'Bearer '+key,Accept:'application/json'};
 }else{
  if(!/^[A-Za-z0-9_-]{5,70}$/.test(dataset||''))throw Error('Enter a valid Apify dataset ID.');
  url='https://api.apify.com/v2/datasets/'+dataset+'/items?clean=true&limit=100';
  options.headers={Authorization:'Bearer '+key};
 }
 async function requestJSON(target,opts){
  const response=await fetch(target,{...opts,redirect:'error',signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error('Provider returned HTTP '+response.status+'.');
  if(!response.headers.get('content-type')?.includes('json'))throw Error('Provider did not return JSON.');
  const raw=await response.text();if(raw.length>2000000)throw Error('Provider response exceeds the snapshot limit.');
  const parsed=JSON.parse(raw.split(key).join('[redacted]'));
  if(!parsed||typeof parsed!=='object'||parsed.error||parsed.success===false)throw Error('Provider rejected the request.');
  return parsed;
 }
 const parsed=await requestJSON(url,options);
 let rows=parsed.data??parsed;
 if(provider==='fighterapi'){
  const bouts=rows.bouts;
  if(!Array.isArray(bouts))throw Error('Provider returned an unexpected schedule schema.');
  rows=bouts.filter(b=>b.event_date===card.event.date);
 }else if(provider==='ufcalendar'){
  if(!Array.isArray(rows))throw Error('Provider returned an unexpected calendar schema.');
  const day=card.event.date;const selected=rows.find(r=>r.starts_at?.slice(0,10)===day && (r.org==='ufc'||!r.org));
  if(selected?.slug||selected?.id){
   const base='https://api.ufcalendar.com/v1/events/'+encodeURIComponent(selected.slug||selected.id);
   const [event,odds]=await Promise.all([requestJSON(base,options),requestJSON(base+'/odds',options)]);
   rows={event:event.data??event,consensus:odds.data??odds};
  }
 }else if((provider==='theodds'||provider==='apify')&&!Array.isArray(rows))throw Error('Provider returned an unexpected schema.');
 return {provider,event:card.event.id,observed:new Date().toISOString(),rows};
}
async function api(req,env,url){
 const provider=url.pathname.split('/').pop(),user=req.headers.get('oai-authenticated-user-id');
 const runner=url.pathname==='/api/refresh';
 if(req.method==='POST'&& !runner && req.headers.get('origin')!==url.origin)return send({error:'Origin mismatch'},403);
 if(!env.BUCKET||!env.PROVIDER_VAULT_KEY)return send({error:'Private provider storage is unavailable.'},503);
 if(runner){
  const proof=req.headers.get('x-ledger-proof')||'';
  if(req.method!=='POST'||!proof||hex(await crypto.subtle.digest('SHA-256',enc.encode(proof)))!==env.LEDGER_REFRESH_DIGEST)return send({error:'Private refresh authorization required.'},403);
 }else if(!user)return send({error:'Sign in to connect accounts.'},401);
 if(!runner && (!env.LEDGER_OWNER_EMAIL || req.headers.get('oai-authenticated-user-email')?.toLowerCase()!==env.LEDGER_OWNER_EMAIL))return send({error:'Owner access required.'},403);
 const ownerKey='v1/connection-owner';
 let owner=await env.BUCKET.get(ownerKey).then(o=>o?.text());
 if(!runner && owner && owner!==user)return send({error:'Owner access required.'},403);
 const path=id=>'v1/secrets/'+id;
 if(url.pathname==='/api/connections'&&req.method==='GET'){
  const states={};
  await Promise.all(families.map(async id=>{let o=await env.BUCKET.get('v1/data/'+id);states[id]=o?await o.json():null}));
  return send(states);
 }
 const card=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(ASSETS['/data.json'][1]), c=>c.charCodeAt(0))));
 if(runner){
  const result={};
  for(const id of families){
   const secret=await readSecret(env,path(id));if(!secret){result[id]='needs key';continue}
   try{const snapshot=await upstream(id,secret,card);await env.BUCKET.put('v1/data/'+id,JSON.stringify(snapshot));result[id]=snapshot.observed}
   catch(e){result[id]=e.message.startsWith('Provider ')?e.message:'Provider unavailable'}
  }
  return send(result);
 }
 if(!families.includes(provider)||req.method!=='POST')return send({error:'Unknown endpoint.'},404);
 const input=await req.json();
 if(input.action==='disconnect'){
  if(owner!==user)return send({error:'Owner access required.'},403);
  await env.BUCKET.delete([path(provider),'v1/data/'+provider]);return send({removed:true});
 }
 if(!['connect','refresh'].includes(input.action))return send({error:'Invalid action.'},400);
 const secret=input.action==='connect'?{key:String(input.key||'').trim(),dataset:String(input.dataset||'').trim()}:await readSecret(env,path(provider));
 if(!secret?.key||secret.key.length>1024)return send({error:'Enter a provider key.'},400);
 let snapshot;
 try{snapshot=await upstream(provider,secret,card)}catch(e){return send({error:/^(Provider |Enter a valid)/.test(e.message)?e.message:'Could not retrieve provider data.'},502)}
 if(!owner){
  const lock=await env.BUCKET.put(ownerKey,user,{onlyIf:{etagDoesNotMatch:'*'}});
  if(!lock && (await (await env.BUCKET.get(ownerKey)).text())!==user)return send({error:'Owner access required.'},403);
 }
 if(input.action==='connect')await env.BUCKET.put(path(provider),await seal(env,path(provider),secret));
 await env.BUCKET.put('v1/data/'+provider,JSON.stringify(snapshot));return send(snapshot);
}
export default {async fetch(req,env){
 const u=new URL(req.url);
 if(u.pathname.startsWith('/api/')){
  try{return await api(req,env,u)}catch{return send({error:'Connection request could not be completed.'},503)}
 }
 const asset=ASSETS[u.pathname==='/'?'/index.html':u.pathname];
 if(!asset||!['GET','HEAD'].includes(req.method))return new Response('Not found',{status:404});
 return new Response(req.method==='HEAD'?null:Uint8Array.from(atob(asset[1]),c=>c.charCodeAt(0)),{headers:{'Content-Type':asset[0],'Cache-Control':'private, no-cache','X-Content-Type-Options':'nosniff'}});
}};
