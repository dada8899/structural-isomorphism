const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/frontend/assets/research.js'),'utf8');
const funcs=source.slice(source.indexOf('  function clearFirstAnswer()'),source.indexOf("  byId('first-answer-retry').addEventListener"));
const id='11111111-1111-4111-8111-111111111111';
function harness({reason='unavailable',status='failed',http=200,pending=false,start=true}={}){
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,textContent:'',replaceChildren(){},append(){}});return nodes.get(id)};
 const calls=[];let resolveStart;
 const ctx={console,AbortController,setTimeout,clearTimeout,byId:node,
  fetch:async(url,options)=>{calls.push(options.method||'GET');return {status:http,ok:http===200,json:async()=>http===503?{error:{code:'FEATURE_UNAVAILABLE'}}:{contract_revision:'first-answer-job-v1',status,reason,metadata:{research_id:id,input_revision:1,problem_digest:'a'.repeat(64)}}}},
  authenticated:async()=>true,readOnlyView:()=>false,validId:()=>true,
  observationSync(){},revokeExternalStart(){},clearPrivateView(){},
  externalContext:()=>pending?{external_first_answer:'pending'}:{external_first_answer:'ready'},
  externalPanel:{reset(){calls.push('RESET')},start:async()=>{calls.push('START');assert.equal(node('first-answer').hidden,true);if(start==='defer')return new Promise(r=>resolveStart=r);if(start==='throw')throw Error('unknown');return start},offer:auto=>calls.push(auto?'OFFER_READ':'OFFER')},
 };
 vm.createContext(ctx);vm.runInContext(`let firstAnswerGeneration=0,firstAnswerController=null,firstAnswerJob=null,firstAnswerRefreshOnly=false;
 let accountScope='owner',researchId='${id}',editBase={revision:1,digest:'${'a'.repeat(64)}',researchVersion:1},externalStartIntent={};
 ${funcs}
 globalThis.test={readFirstAnswer,clearFirstAnswer,actor:()=>{accountScope='other'},revision:()=>{editBase.revision=2}};`,ctx);
 return {ctx,node,calls,finish:v=>resolveStart(v)};
}
(async()=>{
 let count=0;
 for(const http of [200,503])for(const outcome of [true,false,'throw']){
  const h=harness({http,start:outcome});await h.ctx.test.readFirstAnswer(true);
  assert.equal(h.node('first-answer').hidden,outcome===true,`${http}/${outcome}`);assert.equal(h.calls.filter(v=>v==='START').length,1);count++;
 }
 for(const mutate of ['clearFirstAnswer','actor','revision']){
  const h=harness({start:'defer'}),p=h.ctx.test.readFirstAnswer(true);
  await new Promise(r=>setImmediate(r));h.ctx.test[mutate]();h.node('first-answer').hidden=true;h.finish(false);await p;
  assert.equal(h.node('first-answer').hidden,true,mutate);count++;
 }
 for(const state of ['failed','interrupted']){
  const h=harness({status:state,pending:true});await h.ctx.test.readFirstAnswer(false);
  assert.equal(h.node('first-answer').hidden,true);assert(h.calls.includes('OFFER_READ'));assert(!h.calls.includes('START'));assert.deepEqual(h.calls.filter(v=>['GET','POST','DELETE'].includes(v)),['GET']);count++;
 }
 for(const [state,reason] of [['failed','insufficient'],['failed','local_error'],['cancelled','cancelled']]){
  const h=harness({status:state,reason});await h.ctx.test.readFirstAnswer(false);
  assert.equal(h.node('first-answer').hidden,false);assert(h.node('first-answer-status').textContent.length>0);assert(!h.calls.includes('START'));assert(!h.calls.includes('OFFER_READ'));count++;
 }
 const cancelled=harness({status:'cancelled',reason:'cancelled',pending:true});
 await cancelled.ctx.test.readFirstAnswer(false,'job');assert.equal(cancelled.node('first-answer').hidden,false);
 assert(!cancelled.calls.includes('START'));assert(!cancelled.calls.includes('OFFER_READ'));assert(cancelled.calls.includes('DELETE'));count++;
 // Actual unchanged panel module: recovery automatically reads the original status/result only.
 const api=require('../web/frontend/assets/externalFirstAnswer.js');
 class Element{constructor(doc){this.ownerDocument=doc;this.children=[];this.hidden=false;this.disabled=false;}append(...x){this.children.push(...x)}replaceChildren(){this.children=[]}setAttribute(){}addEventListener(){}}
 const doc={createElement:()=>new Element(doc)},panel=new Element(doc),methods=[];
 const anchor={research_id:id,input_revision:1,research_version:1,problem_digest:'a'.repeat(64),actor:'owner',operation_key:id,external_first_answer:'pending',recovery_only:true};
 const metadata=Object.fromEntries(['research_id','input_revision','research_version','problem_digest'].map(k=>[k,anchor[k]]));
 const mounted=api.mount(panel,{current:()=>anchor,inspect:async()=>{methods.push('GET status');return {contract_revision:'external-first-answer-v1',metadata,operation_key:id,status:'completed'}},loadResult:async()=>{methods.push('GET result');return {contract_revision:'external-first-answer-v1',metadata,operation_key:id,result_digest:'b'.repeat(64),schema:'external-first-answer-unverified-candidate-v1',review_required:true,candidate:{status:'candidate',explanation:'已保存解释',assumptions:['条件'],next_check:'后续核查',evidence_status:'not_checked'}}},submit:()=>{throw Error('MUST NOT SEND')}});
 mounted.offer(true);await new Promise(r=>setImmediate(r));assert.deepEqual(methods,['GET status','GET result']);assert.equal(panel.hidden,false);mounted.reset();assert.equal(panel.hidden,true);count++;
 const unknownPanel=new Element(doc),unknownMethods=[];
 api.mount(unknownPanel,{current:()=>anchor,inspect:async()=>{unknownMethods.push('GET status');return {contract_revision:'external-first-answer-v1',metadata,operation_key:id,status:'unknown'}},loadResult:()=>{throw Error('UNKNOWN MUST NOT LOAD RESULT')},submit:()=>{throw Error('UNKNOWN MUST NOT SEND')}}).offer(true);
 await new Promise(r=>setImmediate(r));assert.deepEqual(unknownMethods,['GET status']);assert.equal(unknownPanel.hidden,false);count++;
 console.log(`${count} status cases PASS; actual panel recovery GET status/result only`);
})().catch(e=>{console.error(e);process.exit(1)});
