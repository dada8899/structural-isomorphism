'use strict';
/* Synthetic plain snapshots and transport controls; browser tests prove persistence. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
if(!globalThis.crypto)globalThis.crypto=crypto.webcrypto;
const api=require('../assets/financial-registry.js');
const uid=n=>`${String(n).padStart(8,'0')}-1111-4111-8111-111111111111`,rid=uid(1),ref=uid(2),digest='a'.repeat(64),at='2026-10-23T02:03:04.123456Z';
const cp=v=>JSON.parse(JSON.stringify(v));
const owner={kind:'owner_supplied',verification:'unverified',original_available:false,system_verified:false};
async function fixture({version=3,revision=1,refId=ref,currentRevision=revision}={}){
 const csv='synthetic exact CSV\r\nprivate source excerpt',base={...owner,record_index:1,physical_line_start:2,physical_line_end:3};
 const source={...base,key:'source',row_type:'source',url:'https://example.invalid/<literal>',locator:'owner page 3',excerpt:'é private <img src=x>',received_excerpt_sha256:await api.sha('é private <img src=x>'),declared_original_sha256:null,claimed_published_at:'2026-01-01',claimed_accessed_at:'2026-01-02',read_scope:'owner excerpt',source_chain:[]};
 const obs={...base,record_index:2,physical_line_start:4,physical_line_end:4,key:'revenue',row_type:'observation',entity_scope:'Synthetic group',scope_kind:'group',metric:'revenue',period_start:'2026-01-01',period_end:'2026-06-30',period_grain:'interim',value:'1e+02',currency:'USD',unit:'million',accounting_basis:'owner GAAP',declared_basis:'disclosed',source_refs:['source'],alternative_refs:[]};
 const missing={...obs,record_index:3,physical_line_start:5,physical_line_end:5,key:'unknown_op',metric:'operating_profit',value:null,declared_basis:'missing',source_refs:[]};
 const plan={contract:'owner-financial-key-plan-v2',parser_revision:'owner-financial-csv-v1',records:[source,obs,missing]},csvSha=await api.sha(csv),planSha=await api.hash(plan);
 const p=await api.hash({contract:api.CONTRACT,parser_revision:'owner-financial-csv-v1',research_id:rid,input_revision:revision,problem_digest:digest,expected_research_version:version,exact_received_csv_sha256:csvSha,key_based_plan_digest:planSha});
 const request={schema_version:'structure-research-v1',contract_revision:api.CONTRACT,data:{input_revision:revision,expected_research_version:version,csv_text:csv,preview_digest:p,confirmed:true}};
 const meta={...owner,registry_ref:{id:refId,revision:1,digest:'b'.repeat(64)},research_id:rid,input_revision:revision,problem_digest:digest,research_version_before:version,research_version_after:version+1,received_at:at,parser_revision:'owner-financial-csv-v1',exact_received_csv_sha256:csvSha,key_based_plan_digest:planSha,preview_digest:p,request_digest:await api.hash(request),qualification:'conditional_on_owner_supplied_data'};
 const records=cp(plan.records).map((r,i)=>({...r,id:uid(i+10),...(r.source_refs?{source_refs:r.source_refs.map(()=>uid(10))}: {})}));
 const registry={format_version:'owner-financial-registry-public-v2',parser_revision:'owner-financial-csv-v1',identity:{id:refId,revision:1},binding:Object.fromEntries(['research_id','input_revision','problem_digest','research_version_before','research_version_after'].map(k=>[k,meta[k]])),receipt:Object.fromEntries(['received_at','exact_received_csv_sha256','key_based_plan_digest','preview_digest'].map(k=>[k,meta[k]])),key_map:records.map(r=>({key:r.key,row_type:r.row_type,registered_id:r.id,record_index:r.record_index,physical_line_start:r.physical_line_start,physical_line_end:r.physical_line_end})),records};
 const projection={csv_text:csv,registry},common={metadata:meta,current:{input_revision:currentRevision,research_version:version+1},is_historical:revision!==currentRevision,public_projection_digest:await api.hash(projection),execution_authorized:false};
 const wrap=data=>({schema_version:'structure-research-v1',contract_revision:api.CONTRACT,data});
 const read=wrap({...common,projection}),confirm=wrap({...common,persisted:true});
 const item={...owner,registry_ref:meta.registry_ref,input_revision:revision,problem_digest:digest,research_version_before:version,research_version_after:version+1,received_at:at,is_historical:revision!==currentRevision,public_projection_digest:common.public_projection_digest,qualification:meta.qualification};
 const list=wrap({research_id:rid,current:common.current,items:[item],next_cursor:null});
 const preview={...owner,research_id:rid,input_revision:revision,problem_digest:digest,expected_research_version:version,parser_revision:'owner-financial-csv-v1',exact_received_csv_sha256:csvSha,key_based_plan_digest:planSha,preview_digest:p,plan,persisted:false,execution_authorized:false};
 return {csv,plan,request,read,confirm,list,preview};
}
class Element {
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.text='';this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.attrs={};this.events={};}
 set textContent(v){this.text=String(v);this.children=[];}get textContent(){return this.text+this.children.map(x=>x.textContent??x).join('');}
 replaceChildren(...v){this.text='';this.children=v;}append(...v){this.children.push(...v);}setAttribute(k,v){this.attrs[k]=v;}
 addEventListener(k,fn){(this.events[k]||=[]).push(fn);}fire(k){return Promise.all((this.events[k]||[]).map(fn=>fn({target:this})));}
 querySelectorAll(tag){return this.children.flatMap(n=>typeof n==='string'?[]:[...(n.tagName.toLowerCase()===tag?[n]:[]),...n.querySelectorAll(tag)]);}
}
function memory(){const values=new Map();return {values,get length(){return values.size;},key:i=>[...values.keys()][i]??null,getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};}
const html=fs.readFileSync(path.join(__dirname,'../research.html'),'utf8');
function runtime(sender,{storage=memory(),scope={},onObservedRoot=()=>{}}={}){
 const elements=new Map([...html.matchAll(/id="(financial-registry-[^"]+|financial-preview-csv)"/g)].map(m=>[m[1],new Element()]));const doc={getElementById:k=>elements.get(k),createElement:t=>new Element(t)};
 const s={account:JSON.stringify(['synthetic@example.invalid','2026-10-23']),privateGeneration:1,rid,revision:1,digest,version:3,dirty:false,readonly:false,busy:false,visible:true,...scope};let authenticated=true,rootVersion=3,rootRevision=1;const requests=[];
 const root=async()=>({research:{id:s.rid,current_revision:rootRevision},research_version:rootVersion,revisions:Array.from({length:rootRevision},(_,i)=>({revision:i+1,digest}))});
 const controller=api.mount({document:doc,getScope:()=>({...s}),authenticate:async active=>authenticated&&active(),fetchRoot:root,onObservedRoot,storage,fetch:async(url,options)=>{requests.push({url,options});return sender(url,options);}});
 return {controller,scope:s,requests,elements,storage,el:k=>elements.get('financial-registry-'+k),csv:()=>elements.get('financial-preview-csv'),auth:v=>{authenticated=v;},root:(v,r=1)=>{rootVersion=v;rootRevision=r;}};
}
const response=v=>new Response(JSON.stringify(v),{status:200});
async function prepare(r,f){r.csv().value=f.csv;await r.controller.acceptPreview({checked:f.preview,csv:f.csv});r.el('consent').checked=true;}

test('four actual exports retain canonical byte hashes and frozen source SHA',async()=>{
 for(const [name,schema] of Object.entries(api.SCHEMAS)){const raw=api.canonical(schema)+'\n';assert.equal(Buffer.byteLength(raw),api.EXPORTS[name].bytes);assert.equal(await api.sha(raw),api.EXPORTS[name].sha256);}
 const source=fs.readFileSync(path.join(__dirname,'../../backend/research/financial_input_schemas.py'));assert.equal(crypto.createHash('sha256').update(source).digest('hex'),api.SOURCE_SHA256);
});

test('strict bounded decoding rejects duplicate/surrogate/float/unsafe/depth/stream overflow',async()=>{
 for(const raw of ['{"a":1,"a":2}','{"a":1.0}','{"a":NaN}','{"a":-0}','{"a":9007199254740993}','"\\ud800"','\ufeff{}','['.repeat(34)+'0'+']'.repeat(34)])assert.throws(()=>api.strictJSON(raw));
 assert.equal(api.strictJSON('{"a":1}').a,1);await assert.rejects(api.body(new Response(new Uint8Array(524289))));await assert.rejects(api.body(new Response(new Uint8Array([255]))));
});

test('full real read/confirm/list shapes and each raw hash domain bind original creation version',async()=>{
 const f=await fixture();for(const [kind,v] of [['read',f.read],['confirm',f.confirm],['list',f.list]])assert.equal(await api.check(kind,v,{rid,ref,...(kind==='confirm'?{request:f.request}: {})}),v.data);
 const read=cp(f.read);read.data.current.research_version=20;assert.equal((await api.check('read',read,{rid,ref})).is_historical,false);
 for(const mutate of [d=>d.metadata.input_revision=2,d=>d.metadata.research_id=uid(90),d=>d.projection.csv_text+=' ',d=>d.projection.registry.key_map[0].key='other',d=>d.projection.registry.receipt.received_at='2026-02-30T00:00:00.123456Z',d=>d.projection.registry.records[0].original_available=0,d=>d.execution_authorized=0,d=>d.metadata.extra=true,d=>d.metadata.preview_digest='c'.repeat(64),d=>d.metadata.request_digest='c'.repeat(64)]){const bad=cp(f.read);mutate(bad.data);await assert.rejects(api.check('read',bad,{rid,ref}));}
 assert.equal(f.read.data.projection.registry.records[1].value,'1e+02');assert.equal(f.read.data.projection.registry.records[2].value,null);
});

test('private opaque digest is an anchor, never substituted with public projection digest',async()=>{
 const f=await fixture();assert.notEqual(f.read.data.metadata.registry_ref.digest,f.read.data.public_projection_digest);await api.check('read',f.read,{rid,ref,anchor:{...f.read.data.metadata,public_projection_digest:f.read.data.public_projection_digest}});
 const bad=cp(f.read);bad.data.metadata.registry_ref.digest=bad.data.public_projection_digest;await assert.rejects(api.check('read',bad,{rid,ref,anchor:f.list.data.items[0]}));
});

test('key map/reference cycle and decimal cap fail even if outer public digest is rebuilt',async()=>{
 for(const mutate of [r=>r.key_map.reverse(),r=>r.records[0].source_chain=[uid(10)],r=>r.records[1].source_refs=[uid(11)],r=>r.records[1].value='1000000000000000001',r=>r.records[2].value='0',r=>r.records[1].period_end='2026-02-30',r=>r.records[0].claimed_accessed_at='2025-01-01']){const f=await fixture();mutate(f.read.data.projection.registry);f.read.data.public_projection_digest=await api.hash(f.read.data.projection);await assert.rejects(api.check('read',f.read,{rid,ref}));}
});

test('historical flag and pagination use original refs and do not treat higher version as history',async()=>{
 const f=await fixture({currentRevision:2});assert.equal((await api.check('read',f.read,{rid,ref})).is_historical,true);const bad=cp(f.list);bad.data.items[0].is_historical=false;await assert.rejects(api.check('list',bad,{rid}));
 bad.data.items[0].is_historical=true;bad.data.next_cursor=uid(99);await assert.rejects(api.check('list',bad,{rid}));
});

test('double confirm sends once, verifies GET, leaves original editor and no automatic selection',async()=>{
 const f=await fixture();let resolve;const gate=new Promise(r=>{resolve=r;});let posts=0;const r=runtime(async(url,options)=>{if(options.method==='POST'){posts++;await gate;r.root(4);return response(f.confirm);}return response(f.read);});await prepare(r,f);
 const wait=r.controller.confirm();await new Promise(resolve=>setImmediate(resolve));await r.controller.confirm();resolve();await wait;
 assert.equal(posts,1);assert.equal(r.requests.length,2);assert.match(r.el('status').textContent,/已保存并核对读回/);assert.equal(r.scope.version,3);assert.equal(r.controller.getSelectedRegistry(),null);r.controller.choose();assert.ok(r.controller.getSelectedRegistry());assert.equal(Object.isFrozen(r.controller.getSelectedRegistry()),true);assert.match(r.el('detail').textContent,/缺失／争议，未按0处理/);assert.equal(r.el('detail').querySelectorAll('img').length,0);
 assert.equal(r.storage.values.size,0);
});

test('lost ACK keeps original body/key through dirty/new-version recovery; no new preview required',async()=>{
 const f=await fixture();let n=0;const r=runtime((url,options)=>{if(options.method==='POST'){if(++n===1)throw new TypeError('synthetic lost ACK');return response({...f.confirm,data:{...f.confirm.data,current:{input_revision:2,research_version:9},is_historical:true}});}return response({...f.read,data:{...f.read.data,current:{input_revision:2,research_version:9},is_historical:true}});});await prepare(r,f);await r.controller.confirm();const first=r.requests[0].options;
 assert.equal(r.controller.inspect().pending,true);assert.match(r.el('status').textContent,/可能已经保存/);assert.equal(r.storage.values.size,1);assert.doesNotMatch([...r.storage.values.values()][0],/private source excerpt|synthetic@example|csv_text|task_request/);
 r.scope.dirty=true;r.scope.revision=2;r.scope.version=9;r.root(9,2);r.controller.observe();await r.controller.recover();const replay=r.requests.findLast(x=>x.options.method==='POST').options;assert.equal(replay.body,first.body);assert.equal(replay.headers['Idempotency-Key'],first.headers['Idempotency-Key']);assert.match(r.el('status').textContent,/已保存并核对读回/);assert.equal(r.controller.getSelectedRegistry(),null);
});

test('reload descriptor requires exact resupplied CSV and original Envelope, never a new key',async()=>{
 const f=await fixture(),storage=memory();const one=runtime(()=>{throw new TypeError('lost ACK');},{storage});await prepare(one,f);await one.controller.confirm();const original=one.requests[0].options;
 const two=runtime((url,opts)=>{if(opts.method==='POST'){two.root(4);return response(f.confirm);}return response(f.read);},{storage});await two.controller.history();assert.match(two.el('pending').textContent,/原 CSV 未保留/);two.csv().value=f.csv+' ';await two.controller.recover();assert.equal(two.requests.filter(r=>r.options.method==='POST').length,0);
 two.csv().value=f.csv;await two.controller.recover();const replay=two.requests.find(x=>x.options.method==='POST').options;assert.equal(replay.body,original.body);assert.equal(replay.headers['Idempotency-Key'],original.headers['Idempotency-Key']);
});

test('Auth unknown, navigation and bfcache hide private bodies and preserve unresolved fence',async()=>{
 for(const cause of ['auth_unknown','page_suspended','bfcache_restore','inflight_navigation']){const f=await fixture(),r=runtime(()=>{throw new TypeError('lost');});await prepare(r,f);await r.controller.confirm();const before=[...r.storage.values.entries()];r.controller.invalidate(cause);assert.deepEqual([...r.storage.values.entries()],before);assert.equal(r.el('detail').textContent,'');assert.equal(r.controller.inspect().pending,true);assert.equal(r.el('confirm').disabled,true);}
});

test('confirmed exit/actor change erase only own actor metadata, and old response cannot resurrect',async()=>{
 for(const cause of ['confirmed_logout','credential_conflict','actor_changed']){const f=await fixture(),r=runtime(()=>{throw new TypeError('lost');});await prepare(r,f);await r.controller.confirm();r.storage.setItem('structure-research-pending:other-module','keep');r.controller.reset(cause);assert.deepEqual([...r.storage.values.entries()],[['structure-research-pending:other-module','keep']]);assert.equal(r.controller.inspect().pending,false);}
 const f=await fixture();let release,started;const began=new Promise(done=>{started=done;});const r=runtime(()=>new Promise(done=>{release=()=>done(response(f.read));started();}));const wait=r.controller.readRecord(ref);await began;r.controller.reset('confirmed_logout');release();await wait;assert.equal(r.el('detail').textContent,'');assert.equal(r.controller.getSelectedRegistry(),null);
});

test('dirty/read-only still permit legitimate list and read; selection never becomes write authority',async()=>{
 const f=await fixture();const r=runtime(url=>response(url.endsWith(ref)?f.read:f.list),{scope:{dirty:true,readonly:true}});r.root(4);await r.controller.history();assert.match(r.el('list').textContent,/打开材料/);await r.controller.readRecord(ref);r.controller.choose();assert.equal(r.controller.getSelectedRegistry(),null);assert.equal(r.el('confirm').disabled,true);assert.equal(r.requests.every(r=>r.options.method!=='POST'),true);
});

test('storage failure falls back to explicit memory-only; corrupt descriptor blocks new confirmation',async()=>{
 const f=await fixture();const store=memory();store.setItem=()=>{throw Error('quota');};const r=runtime(()=>{throw new TypeError('lost');},{storage:store});await prepare(r,f);await r.controller.confirm();assert.match(r.el('pending').textContent,/只保留在本页内存/);assert.equal(r.controller.inspect().pending,true);
 const actor=await api.hash({account:JSON.parse(r.scope.account)}),bad=memory();bad.setItem('structure-research-pending:financial-registry-v2:'+actor+':'+rid,'{"bad":true}');const x=runtime(()=>response(f.list),{storage:bad});x.root(4);await x.controller.history();assert.equal(x.controller.inspect().fence,true);assert.equal(x.el('confirm').disabled,true);
});

test('same-ref anchor mismatch and malformed read clear all old private view',async()=>{
 const f=await fixture();let corrupt=false;const r=runtime(()=>{const v=cp(f.read);if(corrupt)v.data.projection.csv_text+=' ';return response(v);});r.root(4);await r.controller.readRecord(ref);assert.match(r.el('detail').textContent,/private/);r.controller.choose();assert.ok(r.controller.getSelectedRegistry());corrupt=true;await r.controller.readRecord(ref);assert.equal(r.el('detail').textContent,'');assert.equal(r.controller.getSelectedRegistry(),null);
});

test('new preview retains original FIN1 privacy and module never writes raw material to webstorage',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../assets/financial-registry.js'),'utf8');assert.doesNotMatch(source,/\.innerHTML\s*=|\beval\s*\(|localStorage|operationKey\(/);assert.match(html,/financial-registry\.js\?v=/);assert.match(html,/预览 CSV（不保存、不计算）/);assert.match(html,/id="financial-registry-confirm"/);assert.match(source,/storage\?\.setItem\(slot\(meta.actor,meta.rid\),canonical\(meta\)\)/);
});


test('new save observes version without rebasing editor and rejects a later lower Root',async()=>{
 const f=await fixture();let seen=0;let r;const onObservedRoot=v=>{seen=Math.max(seen,v.research_version);r.scope.version=Math.max(r.scope.version,v.research_version);};r=runtime((url,o)=>{if(o.method==='POST'){r.root(4);return response(f.confirm);}return response(f.read);},{onObservedRoot});await prepare(r,f);await r.controller.confirm();assert.equal(seen,4);assert.equal(r.scope.version,4);assert.equal(r.scope.revision,1);assert.match(r.el('status').textContent,/已保存并核对读回/);r.root(3);await r.controller.readRecord(ref);assert.equal(seen,4);assert.equal(r.el('detail').textContent,'');
});

test('verified actor after reload clears only foreign financial descriptors',async()=>{
 const f=await fixture(),store=memory(),other='d'.repeat(64);store.setItem('structure-research-pending:financial-registry-v2:'+other+':'+rid,'{}');store.setItem('structure-research-pending:other-module','keep');const r=runtime(()=>response(f.list),{storage:store});r.root(4);await r.controller.history();assert.deepEqual([...store.values.entries()],[['structure-research-pending:other-module','keep']]);
});

test('canonical explicit pre-birth refusal retires the intent, malformed rejection keeps original key',async()=>{
 const f=await fixture();globalThis.location={origin:'https://beta.structural.bytedance.city'};
 for(const valid of [true,false]){const r=runtime(()=>{const payload={error:{code:'REVISION_CONFLICT',message:'问题或版本已变化。',retryable:false,allowed_next_actions:[],incident_id:uid(50)}};if(!valid)payload.extra=true;const response=new Response(JSON.stringify(payload),{status:409});Object.defineProperty(response,'url',{value:globalThis.location.origin+'/api/research/'+rid+'/financial-registries'});return response;});await prepare(r,f);await r.controller.confirm();assert.equal(r.controller.inspect().pending,!valid);assert.equal(r.requests.length,1);assert.equal(r.el('confirm').disabled,true);if(valid)assert.match(r.el('status').textContent,/原保存已明确拒绝/);else assert.match(r.el('status').textContent,/可能已经保存/);}
 delete globalThis.location;
});
