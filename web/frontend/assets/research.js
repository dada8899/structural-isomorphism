/* The server is the authority. No generated research or local saved-state mock. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const form = byId('problem-form');
  // Keep first-time sign-in on the new research entry; legacy pages retain
  // their own default return target. Never carry private input in next.
  for (const link of [document.querySelector("header a[href='/auth/login']"), byId('access').querySelector("a[href='/auth/login']")]) {
    if (link) link.setAttribute('href', '/auth/login?next=%2Fresearch');
  }
  const schema = 'structure-research-v1';
  const revision = 'b1-candidate-01';
  let current = null;
  let editBase = null;
  let observed = null;
  let busy = false;
  let variables = [];
  let taskData = null;
  let taskBusy = false;
  let sourceBusy = false;
  let sourcePreview = null;
  let sourceApproval = null;
  let sourceRecordScope = null;
  let sourceRecordGeneration = 0;
  let sourcePreviewGeneration = 0;
  let privateGeneration = 0;
  let listGeneration = 0;
  let listCursor = null;
  let listBusy = false;
  let listSeen = new Set();
  let kbGeneration = 0;
  let kbBusy = false;
  let summaryEdited = false;
  let observationReview = null;
  let accountScope = null;
  let evidenceUI = null;
  let registryUI = null;
  let scenarioUI = null;
  let methodGeneration = 0;
  let methodSeen = false;
  let methodDirty = false;
  let historySeen = false;
  const financialState={epoch:0,busy:false,operation:null,controller:null,basis:null,previewVersion:null};
  const draftState={epoch:0,readEpoch:0,rid:null,target:null,busy:false,operation:null,actor:null,dirty:false,selected:new Map(),excerpts:new Map(),plans:new Map(),formulas:new Map(),history:new Map(),origin:null,supersedes:null,view:null,casRejected:null,catalog:new Map(),catalogNext:null,catalogCursors:new Set(),catalogGeneration:0,catalogKnown:false};
  const planState = {epoch:0,readGeneration:0,view:null,meta:null,preview:null,busy:false,operation:null,timer:null};
  const formulaState = {draft:null,snapshot:null,scope:null,view:null,dirty:false,loading:false,busy:false,busyToken:null,epoch:0,snapshotEpoch:0,metadata:null};
  const initialSection = ['#my-research', '#kb-section'].includes(location.hash) ? location.hash.slice(1) : null;
  let initialLoad = true;
  let entryPositioned = false;
  const initialPath = location.pathname.split('/').filter(Boolean);
  let researchId = initialPath.length === 2 ? initialPath[1] : null;
  const selectedTask = new URLSearchParams(location.search).get('task_id');
  const validId = value => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);

  function readOnlyView() { return selectedTask !== null || Boolean(editBase?.historical); }
  const recordTime = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(value) && Number.isFinite(Date.parse(value));
  function showTime(node, value) {
    node.textContent = ''; node.removeAttribute('datetime');
    if (recordTime(value)) { node.dateTime = value; node.textContent = new Intl.DateTimeFormat('zh-CN', {dateStyle:'medium',timeStyle:'long'}).format(new Date(value)); }
  }
  function clearMethod(message, hide = false) {
    byId('method-body').replaceChildren();
    byId('method-citations').replaceChildren();
    byId('method-meta').hidden = true;
    byId('method-record-details').hidden = true; byId('method-record-details').replaceChildren();
    byId('method-revision').textContent = '';
    byId('method-time').textContent = '';
    byId('method-time').removeAttribute('datetime');
    byId('method-status').textContent = message || '';
    byId('method-section').hidden = hide || !methodSeen;
  }
  function invalidateMethod(message = '本次未取得可展示的方法记录。请重新读取已保存版本。') {
    methodGeneration++;
    clearMethod(message);
  }
  function beginMethodRead() {
    planInvalidate('正在核对已保存记录，旧计划正文已收起。');
    invalidateMethod('正在核对已保存的方法记录…');
    return {generation:methodGeneration, researchId};
  }
  function methodFailure(token) {
    if (token?.generation === methodGeneration) clearMethod('本次未能核对方法记录，旧正文已收起。请重新读取已保存版本。');
  }
  async function methodRequest(url, options, token) {
    // Keep successful write receipts for original-key reconciliation and the
    // existing version checks; stale reads/errors must never clear a newer view.
    const active = response => (options?.method === 'POST' && response.ok) ||
      (token?.generation === methodGeneration && (!token.researchId || token.researchId === researchId));
    try { return await request(url,options,active); }
    catch (error) { methodFailure(token); throw error; }
  }
  function validMethod(data) {
    const value = data.method_result;
    const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
    const keys = (v, allowed) => object(v) && Object.keys(v).sort().join('|') === allowed.slice().sort().join('|');
    const integer = v => Number.isSafeInteger(v) && v > 0 && v <= 2147483647;
    const text = (v, max) => typeof v === 'string' && v.trim().length > 0 && Array.from(v).length <= max && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(v);
    const list = (v, max, check) => Array.isArray(v) && v.length <= max && v.every(check);
    const digest = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
    const handle = v => typeof v === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(v);
    try {
      if (!keys(value, ['schema_version','result_ref','input_revision','input_digest','candidate_schema','body_schema','producer_revision','received_at','candidate_digest','envelope_digest','is_historical','execution_mode','model_analysis_ran','status','evidence','assessment','review','sections','citations']) ||
          value.schema_version !== 'MethodHypothesisResultView-v1' || value.candidate_schema !== 'ModelReportCandidate-v1' ||
          value.body_schema !== 'OwnedMethodBody-v1' || value.producer_revision !== 'owned-method-offline-v1' ||
          !validId(value.result_ref) || !integer(value.input_revision) || !digest(value.input_digest) ||
          !digest(value.candidate_digest) || !digest(value.envelope_digest) || typeof data.is_historical !== 'boolean' || value.is_historical !== data.is_historical ||
          (data.is_historical && (!selectedTask || selectedTask !== data.task?.id)) ||
          (selectedTask !== null && selectedTask !== data.task?.id) ||
          value.execution_mode !== 'offline_probe' || value.model_analysis_ran !== false || value.status !== 'qualified_report' ||
          value.evidence !== 'INSUFFICIENT' || value.assessment !== 'llm_inference' || value.review !== 'unreviewed' ||
          typeof value.received_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(value.received_at) || !Number.isFinite(Date.parse(value.received_at)) ||
          data.research?.id !== researchId || !integer(data.research.current_revision) || !integer(data.research_version) || !integer(data.task_version) ||
          data.research.version !== data.research_version || !validId(data.task?.id) || data.task.version !== data.task_version ||
          data.task?.policy_revision !== 'bounded_usage_upper_v2' || data.execution !== 'COMPLETED' || data.task.execution !== 'COMPLETED' || data.task.stop_requested !== false ||
          data.research.current_task_id !== data.task.id || data.evidence !== 'INSUFFICIENT' || data.report_status !== 'qualified_report' || data.execution_mode !== 'offline_probe' ||
          (!data.is_historical && value.input_revision !== data.research.current_revision) ||
          value.input_revision > data.research.current_revision || data.current_problem?.research_id !== researchId || value.input_revision !== data.current_problem?.revision ||
          value.input_digest !== data.current_problem.digest || data.task.input_revision !== value.input_revision ||
          new TextEncoder().encode(JSON.stringify(value)).length > 512 * 1024) return null;
      if (!Array.isArray(value.citations) || value.citations.length < 1 || !list(value.citations, 20, citation => keys(citation,['handle','source_id','source_revision','excerpt_id','title','attribution','start','end','quote','extracted_digest']) &&
          handle(citation.handle) && validId(citation.source_id) && integer(citation.source_revision) && validId(citation.excerpt_id) &&
          text(citation.title,300) && text(citation.attribution,400) && text(citation.quote,1000) && digest(citation.extracted_digest) &&
          Number.isSafeInteger(citation.start) && Number.isSafeInteger(citation.end) && citation.start >= 0 && citation.end <= 200000 &&
          citation.end > citation.start && Array.from(citation.quote).length === citation.end - citation.start && citation.quote.trim().split(/\s+/).length <= 20)) return null;
      const handles = new Set(value.citations.map(citation => citation.handle));
      if (handles.size !== value.citations.length) return null;
      const section = value.sections;
      if (!keys(section,['summary','mechanisms','competing_explanations','validation_plan','gaps']) || !text(section.summary,1000) ||
          !list(section.mechanisms,3, mechanism => keys(mechanism,['label','mechanism','variable_map','conditions','nontransferable','evidence_handles']) &&
            text(mechanism.label,120) && text(mechanism.mechanism,1200) &&
            list(mechanism.variable_map,12, mapping => keys(mapping,['source','target','rationale']) && text(mapping.source,120) && text(mapping.target,120) && text(mapping.rationale,400)) &&
            list(mechanism.conditions,5,v => text(v,400)) && list(mechanism.nontransferable,5,v => text(v,400)) &&
            list(mechanism.evidence_handles,20,v => handle(v) && handles.has(v)) && new Set(mechanism.evidence_handles).size === mechanism.evidence_handles.length) ||
          !list(section.competing_explanations,5,v => text(v,400)) || !list(section.gaps,12,v => text(v,400)) ||
          !keys(section.validation_plan,['measurement','outcome','falsification','stop_rule']) ||
          !text(section.validation_plan.measurement,700) || !text(section.validation_plan.outcome,240) ||
          !text(section.validation_plan.falsification,400) || !text(section.validation_plan.stop_rule,400)) return null;
      return value;
    } catch (_error) { return null; }
  }
  function renderMethod(data, token) {
    if (!token || token.generation !== methodGeneration || (token.researchId && token.researchId !== data.research?.id)) return;
    methodSeen = methodSeen || data.task?.policy_revision === 'bounded_usage_upper_v2';
    if (data.method_result_state === 'unavailable') {
      clearMethod('本次未取得可展示的方法记录（正文当前不可用）；问题记录仍可访问。');
      status(readOnlyView() ? '方法正文当前不可用；所选问题仍可只读查看。' : '方法正文当前不可用；问题和草稿仍保留，可继续编辑。', true);
      return;
    }
    if (methodDirty) { clearMethod('表单有未保存改动，已收起旧方法记录。'); return; }
    if (['FAILED','CANCELLED','ACCESS_REVOKED'].includes(data.execution) || data.task?.stop_requested) {
      clearMethod('该流程已停止或未完成，本次没有可展示的方法正文。'); return;
    }
    const value = validMethod(data);
    if (!value) { clearMethod('本次未取得可展示的方法记录。请重新读取已保存版本。'); return; }
    methodSeen = true;
    clearMethod('离线流程演练，未运行真实模型。证据不足／未经独立评审；以下是待核的方法假说。');
    byId('method-meta').hidden = false;
    byId('method-revision').textContent = String(value.input_revision);
    showTime(byId('method-time'),value.received_at);
    const recordDetails = document.createElement('details'); const recordSummary = document.createElement('summary'); const recordRef = document.createElement('p');
    recordSummary.textContent = '记录编号'; recordRef.id = 'method-result-ref'; recordRef.textContent = value.result_ref;
    recordDetails.append(recordSummary,recordRef); byId('method-record-details').append(recordDetails); byId('method-record-details').hidden = false;
    byId('method-title').textContent = value.is_historical ? '历史方法假说记录' : '方法假说记录';
    const add = (parent, tag, content, className) => {
      const node = document.createElement(tag); node.textContent = content;
      if (className) node.className = className;
      parent.append(node); return node;
    };
    const group = (parent, title, values, heading = 'h4') => {
      if (!values.length) return;
      add(parent,heading,title); const list = document.createElement('ul');
      values.forEach(value => add(list,'li',value)); parent.append(list);
    };
    const body = byId('method-body');
    add(body,'h3','摘要'); add(body,'p',value.sections.summary);
    const citationIndex = new Map(value.citations.map((citation,index) => [citation.handle,index + 1]));
    value.sections.mechanisms.forEach((mechanism,index) => {
      const article = document.createElement('article'); article.className = 'method-mechanism';
      add(article,'h3',`机制假说 ${index + 1}：${mechanism.label}`); add(article,'p',mechanism.mechanism);
      if (mechanism.variable_map.length) {
        add(article,'h4','变量对应'); const mapping = document.createElement('dl'); mapping.className = 'method-mapping';
        mechanism.variable_map.forEach(item => { add(mapping,'dt',`${item.source} → ${item.target}`); add(mapping,'dd',item.rationale); }); article.append(mapping);
      }
      group(article,'适用条件待核',mechanism.conditions); group(article,'不可直接迁移的部分',mechanism.nontransferable);
      const references = document.createElement('div'); references.className = 'method-references';
      mechanism.evidence_handles.forEach(handle => {
        const number = citationIndex.get(handle); const button = add(references,'button',`查看引用 ${number}`,'secondary'); button.type = 'button';
        button.addEventListener('click',() => { const target = byId('method-citation-' + number); if (target) { target.scrollIntoView({block:'center'}); target.focus(); } });
      }); article.append(references); body.append(article);
    });
    if (!value.sections.mechanisms.length) add(body,'p','这份记录没有机制提名，仍需继续核对。','hint');
    group(body,'其他可能解释',value.sections.competing_explanations,'h3');
    add(body,'h3','验证计划'); const plan = value.sections.validation_plan;
    for (const [title,key] of [['观察与测量','measurement'],['比较结果','outcome'],['反证条件','falsification'],['停止条件','stop_rule']]) { add(body,'h4',title); add(body,'p',plan[key]); }
    group(body,'仍待补齐的部分',value.sections.gaps,'h3');
    const citations = byId('method-citations');
    if (value.citations.length) { add(citations,'h3','引用的原句'); add(citations,'p','引用只对应所列短句，不代表支持整份结论。','hint'); }
    value.citations.forEach((citation,index) => {
      const article = document.createElement('article'); article.className = 'method-citation'; article.id = 'method-citation-' + (index + 1); article.tabIndex = -1;
      add(article,'h4',`引用 ${index + 1}：${citation.title}`); add(article,'p',citation.attribution,'hint'); add(article,'blockquote',citation.quote); citations.append(article);
    });
  }


  // Formula drafts are plain editor data, never execution authority or a parser.
  const formulaChecks = {template:'登记模板',dimensions:'量纲与变量含义',canonical_transform:'标准变换',bounded_numeric:'有限采样'};
  const formulaTemplates = {little:'Little：在途量 = 到达率 × 时间',mm1:'M/M/1：系统时间',passive_decay:'一阶无输入储能恢复',linear_stable:'平衡附近局部恢复'};
  const formulaUnits = {one:'无量纲',count:'个',s:'秒',workday:'工作日',count_per_s:'个/秒',count_per_workday:'个/工作日',inverse_s:'1/秒',inverse_workday:'1/工作日',K:'K（温差）',J_per_K:'J/K',K_per_W:'K/W',V:'V',A:'A',ohm:'Ω',F:'F'};
  const formulaRoles = {l:'系统/队列内数量',lambda:'有效到达率',w:'系统/排队时间',mu:'服务容量',rho:'利用率',wq:'仅排队时间',lq:'仅队列数量',x:'状态差',t:'时间',r:'阻力参数',c:'容量参数',x0:'初始状态差',tau:'时间常数',delta:'局部状态差',k:'恢复率',delta0:'初始局部状态差'};
  const formulaQuantities = {system_count:'系统内数量',queue_count:'队列内数量',effective_arrival_rate:'有效到达率',service_capacity:'服务容量',system_time:'系统时间',queue_wait:'仅排队时间',ratio:'比率',state_difference:'状态差',time:'时间',thermal_resistance:'热阻',thermal_capacity:'热容',electrical_resistance:'电阻',electrical_capacity:'电容',initial_state_difference:'初始状态差',time_constant:'时间常数',local_state_difference:'局部状态差',recovery_rate:'恢复率',initial_local_state_difference:'初始局部状态差'};
  const formulaConditionNames = {same_boundary:'系统边界一致',finite_long_run_means:'长期均值有限',effective_arrivals:'使用有效到达率',same_population:'数量与时间对应同一群体',poisson_arrivals:'泊松到达',independent_exponential_service:'独立指数服务时间',single_server:'单服务台',fcfs:'先到先服务',infinite_capacity:'无限容量',no_abandonment:'无弃队',constant_parameters:'参数保持不变',stable_regime:'存在稳定状态',no_external_input:'没有外部输入',positive_parameters:'相关参数为正',lumped_state:'可用集总状态描述',constant_environment:'环境保持不变',ideal_isolated_rc:'理想孤立 RC',stable_equilibrium:'稳定平衡',local_linear:'局部线性',small_perturbation:'小扰动',fixed_equilibrium:'平衡位置固定'};
  const formulaConditionSets = {little:['same_boundary','finite_long_run_means','effective_arrivals','same_population'],mm1:['same_boundary','finite_long_run_means','effective_arrivals','same_population','poisson_arrivals','independent_exponential_service','single_server','fcfs','infinite_capacity','no_abandonment','constant_parameters','stable_regime'],passive_decay:['constant_parameters','no_external_input','positive_parameters'],linear_stable:['constant_parameters','no_external_input','positive_parameters','stable_equilibrium','local_linear','small_perturbation','fixed_equilibrium']};
  const formulaName = value => typeof value === 'string' && /^[a-z][a-z0-9_]{0,31}$/.test(value);
  function formulaNormalizeDecimal(value) {
    if(typeof value!=='string'||value.length>64||! /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?$/.test(value))throw Error('须填写有限十进制字符串。');
    const [mantissa,power='0']=value.toLowerCase().split('e');if(Math.abs(Number(power))>64)throw Error('十进制指数超出范围。');
    const negative=mantissa.startsWith('-');const plain=negative?mantissa.slice(1):mantissa;const [whole,fraction='']=plain.split('.');
    let digits=(whole+fraction).replace(/^0+/,'');if(!digits)return '0';let exponent=Number(power)-fraction.length;
    while(digits.endsWith('0')){digits=digits.slice(0,-1);exponent++;}
    const adjusted=digits.length-1+exponent;if(digits.length>18||adjusted < -12||adjusted>12)throw Error('数值精度或量级超出范围。');
    let rendered;
    if(exponent>0||adjusted < -6)rendered=digits[0]+(digits.length>1?'.'+digits.slice(1):'')+'E'+(adjusted>=0?'+':'')+adjusted;
    else if(exponent===0)rendered=digits;
    else {const place=digits.length+exponent;rendered=place>0?digits.slice(0,place)+'.'+digits.slice(place):'0.'+'0'.repeat(-place)+digits;}
    return (negative?'-':'')+rendered;
  }
  const formulaDecimal = value => {try {formulaNormalizeDecimal(value);return true;}catch{return false;}};
  function formulaScientificSide(value) {
    if(!value)return null;const side=formulaCopy(value);delete side.time_basis;
    for(const symbol of side.symbols)if(symbol.value!==null)symbol.value=formulaNormalizeDecimal(symbol.value);
    const normalize=node=>{if(!node)return;if(node.op==='const')node.value=formulaNormalizeDecimal(node.value);for(const child of Object.values(node))if(child&&typeof child==='object')normalize(child);};normalize(side.expression);
    for(const item of side.initial_conditions){item.at_time=formulaNormalizeDecimal(item.at_time);if(item.value!==null)item.value=formulaNormalizeDecimal(item.value);}
    return side;
  }
  const formulaDigest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const formulaCopy = value => JSON.parse(JSON.stringify(value));
  function formulaCanonical(value) { return JSON.stringify((function ordered(v) { return Array.isArray(v) ? v.map(ordered) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k=>[k,ordered(v[k])])) : v; })(value)); }
  async function formulaHash(value) { return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(formulaCanonical(value)))),n=>n.toString(16).padStart(2,'0')).join(''); }
  function formulaElement(parent,tag,text,options={}) {
    const node=document.createElement(tag); if (text!==null) node.textContent=text;
    for (const [key,value] of Object.entries(options)) { if (key==='className') node.className=value; else node.setAttribute(key,String(value)); }
    parent.append(node);return node;
  }
  function formulaField(parent,label,id,value,{select=null,multiline=false,max=400}={}) {
    const wrap=formulaElement(parent,'div',null,{className:'formula-field'});formulaElement(wrap,'label',label,{for:id});
    const field=formulaElement(wrap,select?'select':multiline?'textarea':'input',null,{id});
    if(select) for(const [key,name] of Object.entries(select)) formulaElement(field,'option',name,{value:key});
    else { if(!multiline)field.type='text';field.maxLength=max;if(multiline)field.rows=2; }
    field.value=value??'';return field;
  }
  function formulaChoice(parent,label,id,value) { return formulaField(parent,label,id,value===null?'':String(value),{select:{'':'未核对',true:'满足（用户声明）',false:'不满足'}}); }
  function formulaDefaultSide(side,template='little',domain='thermal') {
    const rows={little:[['l','count','system_count','12'],['lambda','count_per_s','effective_arrival_rate','3'],['w','s','system_time','4']],mm1:[['w','s','system_time','0.5'],['lambda','count_per_s','effective_arrival_rate','3'],['mu','count_per_s','service_capacity','5']],passive_decay:[['x',domain==='thermal'?'K':'V','state_difference',null],['t','s','time',null],['r',domain==='thermal'?'K_per_W':'ohm',domain==='thermal'?'thermal_resistance':'electrical_resistance',domain==='thermal'?'4':'5'],['c',domain==='thermal'?'J_per_K':'F',domain==='thermal'?'thermal_capacity':'electrical_capacity',domain==='thermal'?'2':'1']],linear_stable:[['delta','one','local_state_difference',null],['k','inverse_s','recovery_rate','0.25'],['t','s','time',null]]}[template];
    const conditions=[...formulaConditionSets[template],...(template==='passive_decay'?(domain==='thermal'?['lumped_state','constant_environment']:['ideal_isolated_rc']):[])];
    return {family:template==='little'||template==='mm1'?'queue_flow':template==='passive_decay'?'first_order_storage':'local_recovery',template_id:template,original_display:{little:'L = λ × W',mm1:'W = 1 / (μ − λ)',passive_decay:'C × d(x)/dt = −x / R',linear_stable:'d(δ)/dt = −k × δ'}[template],expression:null,symbols:rows.map(([role,unit_id,quantity,value])=>({id:side+'_'+role,role,unit_id,quantity,value})),assumptions:conditions.map(id=>({id,statement:formulaConditionNames[id],declared_satisfied:null})),initial_conditions:[],boundary_conditions:[],source_refs:[],measure_scope:'system',time_basis:'from_symbol_units'};
  }
  function formulaRegisteredTree(side) {
    const role=name=>({op:'symbol',id:side.symbols.find(v=>v.role===name)?.id||name});
    const binary=(op,left,right)=>({op,left,right});const constant=value=>({op:'const',value});
    const derivative=name=>({op:'derivative',state_symbol:role(name).id,time_symbol:role('t').id,order:1});
    if(side.template_id==='little')return binary('eq',role('l'),binary('mul',role('lambda'),role('w')));
    if(side.template_id==='mm1')return binary('eq',role('w'),binary('div',constant('1'),binary('sub',role('mu'),role('lambda'))));
    if(side.template_id==='passive_decay')return binary('eq',binary('mul',role('c'),derivative('x')),binary('div',{op:'neg',arg:role('x')},role('r')));
    return binary('eq',derivative('delta'),{op:'neg',arg:binary('mul',role('k'),role('delta'))});
  }
  function formulaNodeText(node,depth=0,count={n:0}) {
    if(!node)return '尚未填写结构；可保存草稿';if(depth>16||++count.n>128)throw Error('结构最多16层、128节点。');
    const text=n=>formulaNodeText(n,depth+1,count);
    if(node.op==='symbol')return node.id;if(node.op==='const')return formulaNormalizeDecimal(node.value);
    if(node.op==='derivative')return `d(${node.state_symbol})/d(${node.time_symbol})`;
    if(node.op==='neg')return `−(${text(node.arg)})`;if(node.op==='exp')return `exp(${text(node.arg)})`;
    if(node.op==='pow_int')return `(${text(node.base)})^${node.exponent}`;
    const marks={eq:'=',add:'+',sub:'−',mul:'×',div:'/'};
    if(!(node.op in marks))throw Error('结构中存在未登记运算。');return `(${text(node.left)} ${marks[node.op]} ${text(node.right)})`;
  }
  function validateFormulaNode(node,ids,count={n:0},depth=1) {
    if(!node||typeof node!=='object'||Array.isArray(node)||depth>16||++count.n>128)throw Error('结构须为受限节点，最多16层、128节点。');
    const fields=(...keys)=>Object.keys(node).sort().join('|')===keys.sort().join('|');
    if(node.op==='symbol'&&fields('op','id')&&ids.has(node.id))return;
    if(node.op==='const'&&fields('op','value')&&formulaDecimal(node.value))return;
    if(node.op==='derivative'&&fields('op','state_symbol','time_symbol','order')&&node.order===1&&ids.has(node.state_symbol)&&ids.has(node.time_symbol))return;
    let children;
    if(['neg','exp'].includes(node.op)&&fields('op','arg'))children=[node.arg];
    else if(['add','sub','mul','div','eq'].includes(node.op)&&fields('op','left','right')&&(node.op!=='eq'||depth===1))children=[node.left,node.right];
    else if(node.op==='pow_int'&&fields('op','base','exponent')&&Number.isInteger(node.exponent)&&Math.abs(node.exponent)<=2)children=[node.base];
    else throw Error('结构节点无效；请核对运算、变量与十进制常数。');
    children.forEach(child=>validateFormulaNode(child,ids,count,depth+1));
  }
  function validateFormulaDraft(draft) {
    if(!draft||draft.input_origin!=='user_provided'||!['expression','equation_form','initial_value_problem'].includes(draft.comparison_scope))throw Error('请选择公式比较范围。');
    if(!Array.isArray(draft.requested_checks)||!draft.requested_checks.length||new Set(draft.requested_checks).size!==draft.requested_checks.length||draft.requested_checks.some(v=>!Object.hasOwn(formulaChecks,v)))throw Error('至少选择一项已登记检查。');
    if(!draft.right&&draft.requested_checks.some(v=>!['template','dimensions'].includes(v)))throw Error('单式只能检查模板与量纲。');
    if(!Array.isArray(draft.sample_points)||draft.sample_points.length>256||new Set(draft.sample_points).size!==draft.sample_points.length||draft.sample_points.some(v=>!formulaDecimal(v)))throw Error('采样点须为不重复的十进制数，最多256个。');
    for(const side of [draft.left,draft.right].filter(Boolean)) {
      if(!Object.hasOwn(formulaTemplates,side.template_id)||side.family!==({little:'queue_flow',mm1:'queue_flow',passive_decay:'first_order_storage',linear_stable:'local_recovery'}[side.template_id]))throw Error('公式模板与家族不匹配。');
      if(typeof side.original_display!=='string'||!side.original_display.trim()||Array.from(side.original_display).length>2048)throw Error('原展示式须填写，最多2048字。');
      if(!Array.isArray(side.symbols)||side.symbols.length>12||new Set(side.symbols.map(v=>v.id)).size!==side.symbols.length||new Set(side.symbols.map(v=>v.role)).size!==side.symbols.length)throw Error('变量名称和角色须一一对应，每侧最多12项。');
      for(const symbol of side.symbols)if(!formulaName(symbol.id)||!formulaName(symbol.role)||!Object.hasOwn(formulaUnits,symbol.unit_id)||!formulaName(symbol.quantity)||(symbol.value!==null&&!formulaDecimal(symbol.value)))throw Error('请核对变量名、单位、含义和十进制数值；状态与时间值可留空。');
      if(side.expression!==null)validateFormulaNode(side.expression,new Set(side.symbols.map(v=>v.id)));
      const conditions=[...side.assumptions,...side.boundary_conditions];
      if(conditions.length+side.initial_conditions.length>24||side.initial_conditions.length>1||new Set(conditions.map(v=>v.id)).size!==conditions.length)throw Error('条件最多24项，初值最多1项，条件名称不可重复。');
      for(const item of conditions)if(!formulaName(item.id)||typeof item.statement!=='string'||!item.statement.trim()||Array.from(item.statement).length>400||![true,false,null].includes(item.declared_satisfied))throw Error('请填写条件说明及满足状态。');
      for(const item of side.initial_conditions)if(!formulaName(item.state_symbol)||!formulaDecimal(item.at_time)||(item.value!==null&&!formulaDecimal(item.value))||![true,false,null].includes(item.declared_satisfied))throw Error('请核对初值、时点和声明。');
      if(!['system','queue'].includes(side.measure_scope)||!['from_symbol_units','s','workday'].includes(side.time_basis))throw Error('请选择度量边界和时间基准。');
      if(!Array.isArray(side.source_refs)||side.source_refs.length>20)throw Error('来源引用过多。');
      for(const ref of side.source_refs)if(!validId(ref.id)||!Number.isSafeInteger(ref.revision)||ref.revision<1||!formulaDigest(ref.content_digest)||!['curated_reference','product_excerpt'].includes(ref.provenance)||typeof ref.locator!=='string'||ref.locator.length>300)throw Error('已保存来源引用无法核对，请重新读取。');
    }
    if(new TextEncoder().encode(formulaCanonical(draft)).length>65536)throw Error('公式草稿超过64KiB，请缩短输入；当前草稿未删除。');
    return draft;
  }
  function formulaDirty(message='公式草稿有修改，请保存新修订后再核对快照。') {
    if(readOnlyView())return;formulaState.dirty=true;formulaState.epoch++;formulaState.snapshotEpoch++;formulaState.loading=false;
    methodDirty=true;invalidateMethod('问题包含未保存的公式改动，旧方法记录已收起。');byId('formula-confirm').checked=false;
    evidenceUI?.invalidate('问题包含未保存的公式改动，外送预览已失效。',true);
    planInvalidate('公式草稿有未保存改动，旧计划已收起。');
    draftChanged('问题含未保存的公式改动；方法文字已保留，请先保存问题。');
    financialInvalidate('问题包含未保存公式，旧预览已失效；CSV 仍暂存在本页。');
    formulaClearResult(message);formulaPreview();syncFormulaControls();
  }
  function formulaClearResult(message='') { byId('formula-results').replaceChildren();byId('formula-status').textContent=message; }
  function formulaErrorText(error) {
    return error.status===413||error.code==='PAYLOAD_LIMIT'?'公式输入最多64KiB，结果最多512KiB。当前问题和草稿已保留，请缩短输入或重读原记录。':error.message;
  }
  function formulaPending() {
    if(!researchId)return [];
    const prefix='structure-research-pending:formula-check:'+researchId+':';const result=[];
    for(const key of Object.keys(sessionStorage))if(key.startsWith(prefix)) {try {const value=JSON.parse(sessionStorage.getItem(key));if(value?.key&&value.task_request)result.push({slot:key,...value});}catch{}}
    return result;
  }
  function syncFormulaControls() {
    const f=formulaState;const ro=readOnlyView();
    for(const control of byId('formula-editor').querySelectorAll('input,textarea,select,button'))control.disabled=busy||ro||f.loading;
    const selected=byId('formula-enable').checked;
    for(const control of byId('formula-fields').querySelectorAll('.formula-check-options input'))if(!f.draft?.right&&!['template','dimensions'].includes(control.value))control.disabled=true;
    if(ro)for(const field of byId('formula-editor').querySelectorAll('textarea')){field.style.height='';field.style.height=`${field.scrollHeight+2}px`;}
    byId('formula-confirm').disabled=ro||f.loading||f.busy||(['claimed','interrupted'].includes(f.metadata?.state)&&!f.metadata?.result_available)||!f.snapshot||f.dirty||methodDirty||!f.snapshot.executable;
    byId('formula-run').disabled=byId('formula-confirm').disabled||!byId('formula-confirm').checked;
    byId('formula-refresh').disabled=f.busy||f.loading||!researchId;
    byId('formula-recover').hidden=formulaPending().length===0;byId('formula-recover').disabled=ro||f.busy;
    byId('save').disabled=busy||ro||f.loading||(selected&&!f.draft);
    byId('formula-check-section').hidden=!(selected||f.scope?.meta||f.view?.formula_check||formulaPending().length);
    planSync();
    draftSync();
  }
  function formulaPreview() {
    for(const name of ['left','right']) {
      const side=formulaState.draft?.[name];const preview=byId('formula-'+name+'-preview');if(!side||!preview)continue;
      try {preview.textContent=formulaNodeText(side.expression);}catch(error){preview.textContent=error.message;}
    }
    if(!byId('formula-enable').checked)return;
    try {validateFormulaDraft(formulaState.draft);byId('formula-editor-status').textContent='草稿结构已登记；仍需保存并核对服务端快照，未执行任何数学检查。';}
    catch(error){byId('formula-editor-status').textContent=error.message;}
  }
  function formulaRenderTree(sideName) {
    const side=formulaState.draft[sideName],parent=byId('formula-'+sideName+'-tree');parent.replaceChildren();
    if(side.expression===null){formulaElement(parent,'p','尚无结构。可先保存草稿，或按“填入登记结构”后编辑。',{className:'hint'});return;}
    const variables=()=>Object.fromEntries(side.symbols.map(v=>[v.id,(formulaRoles[v.role]||v.role)+' · '+v.id]));
    const first=()=>side.symbols[0]?.id||sideName+'_x';
    const defaultNode=op=>op==='symbol'?{op,id:first()}:op==='const'?{op,value:'1'}:op==='derivative'?{op,state_symbol:first(),time_symbol:side.symbols.find(v=>v.role==='t')?.id||first(),order:1}:op==='pow_int'?{op,base:{op:'symbol',id:first()},exponent:1}:['neg','exp'].includes(op)?{op,arg:{op:'symbol',id:first()}}:{op,left:{op:'symbol',id:first()},right:{op:'const',value:'1'}};
    let rendered=0;
    function render(node,container,path,depth) {
      if(++rendered>128)return;
      if(depth>16){formulaElement(container,'p','结构超出16层限制。');return;}
      const row=formulaElement(container,'fieldset',null,{className:'formula-node'});formulaElement(row,'legend',path.length===1?'结构根节点':'子结构');
      const ops={symbol:'变量',const:'常数',add:'相加',sub:'相减',mul:'相乘',div:'相除',neg:'取负',exp:'指数',pow_int:'整数次幂',derivative:'一阶导数',...(path.length===1?{eq:'等式'}:{})};
      const id='formula-'+sideName+'-node-'+(path.join('-')||'root');const select=formulaField(row,'运算',id,node.op,{select:ops});
      select.addEventListener('change',()=>{let owner=side;for(const key of path.slice(0,-1))owner=owner[key];if(!path.length)side.expression=defaultNode(select.value);else owner[path.at(-1)]=defaultNode(select.value);formulaDirty();formulaRenderTree(sideName);syncFormulaControls();});
      const field=(label,key,value,choices=null)=>{const input=formulaField(row,label,id+'-'+key,value,{select:choices});input.addEventListener('input',()=>{node[key]=key==='exponent'?Number(input.value):input.value;formulaDirty();});};
      if(node.op==='symbol')field('引用变量','id',node.id,variables());else if(node.op==='const')field('十进制常数','value',node.value);
      else if(node.op==='derivative'){field('状态变量','state_symbol',node.state_symbol,variables());field('时间变量','time_symbol',node.time_symbol,variables());}
      else if(node.op==='pow_int'){field('指数','exponent',node.exponent,{'-2':'−2','-1':'−1',0:'0',1:'1',2:'2'});render(node.base,row,[...path,'base'],depth+1);}
      else if(['neg','exp'].includes(node.op))render(node.arg,row,[...path,'arg'],depth+1);
      else {render(node.left,row,[...path,'left'],depth+1);render(node.right,row,[...path,'right'],depth+1);}
    }
    // Paths start at expression, so edits replace only the selected node.
    render(side.expression,parent,['expression'],1);
    const rootSelect=parent.querySelector('select');if(side.expression.op==='eq'&&!Array.from(rootSelect.options).some(v=>v.value==='eq')){const option=document.createElement('option');option.value='eq';option.textContent='等式';rootSelect.append(option);rootSelect.value='eq';}
  }
  function formulaRenderSide(name) {
    const side=formulaState.draft[name],parent=byId('formula-'+name);parent.replaceChildren();if(!side){parent.hidden=true;return;}parent.hidden=false;
    formulaElement(parent,'h3',name==='left'?'左侧公式':'右侧公式');
    const template=formulaField(parent,'登记模板','formula-'+name+'-template',side.template_id,{select:formulaTemplates});
    template.addEventListener('change',()=>{const next=formulaDefaultSide(name,template.value);if(side.original_display!==formulaDefaultSide(name,side.template_id).original_display)next.original_display=side.original_display;next.source_refs=formulaCopy(side.source_refs);formulaState.draft[name]=next;formulaDirty();formulaRenderSide(name);syncFormulaControls();});
    if(side.template_id==='passive_decay'){
      const thermal=side.symbols.find(v=>v.role==='x')?.unit_id==='K'||side.symbols.find(v=>v.role==='r')?.unit_id==='K_per_W';
      const domain=formulaField(parent,'储能场景','formula-'+name+'-domain',thermal?'thermal':'electrical',{select:{thermal:'集总温差',electrical:'孤立 RC 电压'}});
      domain.addEventListener('change',()=>{const next=formulaDefaultSide(name,'passive_decay',domain.value);next.original_display=side.original_display;next.source_refs=formulaCopy(side.source_refs);formulaState.draft[name]=next;formulaDirty();formulaRenderSide(name);syncFormulaControls();});
    }
    const display=formulaField(parent,'原展示式（不会自动解析）','formula-'+name+'-display',side.original_display,{multiline:true,max:2048});display.addEventListener('input',()=>{side.original_display=display.value;formulaDirty();});
    const scope=formulaField(parent,'度量边界','formula-'+name+'-measure',side.measure_scope,{select:{system:'整个系统',queue:'仅队列'}});scope.addEventListener('change',()=>{side.measure_scope=scope.value;formulaDirty();});
    const basis=formulaField(parent,'时间基准','formula-'+name+'-basis',side.time_basis,{select:{from_symbol_units:'按已填变量单位',s:'秒',workday:'工作日'}});basis.addEventListener('change',()=>{side.time_basis=basis.value;formulaDirty();});
    formulaElement(parent,'h4','变量角色、单位与数值');const rows=formulaElement(parent,'div',null,{className:'formula-symbols'});
    side.symbols.forEach((symbol,index)=>{
      const row=formulaElement(rows,'fieldset',null,{className:'formula-symbol'});formulaElement(row,'legend',formulaRoles[symbol.role]||symbol.role);
      const prefix='formula-'+name+'-symbol-'+index;
      const id=formulaField(row,'结构内名称（字母开头）',prefix+'-id',symbol.id,{max:32});
      id.addEventListener('input',()=>{const previous=symbol.id;symbol.id=id.value;const rename=node=>{if(!node||typeof node!=='object')return;for(const key of ['id','state_symbol','time_symbol'])if(node[key]===previous)node[key]=symbol.id;for(const child of Object.values(node))if(child&&typeof child==='object')rename(child);};rename(side.expression);side.initial_conditions.forEach(v=>{if(v.state_symbol===previous)v.state_symbol=symbol.id;});formulaDirty();formulaRenderTree(name);syncFormulaControls();});
      const role=formulaField(row,'角色',prefix+'-role',symbol.role,{select:formulaRoles});role.addEventListener('change',()=>{symbol.role=role.value;formulaDirty();});
      const unit=formulaField(row,'单位',prefix+'-unit',symbol.unit_id,{select:formulaUnits});unit.addEventListener('change',()=>{symbol.unit_id=unit.value;formulaDirty();});
      const quantity=formulaField(row,'量的含义',prefix+'-quantity',symbol.quantity,{select:formulaQuantities});quantity.addEventListener('change',()=>{symbol.quantity=quantity.value;formulaDirty();});
      const value=formulaField(row,'数值（状态/时间可留空）',prefix+'-value',symbol.value,{max:40});value.addEventListener('input',()=>{symbol.value=value.value===''?null:value.value;formulaDirty();});
      const remove=formulaElement(row,'button','移除此变量',{type:'button',className:'secondary'});remove.addEventListener('click',()=>{side.symbols.splice(index,1);formulaDirty();formulaRenderSide(name);syncFormulaControls();});
    });
    const add=formulaElement(parent,'button','添加变量',{type:'button',className:'secondary'});add.addEventListener('click',()=>{if(side.symbols.length>=12)return;const role=Object.keys(formulaRoles).find(r=>!side.symbols.some(v=>v.role===r));side.symbols.push({id:name+'_'+role,role,unit_id:'one',quantity:'ratio',value:null});formulaDirty();formulaRenderSide(name);syncFormulaControls();});
    formulaElement(parent,'h4','结构式（与原文分别保存）');const actions=formulaElement(parent,'div',null,{className:'actions'});
    const use=formulaElement(actions,'button','填入登记结构',{type:'button',id:'formula-'+name+'-use-template',className:'secondary'});use.addEventListener('click',()=>{side.expression=formulaRegisteredTree(side);formulaDirty();formulaRenderTree(name);syncFormulaControls();});
    const clear=formulaElement(actions,'button','清空结构，仅存草稿',{type:'button',className:'secondary'});clear.addEventListener('click',()=>{side.expression=null;formulaDirty();formulaRenderTree(name);syncFormulaControls();});
    formulaElement(parent,'pre','',{id:'formula-'+name+'-preview',className:'formula-preview',tabindex:'0','aria-label':(name==='left'?'左':'右')+'侧结构式预览'});const editor=formulaElement(parent,'details',null,{id:'formula-'+name+'-structure-editor'});formulaElement(editor,'summary','调整结构节点（无需 JSON）');formulaElement(editor,'div',null,{id:'formula-'+name+'-tree'});formulaRenderTree(name);
    for(const group of ['assumptions','boundary_conditions']) {
      formulaElement(parent,'h4',group==='assumptions'?'条件（不是已验证事实）':'附加边界');
      side[group].forEach((condition,index)=>{
        const field=formulaElement(parent,'div',null,{className:'formula-condition'});const id='formula-'+name+'-'+group+'-'+index;
        const statement=formulaField(field,'条件说明',id+'-statement',condition.statement,{multiline:true,max:400});statement.addEventListener('input',()=>{condition.statement=statement.value;formulaDirty();});
        const declared=formulaChoice(field,'是否满足',id+'-declared',condition.declared_satisfied);declared.addEventListener('change',()=>{condition.declared_satisfied=declared.value===''?null:declared.value==='true';formulaDirty();});
      });
      if(group==='boundary_conditions'){const button=formulaElement(parent,'button','添加附加边界',{type:'button',className:'secondary'});button.addEventListener('click',()=>{if(side.assumptions.length+side.boundary_conditions.length+side.initial_conditions.length>=24)return;side.boundary_conditions.push({id:'extra_boundary_'+side.boundary_conditions.length,statement:'请填写边界；未登记条件可能不受支持',declared_satisfied:null});formulaDirty();formulaRenderSide(name);syncFormulaControls();});}
    }
    formulaElement(parent,'h4','初值（独立于状态变量数值）');const initialWrap=formulaElement(parent,'label',null,{className:'check'});const initialCheck=formulaElement(initialWrap,'input',null,{type:'checkbox',id:'formula-'+name+'-initial-enable'});initialCheck.checked=side.initial_conditions.length>0;initialWrap.append('登记一个初值');
    initialCheck.addEventListener('change',()=>{side.initial_conditions=initialCheck.checked?[{state_symbol:side.symbols.find(v=>['x','delta'].includes(v.role))?.id||side.symbols[0]?.id||name+'_x',at_time:'0',value:null,declared_satisfied:null}]:[];formulaDirty();formulaRenderSide(name);syncFormulaControls();});
    if(side.initial_conditions.length){const initial=side.initial_conditions[0];const choices=Object.fromEntries(side.symbols.map(v=>[v.id,(formulaRoles[v.role]||v.role)+' · '+v.id]));const state=formulaField(parent,'初值对应状态','formula-'+name+'-initial-state',initial.state_symbol,{select:choices});state.addEventListener('change',()=>{initial.state_symbol=state.value;formulaDirty();});for(const [label,key] of [['初值时点','at_time'],['初值数值','value']]){const input=formulaField(parent,label,'formula-'+name+'-initial-'+key,initial[key],{max:40});input.addEventListener('input',()=>{initial[key]=key==='value'&&input.value===''?null:input.value;formulaDirty();});}const declared=formulaChoice(parent,'初值是否已核对','formula-'+name+'-initial-declared',initial.declared_satisfied);declared.addEventListener('change',()=>{initial.declared_satisfied=declared.value===''?null:declared.value==='true';formulaDirty();});}
    formulaElement(parent,'p',side.source_refs.length?`保留 ${side.source_refs.length} 项已登记来源；保存与读取均由服务端重新核对权限。`:'来源：用户提供，未登记文献引用。',{className:'hint'});
    if(side.source_refs.length){const removeRefs=formulaElement(parent,'button','本修订不引用原来源（用户提供）',{type:'button',className:'secondary'});removeRefs.addEventListener('click',()=>{side.source_refs=[];formulaDirty();formulaRenderSide(name);syncFormulaControls();});}
    formulaPreview();
  }


  function formulaRenderEditor() {
    const draft=formulaState.draft;byId('formula-fields').hidden=!byId('formula-enable').checked||!draft;
    if(!draft){byId('formula-left').replaceChildren();byId('formula-right').replaceChildren();syncFormulaControls();return;}
    byId('formula-use-right').checked=Boolean(draft.right);byId('formula-scope').value=draft.comparison_scope;
    for(const field of byId('formula-fields').querySelectorAll('.formula-check-options input'))field.checked=draft.requested_checks.includes(field.value);
    byId('formula-samples').value=draft.sample_points.join(', ');
    formulaRenderSide('left');formulaRenderSide('right');formulaPreview();syncFormulaControls();
  }
  function formulaReset() {
    const f=formulaState;f.epoch++;f.snapshotEpoch++;f.draft=null;f.snapshot=null;f.scope=null;f.view=null;f.metadata=null;f.dirty=false;f.loading=false;f.busy=false;f.busyToken=null;f.refreshToken=null;
    byId('formula-enable').checked=false;byId('formula-confirm').checked=false;byId('formula-editor-status').textContent='';byId('formula-platform').textContent='';formulaClearResult();
    byId('formula-left').replaceChildren();byId('formula-right').replaceChildren();byId('formula-fields').hidden=true;byId('formula-check-section').hidden=true;
  }
  function formulaProblemEdited() {
    formulaState.epoch++;byId('formula-confirm').checked=false;
    formulaClearResult('问题草稿有修改，已收起旧公式结果；请保存后重新核对。');syncFormulaControls();
  }
  function formulaAuthUncertain() {
    formulaState.epoch++;formulaState.snapshotEpoch++;formulaState.loading=false;formulaState.snapshot=null;
    byId('formula-confirm').checked=false;formulaClearResult('账户状态尚待核对，已收起公式结果；本页输入仍保留。');syncFormulaControls();
  }
  function formulaTicket() { return {epoch:formulaState.epoch,privateScope:privateGeneration,rid:researchId,task:selectedTask}; }
  function formulaActive(ticket) { return ticket.epoch===formulaState.epoch&&ticket.privateScope===privateGeneration&&ticket.rid===researchId&&ticket.task===selectedTask; }
  function formulaTakeDraft() {
    if(!byId('formula-enable').checked)return undefined;
    if(formulaState.loading||!formulaState.draft)throw Error('公式快照尚未读全。请重读，或明确取消本修订的公式草稿；不会自动覆盖为缺失公式。');
    return formulaCopy(validateFormulaDraft(formulaState.draft));
  }
  async function formulaHydrate(data) {
    formulaReset();const f=formulaState;f.view=data;
    const problem=data.current_problem,meta=problem.formula_snapshot;
    f.scope={rid:data.research.id,revision:problem.revision,problemDigest:problem.digest,researchVersion:data.research_version,meta:meta||null};
    formulaPlatform(data);
    if(!meta){syncFormulaControls();return;}
    byId('formula-enable').checked=true;f.loading=true;byId('formula-editor-status').textContent='正在按当前权限读取已保存的公式快照…';syncFormulaControls();
    const epoch=++f.snapshotEpoch,privateScope=privateGeneration,scope=f.scope;
    const active=()=>epoch===f.snapshotEpoch&&privateScope===privateGeneration&&scope===f.scope&&scope.rid===researchId;
    try {
      if(!Number.isSafeInteger(meta.revision)||meta.revision!==problem.revision||!formulaDigest(meta.formula_digest)||meta.input_origin!=='user_provided')throw Error('公式快照元数据无法核对。');
      const body=await request(`/api/research/${researchId}/formula-revisions/${meta.revision}`,{},active);
      if(!active())return;
      if(body.state==='unavailable'&&body.formula===null){byId('formula-editor-status').textContent='公式快照当前不可读取；问题仍可编辑。请重读，或明确取消本修订的公式草稿。';formulaClearResult('公式与验证结果当前不可用。');return;}
      if(body.state!=='available'||body.formula_digest!==meta.formula_digest||body.display_assessment!=='user_confirmation_required_AST_only'||body.source_facts_verified!==false)throw Error('公式快照范围无法核对。');
      const raw=body.formula;if(!raw||new TextEncoder().encode(formulaCanonical(raw)).length>65536)throw Error('公式快照超过64KiB或格式无效。');
      for(const side of [raw.left,raw.right].filter(Boolean))if(!validId(side.id)||side.revision!==scope.revision)throw Error('公式原修订无法核对。');
      if(await formulaHash(raw)!==meta.formula_digest)throw Error('公式快照摘要不匹配。');if(!active())return;
      const draft=formulaCopy(raw);delete draft.executable;for(const side of [draft.left,draft.right].filter(Boolean)){delete side.id;delete side.revision;}
      validateFormulaDraft(draft);
      const executable=[draft.left,draft.right].filter(Boolean).every(v=>v.expression!==null);
      if(raw.executable!==executable||meta.executable!==executable)throw Error('公式结构状态无法核对。');
      f.snapshot={raw:formulaCopy(raw),executable,digest:meta.formula_digest};f.draft=draft;f.dirty=false;formulaRenderEditor();
      byId('formula-editor-status').textContent=executable?'已按权限读取原公式快照。检查前请核对展示式与结构式；修改后须保存新修订。':'这份快照仍缺结构，只能作为草稿；请补充后保存新修订。';
      f.loading=false;syncFormulaControls();
      if(data.formula_check&&data.task?.policy_revision==='local-formula-v1')await formulaReadResult(data.formula_check,data.task.id);
    } catch(error) {if(active()){byId('formula-editor-status').textContent='公式快照未能核对。'+formulaErrorText(error);formulaClearResult('未取得可展示的公式结果。问题输入仍保留。');}}
    finally {if(active()){f.loading=false;syncFormulaControls();}}
  }
  function formulaPlatform(data) {
    const capability=data.capabilities?.formula_checks;
    byId('formula-platform').textContent=capability?.host_supported===true?'执行器会在运行时核对 Linux 隔离能力；任务完成不等于各项检查通过。':'当前环境不支持受保护的隔离计算。提交检查仅会保存“未执行/不支持”的真实回执，不会在界面模拟数学通过。';
  }
  function formulaObserve(data) {
    const f=formulaState;f.view=data;formulaPlatform(data);
    if(!f.scope||!f.snapshot||f.loading||f.dirty||methodDirty)return;
    if(data.current_problem.revision!==f.scope.revision||data.current_problem.digest!==f.scope.problemDigest){f.epoch++;f.metadata=null;f.snapshot=null;formulaClearResult('服务端问题版本已变化；本页输入未替换，请明确重新读取。');syncFormulaControls();return;}
    const metadata=data.task?.policy_revision==='local-formula-v1'?data.formula_check:null;
    if(!metadata){if(f.metadata){f.epoch++;f.metadata=null;formulaClearResult('当前流程没有公式验证记录；旧结果须从原流程只读打开。');}syncFormulaControls();return;}
    f.epoch++;formulaReadResult(metadata,data.task.id).catch(()=>{});
  }
  function validateFormulaMetadata(meta,expectedRef) {
    return meta&&validId(meta.result_ref)&&(!expectedRef||meta.result_ref===expectedRef)&&['claimed','returned','closed','interrupted'].includes(meta.state)&&
      typeof meta.result_available==='boolean'&&meta.input_origin==='user_provided'&&(meta.formula_digest===null||formulaDigest(meta.formula_digest))&&
      (meta.formula_result_recorded_at===null||recordTime(meta.formula_result_recorded_at))&&meta.math_status===null&&
      ['not_attested','reaped','pending'].includes(meta.termination_state)&&meta.task_completed_means_math_passed===false&&meta.known_cost_units===0;
  }
  async function formulaValidateResult(data,meta,taskId) {
    const f=formulaState,raw=f.snapshot.raw,scope=f.scope,result=data.result,proof=data.provenance;
    if(data.state!=='available'||!validateFormulaMetadata(data.metadata,meta.result_ref)||data.metadata.state!=='returned'||!data.metadata.result_available||!recordTime(data.metadata.formula_result_recorded_at)||data.metadata.formula_digest!==f.snapshot.digest)throw Error('公式结果元数据无法核对。');
    if(!proof||typeof proof.execution_attested!=='boolean'||!['ok','unsupported','limited','memory_limited','failed'].includes(proof.execution_state)||proof.execution_attested!==(proof.execution_state==='ok')||proof.reaped!==true||!validId(proof.owned_return_ref)||!formulaDigest(proof.code_version)||proof.formula_digest!==f.snapshot.digest||proof.problem_digest!==scope.problemDigest||proof.display_AST_confirmation!=='user_confirmed_snapshot'||proof.source_origin!=='user_provided'||proof.source_facts_verified!==false||proof.mathematics_is_not_real_world_mechanism!==true)throw Error('独立执行来源无法核对。');
    const side=formulaScientificSide;
    const input={research_id:scope.rid,input_revision:scope.revision,task_id:taskId,attempt:1,comparison_scope:raw.comparison_scope,left:side(raw.left),right:side(raw.right),requested_checks:raw.requested_checks,sample_points:raw.sample_points.map(formulaNormalizeDecimal)};
    const inputDigest=await formulaHash(input);
    if(proof.execution_attested&&proof.resource_guard!=='linux_as_baseline_plus_128mib_cpu1s_wall2s')throw Error('没有登记的 Linux 隔离执行证明。');
    if(proof.execution_state==='unsupported'&&proof.resource_guard!=='not_executed')throw Error('不支持平台的执行状态无法核对。');
    if(result&&new TextEncoder().encode(formulaCanonical(result)).length>524288)throw Error('公式结果超过512KiB；原问题与原记录仍保留。');
    if(!result||result.schema_version!=='formula-content-view-v1'||result.comparison_scope!==raw.comparison_scope||result.policy_revision!=='formula-policy-v1-d2-candidate'||result.content_input_digest!==inputDigest||proof.full_input_digest!==inputDigest||!formulaDigest(result.content_output_digest)||proof.output_digest!==result.content_output_digest||result.authorization_verified!==false||result.execution_attested!==false||result.source_facts_verified!==false||result.display_checked!==false)throw Error('公式结果内容范围无法核对。');
    const forms=[raw.left,raw.right].filter(Boolean);
    if(!Array.isArray(result.provided_formula_refs)||result.provided_formula_refs.length!==forms.length||!Array.isArray(result.formula_displays)||result.formula_displays.length!==forms.length)throw Error('公式输入引用无法核对。');
    for(let i=0;i<forms.length;i++){
      const source=forms[i],ref=result.provided_formula_refs[i],display=result.formula_displays[i];
      if(ref.id!==source.id||ref.revision!==scope.revision||ref.formula_digest!==await formulaHash(side(source))||ref.checked_representation!=='validated_AST'||display.side!==(i===0?'left':'right')||display.original_display!==source.original_display||formulaCanonical(display.checked_AST)!==formulaCanonical(side(source).expression)||formulaCanonical(display.symbols)!==formulaCanonical(side(source).symbols)||formulaCanonical(display.declared_assumptions)!==formulaCanonical(source.assumptions)||formulaCanonical(display.declared_initial_conditions)!==formulaCanonical(side(source).initial_conditions)||formulaCanonical(display.declared_boundary_conditions)!==formulaCanonical(source.boundary_conditions)||display.declaration_assessment!=='not_verified_by_public_adapter')throw Error('原展示式与被检查结构不匹配。');
    }
    if(!Array.isArray(result.outcomes)||formulaCanonical(result.outcomes.map(v=>v.check_kind))!==formulaCanonical(raw.requested_checks))throw Error('检查项目集合无法核对。');
    for(const outcome of result.outcomes){
      if(!['passed','failed','inconclusive','unsupported','resource_limit'].includes(outcome.status)||!['algebraic_identity','conditional_model_equivalence','local_approximation','partial_structure','not_equivalent','undetermined'].includes(outcome.relation)||typeof outcome.reason!=='string'||outcome.reason.length>400||!Array.isArray(outcome.trace)||outcome.trace.length>64||!Array.isArray(outcome.samples)||outcome.samples.length>256)throw Error('分项结果格式无法核对。');
      if(outcome.check_kind!=='canonical_transform'&&!['undetermined','not_equivalent'].includes(outcome.relation))throw Error('采样或量纲不能被提升为恒等证明。');
      if(outcome.check_kind!=='bounded_numeric'&&(outcome.samples.length||outcome.tolerance!==null))throw Error('采样范围不匹配。');
      if(outcome.samples.length&&formulaCanonical(outcome.samples.map(v=>v.point))!==formulaCanonical(raw.sample_points.map(formulaNormalizeDecimal)))throw Error('原采样点无法核对。');
      for(const sample of outcome.samples)if(typeof sample.passed!=='boolean'||!['exact','abs1e-10_rel1e-8_normalized_only'].includes(sample.comparison)||!sample.left||!sample.right||typeof sample.left.value!=='string'||typeof sample.right.value!=='string')throw Error('采样值格式无效。');
      if(!proof.execution_attested&&outcome.status==='passed')throw Error('未执行的回执不能显示数学通过。');
      if(outcome.samples.length&&outcome.status!==(outcome.samples.every(v=>v.passed)?'passed':'failed'))throw Error('采样状态与所列点不一致。');
      if(proof.execution_state==='unsupported'&&(outcome.status!=='unsupported'||outcome.relation!=='undetermined'||outcome.samples.length))throw Error('不支持的平台不能给出已通过结论。');
    }
    const sourceMap=new Map();for(const form of forms)for(const ref of form.source_refs)sourceMap.set(ref.id,{id:ref.id,revision:ref.revision,content_digest:ref.content_digest,declared_provenance:ref.provenance,reference_status:'supplied_reference_not_authorized_here',locator_exposed:false});
    if(formulaCanonical(result.source_references)!==formulaCanonical(Array.from(sourceMap.values())))throw Error('公式来源登记范围无法核对。');
    if(!Array.isArray(result.limitations)||result.limitations.length>100||result.limitations.some(v=>typeof v!=='string'||v.length>2000)||!Array.isArray(result.source_references)||result.source_references.length>40)throw Error('结果边界信息无法核对。');
    return {result,proof,metadata:data.metadata};
  }
  async function formulaReadResult(meta,taskId) {
    const f=formulaState;if(!f.snapshot||!f.scope||f.dirty||methodDirty||!validId(taskId)||!validateFormulaMetadata(meta)||meta.formula_digest!==f.snapshot.digest||(selectedTask&&taskId!==selectedTask))return;
    f.metadata=formulaCopy(meta);const ticket=formulaTicket(),snapshot=f.snapshot;formulaClearResult('正在读取原验证记录…');syncFormulaControls();
    try {
      const data=await request(`/api/research/${researchId}/formula-results/${meta.result_ref}`,{},()=>formulaActive(ticket)&&f.snapshot===snapshot);
      if(!formulaActive(ticket)||f.snapshot!==snapshot)return;
      if(data.state==='unavailable'&&data.result===null){byId('formula-confirm').checked=false;if(data.metadata?.state==='returned')f.snapshot=null;formulaClearResult(['claimed','interrupted'].includes(data.metadata?.state)?'检查状态仍待核对，当前没有结果；请重读原记录，不重复启动。':'公式验证记录当前不可用；问题与本页草稿仍保留。');return;}
      const checked=await formulaValidateResult(data,meta,taskId);if(!formulaActive(ticket)||f.snapshot!==snapshot)return;
      f.metadata=checked.metadata;formulaShowResult(checked);
    } catch(error){if(formulaActive(ticket)){formulaClearResult('未取得可展示的公式结果。'+formulaErrorText(error));byId('formula-confirm').checked=false;}}
    finally {if(formulaActive(ticket))syncFormulaControls();}
  }
  function formulaShowResult({result,proof,metadata}) {
    formulaClearResult(proof.execution_attested?'已读取真实隔离执行回执；数学结论须逐项查看。':'已保存未执行或未完成的回执；没有隔离计算成功证明。');
    const parent=byId('formula-results');const saved=formulaElement(parent,'p',null,{className:'hint'});saved.append('验证记录保存时间 ');const time=formulaElement(saved,'time','',{id:'formula-result-time'});showTime(time,metadata.formula_result_recorded_at);
    const details=formulaElement(parent,'details',null);formulaElement(details,'summary','验证记录编号');formulaElement(details,'p',metadata.result_ref,{id:'formula-result-ref'});
    formulaElement(parent,'p','范围：'+({expression:'结构表达式',equation_form:'声明条件下的模型 / 方程形式',initial_value_problem:'初值问题'}[result.comparison_scope])+'。来源为用户提供；条件、文献和现实机制未经本检查验证。',{className:'scope'});
    for(const display of result.formula_displays){const card=formulaElement(parent,'article',null,{className:'formula-original'});formulaElement(card,'h3',display.side==='left'?'左侧原式与被检查结构':'右侧原式与被检查结构');formulaElement(card,'p',display.original_display);formulaElement(card,'pre',formulaNodeText(display.checked_AST));const conditions=[...display.declared_assumptions,...display.declared_boundary_conditions];if(conditions.length)formulaElement(card,'p','条件声明：'+conditions.map(v=>v.statement+'：'+(v.declared_satisfied===null?'未核对':v.declared_satisfied?'用户声明满足':'不满足')).join('；'),{className:'hint'});}
    const statuses={passed:'此项通过',failed:'此项不满足',inconclusive:'条件不足 / 未判定',unsupported:'不支持',resource_limit:'资源限制，未完成'};
    const relations={algebraic_identity:'代数恒等（限本结构式）',conditional_model_equivalence:'声明条件下的模型等价',local_approximation:'仅局部近似',partial_structure:'仅部分结构对应',not_equivalent:'不等价',undetermined:'关系未判定'};
    const traceNames={constant_fold:'常数合并',commute:'交换次序',associate:'结合重排',rename_bijection:'按角色一一对应',substitute_constant:'代入常数',multiply_nonzero:'乘以非零量',divide_nonzero:'除以非零量',positive_time_scale:'正时间尺度变换',state_normalize:'状态归一'};
    for(const [kind,label] of Object.entries(formulaChecks)){
      const outcome=result.outcomes.find(v=>v.check_kind===kind);const article=formulaElement(parent,'article',null,{className:'formula-outcome','data-check':kind});formulaElement(article,'h3',label);
      if(!outcome){formulaElement(article,'p','本次未选择此项。');continue;}
      formulaElement(article,'p',statuses[outcome.status]+' · '+relations[outcome.relation],{className:'formula-outcome-status','data-status':outcome.status});formulaElement(article,'p','返回依据：'+outcome.reason,{className:'hint'});
      if(outcome.trace.length){const list=formulaElement(article,'ol',null);outcome.trace.forEach(step=>formulaElement(list,'li',(traceNames[step.kind]||'未登记变换')+(step.precondition_ids?.length?'；前提：'+step.precondition_ids.map(v=>formulaConditionNames[v]||v).join('、'):'')));}
      if(outcome.samples.length){const list=formulaElement(article,'ul',null);for(const sample of outcome.samples){const value=v=>v.value+(v.physical_time!==undefined?'；实际时间 '+v.physical_time+' 秒':'')+(v.actual_state!==null&&v.actual_state!==undefined?'；实际状态 '+v.actual_state:'');formulaElement(list,'li',`点 ${sample.point}：左 ${value(sample.left)}；右 ${value(sample.right)}；${sample.passed?'本点一致':'本点不一致'}`);}formulaElement(article,'p','有限采样只针对所列点。归一结果一致不证明恒等、现实因果或迁移成功。',{className:'hint'});}
    }
    if(result.limitations.length){const list=formulaElement(parent,'ul',null,{className:'hint'});result.limitations.forEach(v=>formulaElement(list,'li',v));}
  }
  function formulaRetire(pending) {try {const saved=JSON.parse(sessionStorage.getItem(pending.slot));if(saved?.key===pending.key)sessionStorage.removeItem(pending.slot);}catch{}}
  async function formulaConfirmAck(ack,payload,ticket) {
    if(!validateFormulaMetadata(ack)||!validId(ack.task_id)||ack.formula_digest!==payload.formula_digest)throw Error('检查回执格式或公式绑定尚未确认。');
    const samePrivate=()=>ticket.privateScope===privateGeneration&&ticket.rid===researchId;
    if(!samePrivate())throw Error('账户读取范围已变化，原操作保留待核对。');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try {
      // This is acknowledgment verification, not a current-view read. An
      // untrusted task404 cannot clear a newer form or acknowledge the POST.
      const response=await fetch(`/api/research/${ticket.rid}?task_id=${encodeURIComponent(ack.task_id)}`,{credentials:'same-origin',cache:'no-store',signal:controller.signal});
      if(!samePrivate())throw Error('账户读取范围已变化，原操作保留待核对。');
      // A task selector may be wrong while the owner still has access. Only
      // a current ticket probes the trusted root; discard its view, never rebase.
      if(response.status===404&&formulaActive(ticket)) {
        try {await request(`/api/research/${ticket.rid}`,{},()=>formulaActive(ticket));}
        catch {throw Error('检查回执尚未确认，原key保留待核对。');}
      }
      // Confirm identity loss through the shared gate, retaining the unknown key.
      if(response.status===401&&formulaActive(ticket))await authenticated(()=>formulaActive(ticket),controller.signal);
      const envelope=await response.json();if(!samePrivate())throw Error('账户读取范围已变化，原操作保留待核对。');
      if(response.status===409&&envelope.error?.code==='AUTHORIZATION_STALE'&&formulaActive(ticket)) {
        await authenticated(()=>formulaActive(ticket),controller.signal);
        if(!samePrivate())throw Error('账户读取范围已变化，原操作保留待核对。');
      }
      const view=envelope.data,stored=view?.formula_check,anchor=view?.task_history?.[0];
      if(!response.ok||envelope.schema_version!==schema||envelope.contract_revision!==revision||view?.research?.id!==ticket.rid||view.task?.id!==ack.task_id||view.task.policy_revision!=='local-formula-v1'||view.task.input_revision!==payload.input_revision||view.current_problem?.revision!==payload.input_revision||view.current_problem.formula_snapshot?.revision!==payload.input_revision||view.current_problem.formula_snapshot.formula_digest!==payload.formula_digest||!validateFormulaMetadata(stored,ack.result_ref)||stored.formula_digest!==payload.formula_digest||anchor?.task_id!==ack.task_id||anchor.input_revision!==payload.input_revision||anchor.input_digest!==view.current_problem.digest||anchor.start_version!==payload.expected_research_version+1)throw Error('检查回执尚未与原请求绑定，原key保留待核对。');
    } finally {clearTimeout(timer);}
  }
  async function formulaStart(recover=false) {
    const f=formulaState;if(readOnlyView()||f.busy||busy||!researchId)return;
    let payload,pending;
    try {
      if(recover){const original=formulaPending()[0];if(!original)throw Error('没有待核对的公式操作。');payload=original.task_request;pending={key:original.key,slot:original.slot};}
      else {
        if(!f.snapshot||!f.scope||f.dirty||methodDirty||!f.snapshot.executable||!byId('formula-confirm').checked)throw Error('请先保存并读取完整公式快照，核对展示式与结构式。');
        payload={input_revision:f.scope.revision,expected_research_version:f.scope.researchVersion,formula_digest:f.snapshot.digest,confirm_formula_input:true};
      }
      if(!Number.isSafeInteger(payload.input_revision)||!Number.isSafeInteger(payload.expected_research_version)||!formulaDigest(payload.formula_digest)||payload.confirm_formula_input!==true)throw Error('原检查请求无法核对。');
      const body=JSON.stringify({schema_version:schema,contract_revision:revision,data:payload});
      if(!pending)pending=await operationKey(`formula-check:${researchId}:${payload.input_revision}:${payload.formula_digest}`,body,payload.input_revision,payload);
      f.epoch++;const ticket=formulaTicket(),operation=Symbol();f.busy=true;f.busyToken=operation;byId('formula-confirm').checked=false;formulaClearResult(recover?'正在核对原操作；不会检查当前未保存草稿。':'正在请求已保存公式的检查；结果以真实回执为准。');syncFormulaControls();
      try {
        const ack=await request(`/api/research/${researchId}/formula-checks`,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':pending.key},body},response=>response.ok||formulaActive(ticket));
        await formulaConfirmAck(ack,payload,ticket);
        formulaRetire(pending);if(!formulaActive(ticket))return;
        const view=await request(viewUrl(),{},()=>formulaActive(ticket));if(!formulaActive(ticket))return;
        const token=beginMethodRead();renderTask(view,{methodToken:token});
        if(!f.snapshot||!f.scope||f.scope.revision!==payload.input_revision||f.snapshot.digest!==payload.formula_digest||f.dirty||methodDirty||view.task?.id!==ack.task_id){
          formulaClearResult('原操作已确认，当前草稿和流程未替换。');const link=formulaElement(byId('formula-results'),'a','新标签页只读查看原验证记录',{href:`/research/${researchId}?task_id=${ack.task_id}`,target:'_blank',rel:'noopener'});return;
        }
        await formulaReadResult(ack,ack.task_id);
      } catch(error){if(pending&&error.status>=400&&error.status<500)formulaRetire(pending);if(formulaActive(ticket)){byId('formula-confirm').checked=false;formulaClearResult(error.status?formulaErrorText(error):'检查状态尚未确认。请保留本页输入，用原操作核对；不会另启重复计算。');}}
      finally {if(f.busyToken===operation){f.busy=false;f.busyToken=null;}if(ticket.privateScope===privateGeneration&&ticket.rid===researchId)syncFormulaControls();}
    } catch(error){formulaClearResult(error.message);syncFormulaControls();}
  }
  function initFormula() {
    byId('formula-enable').addEventListener('change',()=>{if(readOnlyView())return;if(byId('formula-enable').checked){formulaState.draft={input_origin:'user_provided',comparison_scope:'expression',left:formulaDefaultSide('left'),right:formulaDefaultSide('right'),requested_checks:Object.keys(formulaChecks),sample_points:['0']};}else{formulaState.draft=null;formulaState.snapshot=null;}formulaDirty(byId('formula-enable').checked?undefined:'本次新修订将不包含公式；原修订仍保留。');formulaRenderEditor();});
    byId('formula-use-right').addEventListener('change',()=>{if(readOnlyView()||!formulaState.draft)return;formulaState.draft.right=byId('formula-use-right').checked?formulaDefaultSide('right'):null;if(!formulaState.draft.right)formulaState.draft.requested_checks=formulaState.draft.requested_checks.filter(v=>['template','dimensions'].includes(v));formulaDirty();formulaRenderEditor();});
    byId('formula-scope').addEventListener('change',()=>{if(!readOnlyView()&&formulaState.draft){formulaState.draft.comparison_scope=byId('formula-scope').value;formulaDirty();}});
    for(const field of byId('formula-fields').querySelectorAll('.formula-check-options input'))field.addEventListener('change',()=>{if(!readOnlyView()&&formulaState.draft){formulaState.draft.requested_checks=Array.from(byId('formula-fields').querySelectorAll('.formula-check-options input:checked'),v=>v.value);formulaDirty();}});
    byId('formula-samples').addEventListener('input',()=>{if(!readOnlyView()&&formulaState.draft){formulaState.draft.sample_points=byId('formula-samples').value.split(',').map(v=>v.trim()).filter(Boolean);formulaDirty();}});
    byId('formula-confirm').addEventListener('change',syncFormulaControls);byId('formula-run').addEventListener('click',()=>formulaStart(false));byId('formula-recover').addEventListener('click',()=>formulaStart(true));
    byId('formula-refresh').addEventListener('click',async()=>{
      const f=formulaState;if(f.busy||f.loading||!researchId)return;
      if(f.dirty||methodDirty){formulaClearResult('本页有未保存改动。请先保存，或明确重新读取已存版本；不会覆盖草稿。');return;}
      const ticket=formulaTicket(),refreshToken=Symbol();f.refreshToken=refreshToken;f.loading=true;byId('formula-confirm').checked=false;
      byId('formula-editor-status').textContent='正在重新读取已保存公式…';formulaClearResult('正在核对原快照与记录，旧结果已收起。');syncFormulaControls();
      try {
        const data=await request(viewUrl(),{},()=>formulaActive(ticket));if(!formulaActive(ticket))return;
        if(data.current_problem?.revision!==editBase?.revision||data.current_problem?.digest!==editBase?.digest){observeServer(data);editNotice();f.epoch++;f.snapshot=null;formulaClearResult('服务端问题版本已变化，请明确重新读取已存版本；本页原问题和公式输入未替换。');return;}
        const methodToken=beginMethodRead();renderTask(data,{methodToken});await formulaHydrate(data);
      } catch(error){if(formulaActive(ticket))formulaClearResult('公式未能重读。'+formulaErrorText(error));}
      finally {if(f.refreshToken===refreshToken){f.refreshToken=null;f.loading=false;syncFormulaControls();}}
    });
  }

  // A plan is a purpose-bound record, never execution authority or evidence.
  const planContract = 'funded-plan-v2';
  const planStates = {queued:'已排队，尚未确认生成结果',generating:'正在处理，结果尚待核对',saved:'计划已保存，研究判断仍待核验',failed_insufficient:'本次未取得可展示的完整计划',pending_reconciliation:'请求结果与费用待核对，不会自动重试',cancelled:'后续执行已停止'};
  const planObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const planKeys = (value, keys) => planObject(value) && Object.keys(value).sort().join('|') === keys.slice().sort().join('|');
  const planInt = value => Number.isSafeInteger(value) && value > 0 && value <= 2147483647;
  const planUnits = value => Number.isSafeInteger(value) && value >= 0;
  const planMoney = value => {const units=BigInt(value);return String(units/1000000n)+'.'+String(units%1000000n).padStart(6,'0');};
  const planText = (value, max, min=1) => typeof value === 'string' && Array.from(value).length >= min && Array.from(value).length <= max && value.trim().length > 0 && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(value);
  const planRef = value => typeof value === 'string' && /^[A-Za-z0-9._:-]{1,100}$/.test(value);
  const planDigest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const planError = error => ['AbortError','TypeError','SyntaxError'].includes(error.name)?'本次计划状态尚未确认，请保留输入与原操作。':error.message;
  function planTicket(read=false) { return {epoch:planState.epoch,privateScope:privateGeneration,rid:researchId,task:selectedTask,...(read?{read:planState.readGeneration}:{})}; }
  function planActive(ticket) { return ticket.epoch===planState.epoch&&ticket.privateScope===privateGeneration&&ticket.rid===researchId&&ticket.task===selectedTask&&(ticket.read===undefined||ticket.read===planState.readGeneration); }
  function planClearBody() {
    byId('native-plan-body').replaceChildren();byId('native-plan-record').hidden=true;
    byId('native-plan-result-ref').textContent='';byId('native-plan-record-revision').textContent='';showTime(byId('native-plan-record-time'),null);
    byId('native-plan-query-area').hidden=true;byId('native-plan-query-draft').value='';
  }
  function planInvalidate(message='') {
    planState.epoch++;planState.readGeneration++;planState.preview=null;clearTimeout(planState.timer);planState.timer=null;
    byId('native-plan-consent').checked=false;byId('native-plan-preview-panel').hidden=true;byId('native-plan-exact-input').textContent='';byId('native-plan-quote').textContent='';
    planClearBody();if(message)byId('native-plan-status').textContent=message;planSync();
  }
  function planReset() {
    planInvalidate();planState.view=null;planState.meta=null;planState.busy=false;planState.operation=null;
    byId('native-plan-own').checked=false;byId('native-plan-status').textContent='';byId('native-plan-history').replaceChildren();byId('native-plan-history-status').textContent='';byId('native-plan-section').hidden=true;
  }
  function planPending() {
    if(!researchId)return null;const slot='structure-research-pending:native-plan-v2-confirm:'+researchId;
    try {const value=JSON.parse(sessionStorage.getItem(slot));return value?.key&&value.task_request?{...value,slot}:null;}catch{return null;}
  }
  function planAnchor(data) {
    const problem=data?.current_problem,task=data?.task;
    if(data?.research?.id!==researchId||problem?.research_id!==researchId||!planInt(problem?.revision)||!planDigest(problem?.digest)||!validId(task?.id)||task.input_revision!==problem.revision||task.input_digest!==problem.digest||
      !planInt(data.research_version)||data.research.version!==data.research_version||data.task_version!==task.version||!planInt(task.version)||typeof data.is_historical!=='boolean'||!['native-plan-v1','funded-plan-v1'].includes(task.policy_revision)||(selectedTask!==null&&task.id!==selectedTask))return null;
    if(task.policy_revision==='native-plan-v1'&&!['controlled_fixture','native_live'].includes(task.execution_mode))return null;
    return {rid:researchId,task_id:task.id,input_revision:problem.revision,input_digest:problem.digest,policy:task.policy_revision,execution_mode:task.execution_mode};
  }
  function planMeta(value,legacy=false) {
    const fields=legacy?['task_id','result_ref','state','financial_state','safe_code','recorded_at','plan_generation_ran','real_model_executed','execution_mode','approved_upper_units','usage']:
      ['task_id','result_ref','state','financial_version','execution_mode','real_model_executed','cost_state','cleanup_state','safe_code','recorded_at'];
    return planKeys(value,fields)&&planRef(value.task_id)&&planRef(value.result_ref)&&Object.hasOwn(planStates,value.state)&&
      [null,'access_ended','saved','body_invalid','send_unknown','not_sent','cancelled'].includes(value.safe_code)&&(value.recorded_at===null||recordTime(value.recorded_at))&&
      typeof value.real_model_executed==='boolean'&&(legacy?value.execution_mode==='fixture'&&value.real_model_executed===false&&typeof value.plan_generation_ran==='boolean'&&planUnits(value.approved_upper_units)&&['unreserved','held','upper_booked','unknown'].includes(value.financial_state):
      value.financial_version===9&&[null,'controlled_fixture','native_live'].includes(value.execution_mode)&&['unreserved','held','upper_booked','unknown'].includes(value.cost_state)&&['pending','clean','uncertain'].includes(value.cleanup_state));
  }
  function planUncertain(meta) { return meta&&(meta.state==='pending_reconciliation'||meta.cost_state==='unknown'||meta.cleanup_state==='uncertain'); }
  function planSync() {
    const ro=readOnlyView(),pending=planPending(),p=planState.preview;
    byId('native-plan-section').hidden=form.hidden||!researchId;
    const conflict=editBase&&observed&&(observed.revision!==editBase.revision||observed.digest!==editBase.digest);
    const eligible=researchId&&editBase&&current?.current_problem?.entry==='phenomenon'&&current.current_problem.confirmed&&!methodDirty&&!formulaState.dirty&&!conflict;
    byId('native-plan-own').disabled=ro||busy||planState.busy||!eligible;
    byId('native-plan-preview').disabled=ro||busy||planState.busy||!eligible||!byId('native-plan-own').checked||Boolean(pending);
    const expires=Boolean(p&&Date.now()<p.expires_at*1000);
    byId('native-plan-consent').disabled=ro||busy||planState.busy||!eligible||!p?.can_confirm||!expires||Boolean(pending);
    byId('native-plan-confirm').disabled=byId('native-plan-consent').disabled||!byId('native-plan-consent').checked;
    byId('native-plan-recover').hidden=!pending;byId('native-plan-recover').disabled=ro||busy||planState.busy||planUncertain(planState.meta);
    byId('native-plan-refresh').disabled=!researchId||busy||planState.busy;
    byId('native-plan-query-draft').disabled=ro;
    byId('native-plan-use-query').disabled=ro||busy||planState.busy||!taskData?.capabilities?.source_evidence||!planText(byId('native-plan-query-draft').value,160,3);
    if(!researchId)byId('native-plan-hint').textContent='先保存并核对自己的现象自述，再预览下一步研究计划。';
    else if(ro)byId('native-plan-hint').textContent='固定流程只读查看原记录；要生成新计划，请返回当前问题。';
    else if(methodDirty||formulaState.dirty)byId('native-plan-hint').textContent='本页有未保存改动。先保存，再预览；待核对操作始终使用原请求，不会发送当前草稿。';
    else byId('native-plan-hint').textContent='仅支持已保存的8–1000字自己的观察自述。预览不会调用模型；明确确认后才可进入执行队列。';
  }
  async function planAuthenticate(ticket) {
    if(!planActive(ticket))return false;
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try {return await authenticated(()=>planActive(ticket),controller.signal);}finally{clearTimeout(timer);}
  }
  async function planRequest(url,options,ticket,purpose='v2') {
    if(!planActive(ticket))throw Error('较早的计划请求已失效，未追加读取或外发。');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try {
      const response=await fetch(url,{...options,credentials:'same-origin',cache:'no-store',signal:controller.signal});
      if(!planActive(ticket))throw Error('较早的计划响应已失效，原操作保留待核对。');
      const envelope=await response.json();if(!planActive(ticket))throw Error('较早的计划响应已失效，原操作保留待核对。');
      if(!response.ok) {
        if(response.status===401||envelope.error?.code==='AUTHORIZATION_STALE')await authenticated(()=>planActive(ticket),controller.signal);
        else if(response.status===404&&planActive(ticket)) {
          // A bad result/task reference does not prove loss of the trusted rid.
          try {await request(`/api/research/${ticket.rid}`,{},()=>planActive(ticket));}catch{}
        }
        const error=Error(envelope.error?.message||'本次计划状态无法核对，请保留草稿与原操作。');error.code=envelope.error?.code;
        // Read/reference errors never acknowledge a pending confirmation.
        if(['preview','confirm'].includes(purpose)&&planActive(ticket)){error.status=response.status;error.planPurpose=purpose;}
        throw error;
      }
      const expected=purpose==='bind'?revision:purpose==='legacy'?'funded-plan-v1':planContract;
      if(envelope.schema_version!==schema||envelope.contract_revision!==expected||!planObject(envelope.data))throw Error('计划响应的用途或版本无法核对，原操作已保留。');
      return envelope.data;
    } finally {clearTimeout(timer);}
  }
  function planValidatePreview(value,anchor) {
    const quote=value?.quote;
    if(!planKeys(value,['preview_ref','preview_digest','request_digest','research_id','input_revision','expected_research_version','exact_input','purpose','observation_rights','state','can_confirm','funding_reason','cash_evidence','approved_upper_units','currency','scale','quote','expires_at','explanation'])||
      !planRef(value.preview_ref)||!planDigest(value.preview_digest)||!planDigest(value.request_digest)||value.research_id!==anchor.rid||value.input_revision!==anchor.input_revision||value.expected_research_version!==anchor.research_version||value.exact_input!==anchor.original_input||!planText(value.exact_input,1000,8)||
      value.purpose!=='phenomenon_plan_v1'||value.observation_rights!=='self_declared'||!['awaiting_confirmation','funding_closed'].includes(value.state)||typeof value.can_confirm!=='boolean'||value.can_confirm!==(value.state==='awaiting_confirmation')||value.funding_reason!==(value.can_confirm?null:'FUNDING_CLOSED')||value.cash_evidence!=='not_observed'||
      !planUnits(value.approved_upper_units)||value.currency!=='CNY'||value.scale!==6||!Number.isSafeInteger(value.expires_at)||!planText(value.explanation,160)||!planObject(quote)||quote.protocol!=='financial9-native-quote-v1'||quote.purpose!=='phenomenon_plan_v1'||quote.provider!=='deepseek'||quote.model!=='deepseek-flash'||!planText(quote.declared_model_version,120)||quote.currency!=='CNY'||quote.scale!==6||quote.approved_upper_units!==value.approved_upper_units||quote.valid_until!==value.expires_at||!planDigest(quote.codec_digest))throw Error('外发原文、版本或费用上界无法完整核对，未开放确认。');
    return value;
  }
  function planCandidate(value) {
    const list=(a,max,check,min=0)=>Array.isArray(a)&&a.length>=min&&a.length<=max&&a.every(check);
    if(!planKeys(value,['summary','candidates','query_suggestions','gaps','clarification_questions'])||!planText(value.summary,700)||
      !list(value.candidates,3,v=>planKeys(v,['label','mechanism_hypothesis','why_considered','method_leads','key_unknowns'])&&planText(v.label,120)&&planText(v.mechanism_hypothesis,700)&&planText(v.why_considered,400)&&list(v.method_leads,2,s=>planText(s,160))&&list(v.key_unknowns,5,s=>planText(s,240),1))||
      !list(value.query_suggestions,5,v=>planKeys(v,['candidate_index','query','intent'])&&(v.candidate_index===null||Number.isSafeInteger(v.candidate_index)&&v.candidate_index>=0&&v.candidate_index<value.candidates.length)&&planText(v.query,160,3)&&/^[\x20-\x7e]+$/.test(v.query)&&planText(v.intent,240))||
      !list(value.gaps,8,s=>planText(s,400),1)||!list(value.clarification_questions,3,s=>planText(s,240))||(!value.candidates.length&&!value.query_suggestions.length&&!value.clarification_questions.length)||new Set(value.query_suggestions.map(v=>v.query.trim().replace(/\s+/g,' ').toLowerCase())).size!==value.query_suggestions.length||new TextEncoder().encode(JSON.stringify(value)).length>16384)throw Error('计划正文格式无法完整核对，未展示旧内容。');
    return value;
  }
  function planValidateResult(value,meta,anchor,legacy,pending) {
    const fields=['protocol','purpose','result_ref','task_id','research_id','input_revision','input_digest','request_digest','admission_digest','recorded_at','execution_mode','real_model_executed','literature_status','mathematics_status','mechanism_status','observation_rights','query_state','automatically_created_sources','proposal'];
    if(legacy)fields.push('plan_generation_ran');else fields.push('consent_digest','producer','weight_identity_verified');
    if(!planKeys(value,fields)||value.protocol!==(legacy?'owned-phenomenon-plan-result-v1':'owned-native-plan-result-v2')||value.purpose!=='phenomenon_plan_v1'||value.research_id!==anchor.rid||value.task_id!==anchor.task_id||value.result_ref!==meta.result_ref||value.input_revision!==anchor.input_revision||value.input_digest!==anchor.input_digest||!planDigest(value.request_digest)||!planDigest(value.admission_digest)||value.recorded_at!==meta.recorded_at||!recordTime(value.recorded_at)||
      value.literature_status!=='not_retrieved'||value.mathematics_status!=='not_checked'||value.mechanism_status!=='unverified'||value.observation_rights!=='self_declared'||value.query_state!=='draft_only'||value.automatically_created_sources!==0||meta.state!=='saved'||
      (legacy?value.execution_mode!=='fixture'||value.real_model_executed!==false||value.plan_generation_ran!==true:
      !planDigest(value.consent_digest)||value.weight_identity_verified!==false||!['controlled_fixture','native_live'].includes(value.execution_mode)||!['core-controlled-native-v1','owned-native-plan-runtime-v1'].includes(value.producer)||typeof value.real_model_executed!=='boolean'||value.real_model_executed!==(value.execution_mode==='native_live')||(value.producer==='core-controlled-native-v1'&&value.execution_mode!=='controlled_fixture')||value.execution_mode!==meta.execution_mode||value.execution_mode!==anchor.execution_mode||value.real_model_executed!==meta.real_model_executed))throw Error('计划记录与原问题、流程或执行来源无法绑定。');
    if(pending&&(pending.task_request.anchor.input_revision!==value.input_revision||pending.task_request.anchor.input_digest!==value.input_digest||pending.task_request.data.request_digest!==value.request_digest))throw Error('计划回执与原提交无法绑定，原key仍保留。');
    planCandidate(value.proposal);return value;
  }
  function planPendingFor(meta) {const pending=planPending();return pending?.receipt?.task_id===meta.task_id&&pending.receipt.result_ref===meta.result_ref?pending:null;}
  function planShow(meta,legacy=false) {
    const financial=legacy?meta.financial_state:meta.cost_state;
    const money={unreserved:'尚未预留执行上限',held:'本次上限仍被占用，不是最终实扣',upper_booked:'按上限记账，实际扣费数字尚未确认',unknown:'费用结果尚未确认，原操作与占用保留'};
    byId('native-plan-status').textContent=`${planStates[meta.state]}。${money[financial]||'费用状态待核对'}。`+(!legacy&&meta.cleanup_state==='uncertain'?'资源清理尚未确认，新增执行已停止；请保留原操作。':!legacy&&meta.cleanup_state==='pending'?'资源清理仍待完成，原提交暂时保留；可稍后重新读取状态。':'');
  }
  function planDisplay(value,ticket) {
    planClearBody();byId('native-plan-record').hidden=false;byId('native-plan-record-revision').textContent=String(value.input_revision);showTime(byId('native-plan-record-time'),value.recorded_at);byId('native-plan-result-ref').textContent=value.result_ref;
    const body=byId('native-plan-body'),add=(parent,tag,text,options={})=>formulaElement(parent,tag,text,options);
    add(body,'p',value.execution_mode==='native_live'?'本次记录来自原生模型请求；权重身份未验证，以下只是待核验计划。':value.execution_mode==='fixture'?'历史离线夹具记录，未运行真实模型。':'受控夹具执行记录，未运行真实模型。');
    add(body,'p','文献尚未检索 · 数学关系尚未核对 · 现实机制未经验证 · 自述权属仅为用户声明',{className:'scope'});
    const provenance=add(body,'details','');add(provenance,'summary','执行记录的边界');add(provenance,'p',`执行来源：${value.producer==='owned-native-plan-runtime-v1'?'原生请求运行通道':value.producer==='core-controlled-native-v1'?'项目受控夹具通道':'旧版本地演练通道'}。真实模型执行：${value.real_model_executed?'是':'否'}；模型权重身份未验证。`);
    add(body,'h3','下一步查什么');add(body,'p',value.proposal.summary);
    const group=(parent,title,items)=>{if(!items.length)return;add(parent,'h4',title);const list=add(parent,'ul','');for(const item of items)add(list,'li',item);};
    value.proposal.candidates.forEach((candidate,index)=>{const article=add(body,'article','',{className:'native-plan-candidate'});add(article,'h3',`待核验方向 ${index+1}：${candidate.label}`);add(article,'p',candidate.mechanism_hypothesis);add(article,'h4','为什么考虑');add(article,'p',candidate.why_considered);group(article,'可查找的方法线索',candidate.method_leads);group(article,'仍需核对',candidate.key_unknowns);});
    group(body,'缺口',value.proposal.gaps);group(body,'需要补充的问题',value.proposal.clarification_questions);
    if(value.proposal.query_suggestions.length){add(body,'h3','可手选的英文查询草稿');add(body,'p','选择只填写下方可编辑草稿；不会自动查询来源、批准读取或再次调用模型。',{className:'hint'});}
    for(const suggestion of value.proposal.query_suggestions){const row=add(body,'article','',{className:'native-plan-query'});add(row,'p',suggestion.query);add(row,'p',suggestion.intent,{className:'hint'});const button=add(row,'button','选作可编辑查询草稿',{type:'button',className:'secondary'});button.disabled=readOnlyView();button.addEventListener('click',()=>{if(!planActive(ticket)||readOnlyView())return;byId('native-plan-query-draft').value=suggestion.query;byId('native-plan-query-area').hidden=false;planSync();byId('native-plan-query-draft').focus();});}
  }
  async function planRetireKnownTerminal(meta,anchor,ticket) {
    if(!planActive(ticket)||meta.cleanup_state!=='clean')return false;
    // Only tuples emitted by the current native worker are terminal proof.
    const tuple=[meta.state,meta.safe_code,meta.cost_state].join(':');
    const expected={
      'failed_insufficient:body_invalid:upper_booked':{execution:'FAILED',time:true},
      'failed_insufficient:not_sent:unreserved':{execution:'FAILED',time:false},
      'cancelled:cancelled:unreserved':{execution:'CANCELLED',time:false},
      'cancelled:access_ended:upper_booked':{execution:'CANCELLED',time:true},
    }[tuple];
    if(!expected||(expected.time?!recordTime(meta.recorded_at):meta.recorded_at!==null))return false;
    const pending=planPendingFor(meta),original=pending?.task_request,data=original?.data,scope=original?.anchor;
    if(!pending||pending.slot!=='structure-research-pending:native-plan-v2-confirm:'+anchor.rid||!validId(pending.key)||!planDigest(pending.digest)||
      !planKeys(data,['preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units','confirm_outbound'])||!planRef(data.preview_ref)||!planDigest(data.preview_digest)||!planDigest(data.request_digest)||!planInt(data.expected_research_version)||!planUnits(data.approved_upper_units)||data.confirm_outbound!==true||
      scope?.rid!==anchor.rid||scope.input_revision!==anchor.input_revision||scope.input_digest!==anchor.input_digest||scope.research_version!==data.expected_research_version||anchor.policy!=='native-plan-v1'||anchor.task_id!==meta.task_id)return false;
    const body=JSON.stringify({schema_version:schema,contract_revision:planContract,data});
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(body))),n=>n.toString(16).padStart(2,'0')).join('');
    if(!planActive(ticket)||hash!==pending.digest)return false;
    // Re-read the original fixed task after the terminal GET, without rendering
    // or rebasing it. Page generation is a liveness ticket, not stored identity.
    const bound=await planRequest(`/api/research/${anchor.rid}?task_id=${encodeURIComponent(anchor.task_id)}`,{},ticket,'bind');
    if(!planActive(ticket))return false;
    const actual=planAnchor(bound),projected=bound.native_plan,first=bound.task_history?.[0],task=bound.task;
    const stop=task?.stop_requested===true||task?.stop_requested===1;
    if(!actual||actual.rid!==anchor.rid||actual.task_id!==anchor.task_id||actual.input_revision!==scope.input_revision||actual.input_digest!==scope.input_digest||actual.policy!=='native-plan-v1'||task.execution!==expected.execution||
      (expected.execution==='CANCELLED'&&!stop)||!planInt(task.start_version)||task.start_version!==data.expected_research_version+1||first?.task_id!==task.id||first.input_revision!==scope.input_revision||first.input_digest!==scope.input_digest||first.start_version!==task.start_version||!planMeta(projected)||
      ['task_id','result_ref','state','financial_version','execution_mode','real_model_executed','cost_state','cleanup_state','safe_code','recorded_at'].some(key=>projected[key]!==meta[key]))return false;
    if(!await planAuthenticate(ticket)||!planActive(ticket))return false;
    const current=planPendingFor(meta);if(current?.key!==pending.key||current.digest!==hash)return false;
    formulaRetire(pending);return true;
  }
  async function planRead(meta,anchor,ticket,legacy=false,display=true) {
    try {
      const value=await planRequest(`/api/research/${anchor.rid}/plan-results/${encodeURIComponent(meta.result_ref)}`,{},ticket,legacy?'legacy':'v2');
      if(!planActive(ticket))return;const {content,...metadata}=value;
      if(!planMeta(metadata,legacy)||metadata.task_id!==anchor.task_id||metadata.result_ref!==meta.result_ref||(meta.recorded_at!==null&&metadata.recorded_at!==meta.recorded_at))throw Error('计划状态或原记录时间无法核对。');
      if(display){planState.meta=metadata;planShow(metadata,legacy);}
      if(content!==null){const pending=legacy?null:planPendingFor(metadata);const result=planValidateResult(content,metadata,anchor,legacy,pending);if(!planActive(ticket))return;if(display)planDisplay(result,ticket);
        if(pending&&!planUncertain(metadata)&&metadata.cleanup_state==='clean')formulaRetire(pending);
      }else if(metadata.state==='saved')throw Error('已保存的计划正文尚未读全，原操作仍保留。');
      else if(!legacy)await planRetireKnownTerminal(metadata,anchor,ticket);
      planSync();return metadata;
    }catch(error){if(planActive(ticket)){if(display)planClearBody();byId('native-plan-status').textContent=planError(error);planSync();}return null;}
  }
  function planObserve(data,read=true) {
    if(planState.preview&&planState.preview.expected_research_version!==data.research_version)planInvalidate('已保存的流程版本有变化，请重新预览外发范围。');
    planState.readGeneration++;planState.view=data;planState.meta=null;planClearBody();
    const history=validTaskHistory(data),records=byId('native-plan-history');records.replaceChildren();let count=0,invalidHistory=false;
    for(const [field,legacy] of [['native_plan_history',false],['plan_history',true]]) {
      const values=data[field];if(values===undefined)continue;
      if(!Array.isArray(values)||values.length>20){invalidHistory=true;continue;}
      if(!values.length)continue;if(!history){invalidHistory=true;continue;}
      const seen=new Set();for(const meta of values){const item=history.find(v=>v.task_id===meta?.task_id);if(!item||seen.has(meta?.task_id)||!planMeta(meta,legacy)){invalidHistory=true;continue;}seen.add(meta.task_id);count++;const row=formulaElement(records,'li','');formulaElement(row,'a',`修订 ${item.input_revision} · ${legacy?'历史夹具计划':'研究计划'} · ${planStates[meta.state]}（新标签页，只读）`,{href:`/research/${data.research.id}?task_id=${meta.task_id}`,target:'_blank',rel:'noopener'});}
    }
    byId('native-plan-history-status').textContent=invalidHistory?'计划流程列表尚未完整核对，请重新读取；不能据此判断没有记录。':count?`本页 ${count} 条计划流程；打开原任务可核对原记录。`:'本页尚无已读取的计划流程；不会自动生成。';
    const anchor=planAnchor(data),legacy=anchor?.policy==='funded-plan-v1',meta=legacy?data.plan:data.native_plan;
    if(anchor&&planMeta(meta,legacy)&&meta.task_id===anchor.task_id){planState.meta=meta;
      if(!methodDirty&&!formulaState.dirty&&anchor.input_revision===editBase?.revision&&anchor.input_digest===editBase?.digest){planShow(meta,legacy);if(read)planRead(meta,anchor,planTicket(true),legacy);}
      else byId('native-plan-status').textContent='当前草稿或载入修订已变化，原计划未替换本页输入；可从流程列表只读查看。';
    }else if(!planState.preview)byId('native-plan-status').textContent=methodDirty?'本页有未保存草稿；已存计划只能从流程列表核对。':'当前问题未取得可展示的计划；不会自动生成。';
    planSync();
  }
  function planSavedAnchor() {
    if(!researchId||!editBase||methodDirty||formulaState.dirty||readOnlyView()||editNotice()||current?.current_problem?.entry!=='phenomenon'||current.current_problem.confirmed!==true)throw Error('请先保存并核对自己的现象自述，再预览。');
    const original=current.current_problem.original_input;if(!planText(original,1000,8))throw Error('计划输入仅支持8–1000字自己的观察自述；当前原话已保留，可另存合适版本。');
    return {rid:researchId,input_revision:editBase.revision,input_digest:editBase.digest,original_input:original,research_version:observed?.researchVersion||editBase.researchVersion};
  }
  async function planPreview() {
    if(planState.busy||busy||readOnlyView())return;let pending,ticket;const token=Symbol();
    try {
      if(planPending())throw Error('上次提交尚待核对，请先读取或用原操作核对；不会另开计划。');
      const anchor=planSavedAnchor();if(!byId('native-plan-own').checked)throw Error('请先确认本次仅包含自己的观察自述。');
      planInvalidate();ticket=planTicket();planState.busy=true;planState.operation=token;planSync();byId('native-plan-status').textContent='正在核对外发原文与费用上限；尚未发送模型请求。';
      const data={input_revision:anchor.input_revision,expected_research_version:anchor.research_version,observation_source:'own_observation',declaration_status:'self_declared'};
      const body=JSON.stringify({schema_version:schema,contract_revision:planContract,data});pending=await operationKey(`native-plan-v2-preview:${anchor.rid}:${anchor.input_revision}:${anchor.research_version}`,body,anchor.input_revision,data);
      if(!planActive(ticket))return;const value=planValidatePreview(await planRequest(`/api/research/${anchor.rid}/plan-previews`,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':pending.key},body},ticket,'preview'),anchor);
      if(!planActive(ticket))return;formulaRetire(pending);planState.preview={...value,anchor};byId('native-plan-preview-panel').hidden=false;byId('native-plan-exact-input').textContent=value.exact_input;
      byId('native-plan-quote').textContent=`用途：规划下一步查什么。拟发送至 ${value.quote.provider} / ${value.quote.model}（声明版本 ${value.quote.declared_model_version}）。本次费用上限 CNY ${planMoney(value.approved_upper_units)}；报价有效至 ${new Date(value.expires_at*1000).toLocaleString('zh-CN')}。余额尚未核对，这不是可用余额或已扣费用。`;
      byId('native-plan-status').textContent=value.can_confirm?'请逐字核对上方将外发的已保存原文，并明确确认本次费用上界。':'资金执行入口尚未开放；仅展示本次原文和报价，不能确认外发。保存、账户与公式功能仍可使用。';
      planState.timer=setTimeout(()=>{if(planState.preview?.preview_ref===value.preview_ref){byId('native-plan-consent').checked=false;planSync();byId('native-plan-status').textContent='报价已到期，请重新预览；未自动确认或外发。';}},Math.min(2147483647,Math.max(0,value.expires_at*1000-Date.now())));
    }catch(error){if(!ticket||planActive(ticket)){if(pending&&error.status>=400&&error.status<500)formulaRetire(pending);byId('native-plan-status').textContent=planError(error);}}
    finally{if(planState.operation===token){planState.busy=false;planState.operation=null;planSync();}}
  }
  async function planConfirm(recover=false) {
    if(planState.busy||busy||readOnlyView())return;let pending,ticket;const token=Symbol();
    try {
      let original;
      if(recover){pending=planPending();original=pending?.task_request;if(!original||planUncertain(planState.meta))throw Error('请先读取原计划状态；待核对期间不会重复执行。');}
      else {
        const preview=planState.preview;if(!preview||!preview.can_confirm||Date.now()>=preview.expires_at*1000||!byId('native-plan-consent').checked||!byId('native-plan-own').checked)throw Error('请重新核对原文、有效报价并明确同意外发。');
        const anchor=planSavedAnchor();if(anchor.input_revision!==preview.anchor.input_revision||anchor.input_digest!==preview.anchor.input_digest||anchor.research_version!==preview.expected_research_version)throw Error('已保存问题或流程版本有变化，请重新预览。');
        original={data:{preview_ref:preview.preview_ref,preview_digest:preview.preview_digest,request_digest:preview.request_digest,expected_research_version:preview.expected_research_version,approved_upper_units:preview.approved_upper_units,confirm_outbound:true},anchor:preview.anchor};
      }
      const data=original?.data,anchor=original?.anchor;
      if(!planKeys(data,['preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units','confirm_outbound'])||!planRef(data.preview_ref)||!planDigest(data.preview_digest)||!planDigest(data.request_digest)||!planInt(data.expected_research_version)||!planUnits(data.approved_upper_units)||data.confirm_outbound!==true||anchor?.rid!==researchId||!planInt(anchor.input_revision)||!planDigest(anchor.input_digest))throw Error('原操作范围无法核对，未发起新的请求。');
      const body=JSON.stringify({schema_version:schema,contract_revision:planContract,data});ticket=planTicket();pending=await operationKey('native-plan-v2-confirm:'+researchId,body,anchor.input_revision,original);
      if(!planActive(ticket))return;planState.busy=true;planState.operation=token;planState.preview=null;clearTimeout(planState.timer);byId('native-plan-preview-panel').hidden=true;byId('native-plan-consent').checked=false;planClearBody();planSync();byId('native-plan-status').textContent='正在核对本次明确确认的原操作；排队回执不代表计划已经生成。';
      if(!await planAuthenticate(ticket))return;
      const ack=await planRequest(`/api/research/${ticket.rid}/plan-approvals`,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':pending.key},body},ticket,'confirm');
      if(!planKeys(ack,['task_id','result_ref','state','cash_evidence','real_model_executed','recorded_at'])||!validId(ack.task_id)||!planRef(ack.result_ref)||ack.state!=='queued'||ack.cash_evidence!=='not_observed'||ack.real_model_executed!==false||ack.recorded_at!==null)throw Error('原排队回执格式无法核对，key已保留。');
      const bound=await planRequest(`/api/research/${ticket.rid}?task_id=${encodeURIComponent(ack.task_id)}`,{},ticket,'bind');
      const task=bound.task,first=bound.task_history?.[0],meta=bound.native_plan;
      if(bound.research?.id!==ticket.rid||task?.id!==ack.task_id||task.policy_revision!=='native-plan-v1'||task.input_revision!==anchor.input_revision||task.input_digest!==anchor.input_digest||bound.current_problem?.revision!==anchor.input_revision||bound.current_problem?.digest!==anchor.input_digest||first?.task_id!==task.id||first.input_revision!==anchor.input_revision||first.input_digest!==anchor.input_digest||first.start_version!==data.expected_research_version+1||!planMeta(meta)||meta.result_ref!==ack.result_ref||meta.task_id!==task.id)throw Error('回执未与原研究、修订和请求绑定，key已保留。');
      if(!planActive(ticket))return;const stored=JSON.parse(sessionStorage.getItem(pending.slot));if(stored?.key===pending.key){stored.receipt={task_id:ack.task_id,result_ref:ack.result_ref};sessionStorage.setItem(pending.slot,JSON.stringify(stored));}
      if(methodDirty||formulaState.dirty||bound.is_historical){const originalState=await planRead(meta,planAnchor(bound),planTicket(true),false,false);if(!planActive(ticket)||!originalState)return;byId('native-plan-status').textContent=planStates[originalState.state]+'。已核对原操作，当前草稿未替换；可在新标签页只读查看原流程。';formulaElement(byId('native-plan-body'),'a','只读查看原计划流程',{href:`/research/${ticket.rid}?task_id=${ack.task_id}`,target:'_blank',rel:'noopener'});return;}
      renderTask(bound,{nativePlanRead:false});await planRead(meta,planAnchor(bound),planTicket(true));
    }catch(error){if(!ticket||planActive(ticket)){const rejected=pending&&error.planPurpose==='confirm'&&['INPUT_INVALID','REVISION_CONFLICT','PREVIEW_EXPIRED','PREVIEW_CHANGED','TASK_ACTIVE','FUNDING_GRANT_REQUIRED'].includes(error.code)&&error.status>=400&&error.status<500;if(rejected)formulaRetire(pending);planClearBody();byId('native-plan-status').textContent=planError(error)+(rejected?' 当前输入仍保留，请重新预览；不会自动再次外发。':' 请保留草稿与原操作；不会自动再发模型请求。');}}
    finally{if(planState.operation===token){planState.busy=false;planState.operation=null;planSync();}}
  }
  function initPlan() {
    byId('native-plan-own').addEventListener('change',()=>{planInvalidate('自述声明已变化，请重新预览。');planSync();});
    byId('native-plan-consent').addEventListener('change',planSync);byId('native-plan-preview').addEventListener('click',planPreview);byId('native-plan-confirm').addEventListener('click',()=>planConfirm());byId('native-plan-recover').addEventListener('click',()=>planConfirm(true));
    byId('native-plan-refresh').addEventListener('click',async()=>{
      if(planState.busy||busy||!researchId)return;
      planInvalidate('正在按当前账户核对计划状态；不会发送模型请求。');
      const ticket=planTicket(),operation=Symbol();planState.busy=true;planState.operation=operation;planSync();
      try{if(!await planAuthenticate(ticket))return;const view=await request(viewUrl(),{},()=>planActive(ticket));if(planActive(ticket))renderTask(view);}
      catch(error){if(planActive(ticket)){planClearBody();byId('native-plan-status').textContent=planError(error);}}
      finally{if(planState.operation===operation){planState.busy=false;planState.operation=null;planSync();}}
    });
    byId('native-plan-query-draft').addEventListener('input',planSync);byId('native-plan-use-query').addEventListener('click',()=>{if(readOnlyView()||!taskData?.capabilities?.source_evidence||byId('native-plan-use-query').disabled)return;byId('source-query').value=byId('native-plan-query-draft').value;byId('source-query').dispatchEvent(new Event('input',{bubbles:true}));byId('source-query').focus();byId('source-query').scrollIntoView({block:'center'});byId('native-plan-status').textContent='已填入可编辑的来源查询草稿；尚未预览、批准或读取任何来源。';});
  }


  // FIN1 exported response schema50ba1bdd…5792; independent from Root b1/F8/F9.
  const financialSchema={"$defs":{"FinancialImportPreviewData":{"additionalProperties":false,"properties":{"exact_received_csv_sha256":{"pattern":"^[0-9a-f]{64}$","title":"Exact Received Csv Sha256","type":"string"},"execution_authorized":{"const":false,"default":false,"enum":[false],"title":"Execution Authorized","type":"boolean"},"expected_research_version":{"maximum":2147483647,"minimum":1,"title":"Expected Research Version","type":"integer"},"input_revision":{"maximum":2147483647,"minimum":1,"title":"Input Revision","type":"integer"},"key_based_plan_digest":{"pattern":"^[0-9a-f]{64}$","title":"Key Based Plan Digest","type":"string"},"kind":{"const":"owner_supplied","default":"owner_supplied","enum":["owner_supplied"],"title":"Kind","type":"string"},"original_available":{"const":false,"default":false,"enum":[false],"title":"Original Available","type":"boolean"},"parser_revision":{"const":"owner-financial-csv-v1","default":"owner-financial-csv-v1","enum":["owner-financial-csv-v1"],"title":"Parser Revision","type":"string"},"persisted":{"const":false,"default":false,"enum":[false],"title":"Persisted","type":"boolean"},"plan":{"$ref":"#/$defs/OwnerFinancialImportPlanV2"},"preview_digest":{"pattern":"^[0-9a-f]{64}$","title":"Preview Digest","type":"string"},"problem_digest":{"pattern":"^[0-9a-f]{64}$","title":"Problem Digest","type":"string"},"qualifications":{"default":["owner_declarations_not_verified","claimed_dates_not_verified_as_of","preview_only_no_save_or_execution"],"items":{"enum":["owner_declarations_not_verified","claimed_dates_not_verified_as_of","preview_only_no_save_or_execution"],"type":"string"},"title":"Qualifications","type":"array"},"research_id":{"title":"Research Id","type":"string"},"system_verified":{"const":false,"default":false,"enum":[false],"title":"System Verified","type":"boolean"},"verification":{"const":"unverified","default":"unverified","enum":["unverified"],"title":"Verification","type":"string"}},"required":["research_id","input_revision","problem_digest","expected_research_version","exact_received_csv_sha256","key_based_plan_digest","preview_digest","plan"],"title":"FinancialImportPreviewData","type":"object"},"OwnerFinancialImportPlanV2":{"additionalProperties":false,"properties":{"contract":{"const":"owner-financial-key-plan-v2","default":"owner-financial-key-plan-v2","enum":["owner-financial-key-plan-v2"],"title":"Contract","type":"string"},"parser_revision":{"const":"owner-financial-csv-v1","default":"owner-financial-csv-v1","enum":["owner-financial-csv-v1"],"title":"Parser Revision","type":"string"},"records":{"items":{"discriminator":{"mapping":{"historical_fx":"#/$defs/OwnerHistoricalFXV2","observation":"#/$defs/OwnerObservationV2","source":"#/$defs/OwnerSourceV2"},"propertyName":"row_type"},"oneOf":[{"$ref":"#/$defs/OwnerSourceV2"},{"$ref":"#/$defs/OwnerObservationV2"},{"$ref":"#/$defs/OwnerHistoricalFXV2"}]},"maxItems":96,"title":"Records","type":"array"}},"required":["records"],"title":"OwnerFinancialImportPlanV2","type":"object"},"OwnerHistoricalFXV2":{"additionalProperties":false,"properties":{"declared_basis":{"enum":["disclosed","media_estimate","missing","conflicted"],"title":"Declared Basis","type":"string"},"from_currency":{"enum":["CNY","USD"],"title":"From Currency","type":"string"},"fx_kind":{"enum":["period_average","spot"],"title":"Fx Kind","type":"string"},"key":{"maxLength":32,"minLength":1,"pattern":"^[a-z][a-z0-9_]{0,31}$","title":"Key","type":"string"},"kind":{"const":"owner_supplied","default":"owner_supplied","enum":["owner_supplied"],"title":"Kind","type":"string"},"original_available":{"const":false,"default":false,"enum":[false],"title":"Original Available","type":"boolean"},"period_end":{"title":"Period End","type":"string"},"period_grain":{"enum":["annual","interim","remaining"],"title":"Period Grain","type":"string"},"period_start":{"title":"Period Start","type":"string"},"physical_line_end":{"maximum":131073,"minimum":2,"title":"Physical Line End","type":"integer"},"physical_line_start":{"maximum":131073,"minimum":2,"title":"Physical Line Start","type":"integer"},"record_index":{"maximum":96,"minimum":1,"title":"Record Index","type":"integer"},"row_type":{"const":"historical_fx","enum":["historical_fx"],"title":"Row Type","type":"string"},"source_refs":{"items":{"type":"string"},"maxItems":16,"title":"Source Refs","type":"array"},"system_verified":{"const":false,"default":false,"enum":[false],"title":"System Verified","type":"boolean"},"to_currency":{"enum":["CNY","USD"],"title":"To Currency","type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Value"},"verification":{"const":"unverified","default":"unverified","enum":["unverified"],"title":"Verification","type":"string"}},"required":["key","record_index","physical_line_start","physical_line_end","period_start","period_end","period_grain","value","declared_basis","source_refs","row_type","from_currency","to_currency","fx_kind"],"title":"OwnerHistoricalFXV2","type":"object"},"OwnerObservationV2":{"additionalProperties":false,"properties":{"accounting_basis":{"maxLength":240,"minLength":1,"title":"Accounting Basis","type":"string"},"alternative_refs":{"items":{"type":"string"},"maxItems":8,"title":"Alternative Refs","type":"array"},"currency":{"enum":["CNY","USD"],"title":"Currency","type":"string"},"declared_basis":{"enum":["disclosed","media_estimate","missing","conflicted"],"title":"Declared Basis","type":"string"},"entity_scope":{"maxLength":120,"minLength":1,"title":"Entity Scope","type":"string"},"key":{"maxLength":32,"minLength":1,"pattern":"^[a-z][a-z0-9_]{0,31}$","title":"Key","type":"string"},"kind":{"const":"owner_supplied","default":"owner_supplied","enum":["owner_supplied"],"title":"Kind","type":"string"},"metric":{"enum":["revenue","operating_profit","net_profit","operating_cost","operating_expense","shared_cost","depreciation","sbc","operating_adjustment","capex"],"title":"Metric","type":"string"},"original_available":{"const":false,"default":false,"enum":[false],"title":"Original Available","type":"boolean"},"period_end":{"title":"Period End","type":"string"},"period_grain":{"enum":["annual","interim","remaining"],"title":"Period Grain","type":"string"},"period_start":{"title":"Period Start","type":"string"},"physical_line_end":{"maximum":131073,"minimum":2,"title":"Physical Line End","type":"integer"},"physical_line_start":{"maximum":131073,"minimum":2,"title":"Physical Line Start","type":"integer"},"record_index":{"maximum":96,"minimum":1,"title":"Record Index","type":"integer"},"row_type":{"const":"observation","enum":["observation"],"title":"Row Type","type":"string"},"scope_kind":{"enum":["group","segment","app"],"title":"Scope Kind","type":"string"},"source_refs":{"items":{"type":"string"},"maxItems":16,"title":"Source Refs","type":"array"},"system_verified":{"const":false,"default":false,"enum":[false],"title":"System Verified","type":"boolean"},"unit":{"enum":["unit","thousand","million","billion"],"title":"Unit","type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Value"},"verification":{"const":"unverified","default":"unverified","enum":["unverified"],"title":"Verification","type":"string"}},"required":["key","record_index","physical_line_start","physical_line_end","period_start","period_end","period_grain","value","declared_basis","source_refs","row_type","entity_scope","scope_kind","metric","currency","unit","accounting_basis","alternative_refs"],"title":"OwnerObservationV2","type":"object"},"OwnerSourceV2":{"additionalProperties":false,"properties":{"claimed_accessed_at":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Claimed Accessed At"},"claimed_published_at":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Claimed Published At"},"declared_original_sha256":{"anyOf":[{"pattern":"^[0-9a-f]{64}$","type":"string"},{"type":"null"}],"title":"Declared Original Sha256"},"excerpt":{"maxLength":1000,"minLength":1,"title":"Excerpt","type":"string"},"key":{"maxLength":32,"minLength":1,"pattern":"^[a-z][a-z0-9_]{0,31}$","title":"Key","type":"string"},"kind":{"const":"owner_supplied","default":"owner_supplied","enum":["owner_supplied"],"title":"Kind","type":"string"},"locator":{"maxLength":240,"minLength":1,"title":"Locator","type":"string"},"original_available":{"const":false,"default":false,"enum":[false],"title":"Original Available","type":"boolean"},"physical_line_end":{"maximum":131073,"minimum":2,"title":"Physical Line End","type":"integer"},"physical_line_start":{"maximum":131073,"minimum":2,"title":"Physical Line Start","type":"integer"},"read_scope":{"maxLength":700,"minLength":1,"title":"Read Scope","type":"string"},"received_excerpt_sha256":{"pattern":"^[0-9a-f]{64}$","title":"Received Excerpt Sha256","type":"string"},"record_index":{"maximum":96,"minimum":1,"title":"Record Index","type":"integer"},"row_type":{"const":"source","enum":["source"],"title":"Row Type","type":"string"},"source_chain":{"items":{"type":"string"},"maxItems":16,"title":"Source Chain","type":"array"},"system_verified":{"const":false,"default":false,"enum":[false],"title":"System Verified","type":"boolean"},"url":{"maxLength":1600,"minLength":1,"title":"Url","type":"string"},"verification":{"const":"unverified","default":"unverified","enum":["unverified"],"title":"Verification","type":"string"}},"required":["key","record_index","physical_line_start","physical_line_end","row_type","url","locator","excerpt","received_excerpt_sha256","declared_original_sha256","claimed_published_at","claimed_accessed_at","read_scope","source_chain"],"title":"OwnerSourceV2","type":"object"}},"additionalProperties":false,"properties":{"contract_revision":{"const":"financial-input-v2","default":"financial-input-v2","enum":["financial-input-v2"],"title":"Contract Revision","type":"string"},"data":{"$ref":"#/$defs/FinancialImportPreviewData"},"schema_version":{"const":"structure-research-v1","default":"structure-research-v1","enum":["structure-research-v1"],"title":"Schema Version","type":"string"}},"required":["data"],"title":"FinancialImportPreviewResponse","type":"object"}
;
  const financialContract='financial-input-v2',financialParser='owner-financial-csv-v1',financialLimit=131072;
  const financialQualifications=['owner_declarations_not_verified','claimed_dates_not_verified_as_of','preview_only_no_save_or_execution'];
  function financialInvalidate(message='输入已变化，旧预览已失效；尚未保存或计算。', notifyRegistry=true){
    if(notifyRegistry)registryUI?.invalidate('preview_changed');
    financialState.previewVersion=null;financialState.epoch++;financialState.controller?.abort();financialState.controller=null;financialState.operation=null;financialState.busy=false;byId('financial-preview-result').replaceChildren();byId('financial-preview-status').textContent=message;financialSync();
  }
  function financialReset(){financialInvalidate('');financialState.basis=null;byId('financial-preview-csv').value='';financialSync();byId('financial-preview-section').hidden=true;}
  function financialBasis(){return researchId&&editBase?JSON.stringify([researchId,editBase.revision,editBase.digest,observed?.researchVersion||editBase.researchVersion]):null;}
  function financialObserve(){const next=financialBasis();if(financialState.basis&&next!==financialState.basis)financialInvalidate('研究或问题版本已变化，旧预览已失效；CSV 仍暂存在本页。');financialState.basis=next;financialSync();}
  function financialSync(){
    if(financialState.previewVersion!==null&&observed&&observed.researchVersion>financialState.previewVersion){financialInvalidate('研究版本已变化，旧预览已失效；CSV 仍暂存在本页。');return;}
    const ro=readOnlyView(),conflict=editBase&&observed&&(editBase.revision!==observed.revision||editBase.digest!==observed.digest),bytes=new TextEncoder().encode(byId('financial-preview-csv').value).length;
    byId('financial-preview-section').hidden=form.hidden;
    byId('financial-preview-context').textContent=ro?'当前是只读或历史问题，不能提交预览。':!researchId?'请先保存问题，再提交有限 CSV 预览。':conflict?'问题版本已变化，请明确读取当前问题后再预览；手稿保持不变。':methodDirty||formulaState.dirty?'问题尚有未保存改动；先保存问题，CSV 仅暂存本页。':`预览目标：问题修订 ${editBase?.revision}。免费本地解析，不需要开启模型或来源采集。`;
    byId('financial-preview-size').textContent=`当前 ${bytes} / ${financialLimit} UTF-8 字节${bytes>financialLimit?'，已超出预览范围，请减少文本。':''}`;
    byId('financial-preview-csv').disabled=ro||busy;
    byId('financial-preview-run').disabled=ro||busy||financialState.busy||!researchId||!editBase||!bytes||bytes>financialLimit||methodDirty||formulaState.dirty||Boolean(conflict);
    byId('financial-preview-clear').disabled=ro||busy;
  }
  function financialTicket(){return {epoch:financialState.epoch,privateScope:privateGeneration,rid:researchId,revision:editBase?.revision,digest:editBase?.digest,account:accountScope,csv:byId('financial-preview-csv').value};}
  function financialActive(ticket){return ticket.epoch===financialState.epoch&&ticket.privateScope===privateGeneration&&ticket.rid===researchId&&ticket.revision===editBase?.revision&&ticket.digest===editBase?.digest&&ticket.account===accountScope&&(ticket.version===undefined||!observed||observed.researchVersion<=ticket.version)&&ticket.csv===byId('financial-preview-csv').value&&!readOnlyView()&&!methodDirty&&!formulaState.dirty&&(!observed||(observed.revision===ticket.revision&&observed.digest===ticket.digest));}
  async function financialAuth(ticket){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);try{return await authenticated(()=>financialActive(ticket),controller.signal);}finally{clearTimeout(timer);}}
  function financialShape(value,shape){
    if(shape.$ref)return financialShape(value,shape.$ref.split('/').slice(1).reduce((node,key)=>node[key],financialSchema));
    if(shape.anyOf&&!shape.anyOf.some(child=>financialShape(value,child)))return false;
    if(shape.oneOf&&shape.oneOf.filter(child=>financialShape(value,child)).length!==1)return false;
    if(Object.hasOwn(shape,'const')&&value!==shape.const||shape.enum&&!shape.enum.includes(value))return false;
    if(shape.type==='null'&&value!==null||shape.type==='boolean'&&typeof value!=='boolean')return false;
    if(shape.type==='integer'&&(!Number.isSafeInteger(value)||value<(shape.minimum??-Infinity)||value>(shape.maximum??Infinity)))return false;
    if(shape.type==='string'&&(typeof value!=='string'||Array.from(value).length<(shape.minLength??0)||Array.from(value).length>(shape.maxLength??Infinity)||shape.pattern&&!new RegExp(shape.pattern).test(value)))return false;
    if(shape.type==='array'&&(!Array.isArray(value)||value.length>(shape.maxItems??Infinity)||value.length<(shape.minItems??0)||shape.items&&value.some(item=>!financialShape(item,shape.items))))return false;
    if(shape.type==='object'){
      if(!planObject(value)||(shape.required||[]).some(key=>!Object.hasOwn(value,key))||shape.additionalProperties===false&&Object.keys(value).some(key=>!Object.hasOwn(shape.properties,key)))return false;
      if(Object.entries(value).some(([key,item])=>shape.properties[key]&&!financialShape(item,shape.properties[key])))return false;
    }
    return true;
  }
  async function financialTextHash(text){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));return Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join('');}
  async function financialValidate(envelope,ticket,version){
    if(!financialShape(envelope,financialSchema)||envelope.schema_version!==schema||envelope.contract_revision!==financialContract)throw Error('预览响应格式无法核对，未展示为有效结果。');
    const data=envelope.data,owner=value=>value.kind==='owner_supplied'&&value.verification==='unverified'&&value.original_available===false&&value.system_verified===false;
    if(!owner(data)||data.persisted!==false||data.execution_authorized!==false||data.research_id!==ticket.rid||data.input_revision!==ticket.revision||data.problem_digest!==ticket.digest||data.expected_research_version!==version||data.parser_revision!==financialParser||formulaCanonical(data.qualifications)!==formulaCanonical(financialQualifications)||data.plan.contract!=='owner-financial-key-plan-v2'||data.plan.parser_revision!==financialParser||data.plan.records.some((row,index)=>!owner(row)||row.record_index!==index+1)||new Set(data.plan.records.map(row=>row.key)).size!==data.plan.records.length)throw Error('预览与本次输入、问题或来源限定不匹配。');
    if(new TextEncoder().encode(formulaCanonical(data.plan)).length>financialLimit||await financialTextHash(ticket.csv)!==data.exact_received_csv_sha256||await formulaHash(data.plan)!==data.key_based_plan_digest)throw Error('CSV 或预览内容摘要无法核对。');
    for(const row of data.plan.records)if(row.row_type==='source'&&await financialTextHash(row.excerpt)!==row.received_excerpt_sha256)throw Error('收到的摘录文本摘要无法核对。');
    const binding={contract:financialContract,parser_revision:financialParser,research_id:ticket.rid,input_revision:ticket.revision,problem_digest:ticket.digest,expected_research_version:version,exact_received_csv_sha256:data.exact_received_csv_sha256,key_based_plan_digest:data.key_based_plan_digest};
    if(await formulaHash(binding)!==data.preview_digest)throw Error('预览绑定摘要无法核对。');return data;
  }
  function financialRender(data){
    const box=byId('financial-preview-result');box.replaceChildren();const add=(parent,tag,text,options={})=>formulaElement(parent,tag,text,options),missing=value=>value===null?'缺失（未按 0 处理）':value;
    add(box,'h3','临时预览 · 未保存 · 未计算');add(box,'p','以下均为账户提交与声明，尚未核验；未取得原件。声明日期不构成已验证的 as-of 时点。',{className:'scope'});
    const basis={disclosed:'账户声明为披露（未核验）',media_estimate:'账户声明为媒体估计（未核验）',missing:'账户声明为缺失',conflicted:'账户声明为争议'},metrics={revenue:'营收',operating_profit:'营业利润',net_profit:'净利润',operating_cost:'营业成本',operating_expense:'营业费用',shared_cost:'共享成本',depreciation:'折旧',sbc:'股权激励成本',operating_adjustment:'营业调整',capex:'资本开支'};
    for(const [kind,title] of [['source','账户来源声明'],['observation','历史观察'],['historical_fx','历史汇率']]){
      const rows=data.plan.records.filter(row=>row.row_type===kind);add(box,'h4',`${title}（${rows.length}）`);
      for(const row of rows){const card=add(box,'article','',{className:'draft-material'});add(card,'h4',row.key);add(card,'p',`账户提交 · 未核验 · 未取得原件；CSV 记录 ${row.record_index}，物理行 ${row.physical_line_start}–${row.physical_line_end}（不是原件页码或网页位置）`,{className:'hint'});
        if(kind==='source'){
          for(const [label,value] of [['声明 URL（仅定位文本，不访问）',row.url],['账户填写的位置说明',row.locator],['账户声明的读取范围',row.read_scope],['声明发布日期',row.claimed_published_at],['声明访问日期',row.claimed_accessed_at],['声明原件 SHA256（未核验）',row.declared_original_sha256]])add(card,'p',`${label}：${value===null?'未声明':value}`);
          add(card,'blockquote',row.excerpt);add(card,'p',`来源链 key：${row.source_chain.join('；')||'未声明'}`);
        }else{
          add(card,'p',kind==='observation'?`${row.entity_scope} · ${{group:'集团',segment:'分部',app:'单 App'}[row.scope_kind]} · ${metrics[row.metric]}`:`${row.from_currency} → ${row.to_currency} · ${row.fx_kind==='period_average'?'期间平均汇率':'即期汇率'}`);
          add(card,'p',`原数值字符串：${missing(row.value)}`,{className:'financial-original-value'});add(card,'p',`${row.period_start} 至 ${row.period_end} · ${{annual:'年度',interim:'期间',remaining:'剩余期间'}[row.period_grain]} · ${basis[row.declared_basis]}`);
          if(kind==='observation'){add(card,'p',`币种：${row.currency}；单位：${row.unit}；账户填写的会计口径：${row.accounting_basis}`);add(card,'p',`替代观察 key：${row.alternative_refs.join('；')||'未声明'}`);}
          add(card,'p',`账户引用的来源 key：${row.source_refs.join('；')||'未声明'}；仍需核对原件与口径。`,{className:'hint'});
        }
      }
    }
    const detail=add(box,'details','');add(detail,'summary','本次文本与临时预览的校验摘要');add(detail,'p',`收到的精确 CSV UTF-8 摘要：${data.exact_received_csv_sha256}`);add(detail,'p',`临时预览摘要：${data.preview_digest}；它不是已保存记录编号，也不授计算或公开分享权限。`);
  }
  async function financialPreview(){
    if(byId('financial-preview-run').disabled||financialState.busy)return;
    financialInvalidate('正在核对当前账户、问题版本并预览；尚未保存或计算。');const ticket=financialTicket(),operation=Symbol();financialState.operation=operation;financialState.busy=true;financialSync();
    try{
      if(!await financialAuth(ticket)||!financialActive(ticket))return;
      const root=await request(`/api/research/${ticket.rid}`,{},()=>financialActive(ticket));
      if(root.research?.id!==ticket.rid||root.current_problem?.revision!==ticket.revision||root.current_problem.digest!==ticket.digest||!planInt(root.research_version))throw Error('问题基准已变化，请明确重新读取后再预览；手稿保持不变。');
      ticket.version=root.research_version;if(!financialActive(ticket))return;
      const data={input_revision:ticket.revision,expected_research_version:root.research_version,csv_text:ticket.csv},controller=new AbortController();financialState.controller=controller;const timer=setTimeout(()=>controller.abort(),15000);
      let response,envelope;
      try{response=await fetch(`/api/research/${ticket.rid}/financial-import-preview`,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({schema_version:schema,contract_revision:financialContract,data}),signal:controller.signal});if(!financialActive(ticket))return;envelope=await response.json();}finally{clearTimeout(timer);if(financialState.controller===controller)financialState.controller=null;}
      if(!financialActive(ticket))return;
      if(!response.ok){
        const code=envelope?.error?.code;
        if(response.status===401||response.status===404||code==='AUTHORIZATION_STALE'){await financialAuth(ticket);if(response.status===404&&financialActive(ticket))try{await request(`/api/research/${ticket.rid}`,{},()=>financialActive(ticket));}catch{}if(!financialActive(ticket))return;}
        const labels={VERSION_CONFLICT:'问题版本已变化，请明确重新读取后再预览。',AUTHORIZATION_STALE:'当前权限无法核对，请重新确认账户与问题。',NOT_FOUND:'研究不存在或当前无法访问。',PAYLOAD_LIMIT:'CSV 或预览超出有限范围，请减少文本。',INPUT_INVALID:'CSV 无法解析，请修改指定行与字段。'};
        const detail=envelope?.validation,location=detail&&Number.isSafeInteger(detail.row)&&detail.row>=1&&detail.row<=131073?` 第 ${detail.row} 行`:'',field=detail&&typeof detail.field==='string'&&/^[a-z_]{1,40}$/.test(detail.field)?`，字段 ${detail.field}`:'',safeCode=detail&&typeof detail.code==='string'&&/^[A-Z_]{1,64}$/.test(detail.code)?`（${detail.code}）`:'';
        throw Error((labels[code]||'本次预览未完成，请保留本页 CSV 后重试。')+location+field+safeCode+' 旧预览已失效，尚未保存或计算。');
      }
      const checked=await financialValidate(envelope,ticket,root.research_version);if(!financialActive(ticket))return;
      if(!await financialAuth(ticket)||!financialActive(ticket))return;
      const fresh=await request(`/api/research/${ticket.rid}`,{},()=>financialActive(ticket));
      if(fresh.research?.id!==ticket.rid||fresh.current_problem?.revision!==ticket.revision||fresh.current_problem.digest!==ticket.digest||fresh.research_version!==root.research_version)throw Error('问题或研究版本已变化，旧预览已失效；请重新预览，手稿保持不变。');
      if(!await financialAuth(ticket)||!financialActive(ticket))return;financialState.basis=JSON.stringify([ticket.rid,ticket.revision,ticket.digest,root.research_version]);financialState.previewVersion=root.research_version;financialRender(checked);await registryUI?.acceptPreview({checked,csv:ticket.csv});byId('financial-preview-status').textContent='临时预览已返回；账户声明未核验，未取得原件，尚未保存或计算。';
    }catch(error){if(financialActive(ticket)){byId('financial-preview-result').replaceChildren();byId('financial-preview-status').textContent=['AbortError','TypeError','SyntaxError'].includes(error.name)?'本次预览响应尚未确认；旧预览已失效。本入口不保存或计算，请保留本页 CSV 后主动重试。':error.message;}}
    finally{if(financialState.operation===operation){financialState.operation=null;financialState.busy=false;financialState.controller=null;financialSync();}}
  }
  function initFinancialPreview(){byId('financial-preview-csv').addEventListener('input',()=>financialInvalidate());byId('financial-preview-clear').addEventListener('click',()=>{byId('financial-preview-csv').value='';financialInvalidate('已清空本页 CSV 与临时预览；没有删除或保存研究记录。');});byId('financial-preview-run').addEventListener('click',financialPreview);financialSync();}

  // Manual drafts have their own immutable record and read/write purpose.
  const draftContract='method-draft-v1';
  const draftCasRejection=Symbol('current method draft POST explicitly rejected before write');
  const draftFields=['method-draft-label','method-draft-method','method-draft-mapping','method-draft-nontransferable','method-draft-competing','method-draft-question','method-draft-measurement','method-draft-outcome','method-draft-falsification','method-draft-stop'];
  const draftError=error=>['AbortError','TypeError','SyntaxError'].includes(error.name)?'草稿保存或读取状态尚未确认，请保留输入与原操作。':error.message;
  function draftTicket(){return {epoch:draftState.epoch,privateScope:privateGeneration,rid:researchId};}
  function draftActive(ticket){return ticket.epoch===draftState.epoch&&ticket.privateScope===privateGeneration&&ticket.rid===researchId&&(ticket.readEpoch===undefined||ticket.readEpoch===draftState.readEpoch);}
  function draftReadTicket(){draftState.readEpoch++;return {...draftTicket(),readEpoch:draftState.readEpoch};}
  function draftClearView(){byId('method-draft-view').replaceChildren();byId('method-draft-view-status').textContent='';draftState.view=null;}
  function draftChanged(message='方法草稿有修改；已保存原稿未被改写。'){
    draftState.epoch++;draftState.dirty=true;draftClearView();if(byId('method-draft-history-status').textContent==='正在核对草稿历史…')byId('method-draft-history-status').textContent='编辑内容已变化，较早历史读取不再显示；可主动重新读取。';byId('method-draft-status').textContent=message;draftSync();
  }
  function draftHideMaterials(message){
    draftState.epoch++;draftState.excerpts.clear();draftState.plans.clear();draftState.formulas.clear();draftState.origin=null;draftClearView();
    byId('method-draft-materials').replaceChildren();byId('method-draft-plan-choices').replaceChildren();byId('method-draft-formula').replaceChildren();
    formulaElement(byId('method-draft-formula'),'option','不关联公式记录',{value:''});byId('method-draft-material-status').textContent=message;draftSync();
  }
  function draftReset(){
    draftState.epoch++;draftState.readEpoch++;draftState.rid=null;draftState.target=null;draftState.busy=false;draftState.operation=null;draftState.actor=null;draftState.dirty=false;draftState.selected.clear();draftState.excerpts.clear();draftState.plans.clear();draftState.formulas.clear();draftState.history.clear();draftState.supersedes=null;draftState.origin=null;draftState.casRejected=null;draftState.catalog.clear();draftState.catalogNext=null;draftState.catalogCursors.clear();draftState.catalogGeneration++;draftState.catalogKnown=false;
    for(const id of draftFields)byId(id).value='';byId('method-draft-origin').value='user_proposed';
    for(const id of ['method-draft-task','method-draft-materials','method-draft-plan-choices','method-draft-formula','method-draft-history','method-draft-pending'])byId(id).replaceChildren();
    formulaElement(byId('method-draft-formula'),'option','不关联公式记录',{value:''});
    for(const id of ['method-draft-status','method-draft-material-status','method-draft-history-status','method-draft-parent'])byId(id).textContent='';draftClearView();byId('method-draft-section').hidden=true;byId('method-draft-more-tasks').hidden=true;
  }
  async function draftAuth(ticket){
    if(!draftActive(ticket))return false;const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{return await authenticated(()=>draftActive(ticket),controller.signal);}finally{clearTimeout(timer);}
  }
  async function draftFetch(url,options,ticket,purpose='draft'){
    if(!draftActive(ticket))throw Error('较早的草稿请求已失效，未追加保存或读取。');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch(url,{...options,credentials:'same-origin',cache:'no-store',signal:controller.signal});
      if(!draftActive(ticket))throw Error('较早的草稿响应已失效，原操作保留。');
      const envelope=await response.json();if(!draftActive(ticket))throw Error('较早的草稿响应已失效，原操作保留。');
      if(!response.ok){
        if(response.status===401||envelope.error?.code==='AUTHORIZATION_STALE')await authenticated(()=>draftActive(ticket),controller.signal);
        else if(response.status===404&&draftActive(ticket)){try{await request(`/api/research/${ticket.rid}`,{},()=>draftActive(ticket));}catch{}}
        const error=Error(envelope.error?.message||'本次草稿状态无法完整核对，内容仍保留。');error.code=envelope.error?.code;
        const failure=envelope.error;
        // This API checks replay before CAS; only this exact POST refusal proves no write.
        if(purpose==='save_post'&&options.method==='POST'&&url===`/api/research/${ticket.rid}/method-drafts`&&!response.redirected&&response.url===new URL(url,location.origin).href&&response.status===409&&planKeys(envelope,['error'])&&planKeys(failure,['code','message','retryable','allowed_next_actions','incident_id'])&&failure.code==='VERSION_CONFLICT'&&failure.message==='问题已更新，请重读后保存新草稿。'&&failure.retryable===false&&Array.isArray(failure.allowed_next_actions)&&failure.allowed_next_actions.length===0&&validId(failure.incident_id))error[draftCasRejection]=true;
        throw error;
      }
      const expected={draft:draftContract,save_post:draftContract,root:revision,plan_v1:'funded-plan-v1',plan_v2:planContract}[purpose];
      if(!expected||envelope.schema_version!==schema||envelope.contract_revision!==expected||!planObject(envelope.data))throw Error('草稿响应用途或版本不匹配。');
      return envelope.data;
    }finally{clearTimeout(timer);}
  }
  function draftPending(){
    if(!researchId||!draftState.actor)return [];const prefix=`structure-research-pending:method-draft-v1:${draftState.actor}:${researchId}:`;const result=[];
    for(const slot of Object.keys(sessionStorage))if(slot.startsWith(prefix)){try{const value=JSON.parse(sessionStorage.getItem(slot));if(value?.key&&value.task_request)result.push({...value,slot});}catch{}}
    return result;
  }
  async function draftSetActor(ticket){
    if(!await draftAuth(ticket)||!accountScope||!draftActive(ticket))return false;
    const value=await formulaHash({account:JSON.parse(accountScope)});if(!draftActive(ticket))return false;draftState.actor=value;draftRenderPending();return true;
  }
  function draftSync(){
    const ro=readOnlyView(),target=draftState.target;
    byId('method-draft-section').hidden=form.hidden||!researchId;
    const conflict=Boolean(editBase&&observed&&(editBase.revision!==observed.revision||editBase.digest!==observed.digest));
    const valid=researchId&&target&&editBase&&target.input_revision===editBase.revision&&target.problem_digest===editBase.digest&&!methodDirty&&!formulaState.dirty&&!conflict;
    byId('method-draft-target').textContent=target?`本次目标：问题修订 ${target.input_revision}。引用材料保留各自原修订，保存不会执行验证。`:'先保存并核对问题，再选择已存材料。';
    byId('method-draft-hint').textContent=ro?'当前流程只读；可查看原稿，不能保存新稿。':conflict?'服务端问题已有新版本。本地文字保持不变，保存前请明确载入当前问题。':methodDirty||formulaState.dirty?'问题有未保存改动；先保存问题，此处手写内容已保留。':'手动填写的未验证草稿；保存不会调用模型、查询来源、运行统计或扣费。';
    for(const control of byId('method-draft-form').querySelectorAll('input,textarea,select,button'))control.disabled=ro||busy||(draftState.busy&&control.type==='submit');
    byId('method-draft-save').disabled=ro||busy||draftState.busy||!valid||!draftState.selected.size||[...draftState.selected.keys()].some(id=>!draftState.excerpts.has(id))||!draftState.dirty||Boolean(draftState.casRejected);
    for(const id of ['method-draft-read-sources','method-draft-read-plan','method-draft-read-formula'])byId(id).disabled=ro||busy||draftState.busy||!researchId||!byId('method-draft-task').value;
    byId('method-draft-read-history').disabled=!researchId||draftState.busy;
    byId('method-draft-read-tasks').disabled=ro||busy||draftState.busy||!researchId;
    byId('method-draft-more-tasks').hidden=!draftState.catalogNext;byId('method-draft-more-tasks').disabled=ro||busy||draftState.busy||!researchId;
    byId('method-draft-refresh-base').hidden=!draftState.casRejected;byId('method-draft-refresh-base').disabled=ro||busy||draftState.busy;
    byId('method-draft-task').disabled=ro||busy||draftState.busy;
    for(const button of byId('method-draft-pending').querySelectorAll('button'))button.disabled=ro||busy||draftState.busy;
    byId('method-draft-user').hidden=byId('method-draft-origin').value!=='user_proposed';byId('method-draft-plan').hidden=byId('method-draft-origin').value!=='plan_lead';
    financialSync();
  }
  function draftObserve(data){
    const same=draftState.rid===data.research.id;const changed=draftState.target&&(draftState.target.input_revision!==editBase?.revision||draftState.target.problem_digest!==editBase?.digest);
    if(draftState.rid&&!same)draftReset();
    if(changed){draftState.casRejected=null;draftHideMaterials('目标问题修订已变化。已隐藏旧缓存原文，请重新读取引用；手写内容与原选择标识保留。');}
    if(accountScope){const ticket=draftTicket(),account=accountScope;formulaHash({account:JSON.parse(account)}).then(actor=>{if(draftActive(ticket)&&account===accountScope){draftState.actor=actor;draftRenderPending();}}).catch(()=>{});}
    draftState.rid=data.research.id;draftState.target=editBase?{input_revision:editBase.revision,problem_digest:editBase.digest}:null;
    const selected=byId('method-draft-task').value,history=validTaskHistory(data);
    draftState.catalogGeneration++;draftState.catalog.clear();draftState.catalogCursors.clear();draftState.catalogNext=null;draftState.catalogKnown=Boolean(history);
    if(history){for(const item of history)draftState.catalog.set(item.task_id,item);draftState.catalogNext=data.next_task_id;}
    draftRenderCatalog(selected,data.task?.policy_revision==='d1-source-only-v1'?data.task.id:null);draftSync();
  }
  function draftRenderCatalog(selected=byId('method-draft-task').value,fallback=null){
    const picker=byId('method-draft-task');picker.replaceChildren();formulaElement(picker,'option',draftState.catalogKnown?(draftState.catalog.size?'选择含材料或线索的已存记录':'本页没有已存记录'):'资料目录待刷新，请点击“刷新已有资料”。',{value:''});
    for(const item of draftState.catalog.values())formulaElement(picker,'option',`问题修订 ${item.input_revision} · ${item.is_historical?'以前的':'当前的'}流程 · ${item.execution==='COMPLETED'?'已结束':item.execution==='FAILED'?'未完成':item.execution==='CANCELLED'?'已停止':'状态需核对'}`,{value:item.task_id});
    if(draftState.catalog.has(selected))picker.value=selected;else if(fallback&&draftState.catalog.has(fallback))picker.value=fallback;
  }
  async function draftTasks(earlier=false){
    if(draftState.busy||busy||readOnlyView()||!researchId||!draftState.target)return;
    const cursor=earlier?draftState.catalogNext:null;if(earlier&&(!validId(cursor)||draftState.catalogCursors.has(cursor)))return;
    const ticket=draftTicket(),target={...draftState.target},generation=draftState.catalogGeneration,operation=Symbol();let actor=null;
    const active=()=>draftActive(ticket)&&!readOnlyView()&&generation===draftState.catalogGeneration&&actor===draftState.actor&&target.input_revision===draftState.target?.input_revision&&target.problem_digest===draftState.target?.problem_digest&&editBase?.revision===target.input_revision&&editBase?.digest===target.problem_digest;
    draftState.busy=true;draftState.operation=operation;draftSync();
    try{
      if(!await draftSetActor(ticket))return;actor=draftState.actor;
      const root=await draftFetch(`/api/research/${ticket.rid}`+(cursor?'?task_id='+encodeURIComponent(cursor):''),{},ticket,'root'),items=validTaskHistory(root);
      if(!items||(cursor&&(root.task?.id!==cursor||items[0]?.task_id!==cursor)))throw Error('已存资料目录或分页锚点无法完整核对，请主动刷新。');
      if(!active())return;
      const latest=root.revisions?.find(item=>item.revision===target.input_revision);
      if(root.research.current_revision!==target.input_revision||latest?.digest!==target.problem_digest){observeServer(root);editNotice();throw Error('当前问题已有新版本，请明确载入后再读取资料目录；手稿与原操作保留。');}
      if(!await draftAuth(ticket)||!active())return;
      const seen=new Set(earlier?draftState.catalogCursors:[]);if(cursor)seen.add(cursor);
      if(root.next_task_id&&(root.next_task_id===cursor||seen.has(root.next_task_id)))throw Error('资料目录返回了重复分页锚点，已停止追加；不会自动继续读取。');
      const selected=byId('method-draft-task').value;
      if(!earlier)draftState.catalog.clear();
      for(const item of items)draftState.catalog.set(item.task_id,item);
      draftState.catalogCursors=seen;draftState.catalogNext=root.next_task_id;draftState.catalogKnown=true;draftState.catalogGeneration++;
      // An anchored history page may describe an older current_problem. Only
      // its authorized directory metadata enters this picker, never the form.
      observeServer(root);editNotice();draftRenderCatalog(selected);
      byId('method-draft-material-status').textContent=earlier?'已追加更早的资料目录；当前问题、手稿与原选择保持不变。读取正文和保存时仍核当前权限。':'已按当前权限刷新已有资料目录；请自行选择并读取需要的材料，不会启动采集或替换手稿。';
    }catch(error){if(active()){draftState.catalogGeneration++;draftState.catalog.clear();draftState.catalogNext=null;draftState.catalogCursors.clear();draftState.catalogKnown=false;draftRenderCatalog();draftHideMaterials('资料目录暂时无法核对，已隐藏旧资料正文；手写内容与原操作保留。');byId('method-draft-status').textContent=draftError(error);}}
    finally{if(draftState.operation===operation){draftState.busy=false;draftState.operation=null;draftSync();}}
  }
  function draftRenderMaterials(){
    const box=byId('method-draft-materials');box.replaceChildren();
    for(const [id,item] of draftState.excerpts){const article=formulaElement(box,'article','',{className:'draft-material'});const label=formulaElement(article,'label','',{className:'check'});const check=document.createElement('input');check.type='checkbox';check.checked=draftState.selected.has(id);check.disabled=readOnlyView();label.append(check,document.createTextNode(item.title||'来源未提供标题'));
      formulaElement(article,'p',`原问题修订 ${item.input_revision} · 来源修订 ${item.source_revision} · ${item.execution_mode==='live'?'来源读取记录':'受控来源记录'}；仅短摘录，不表示方法已验证`,{className:'hint'});formulaElement(article,'blockquote',item.quote);
      check.addEventListener('change',()=>{if(readOnlyView())return;if(check.checked){if(draftState.selected.size>=20){check.checked=false;byId('method-draft-status').textContent='每份草稿最多20条摘录。';return;}draftState.selected.set(id,item.ref);}else draftState.selected.delete(id);draftChanged();byId('method-draft-material-status').textContent=`已读取 ${draftState.excerpts.size} 条可选摘录，已明确选择 ${draftState.selected.size} 条；保存仍核当前权限。`;});
    }
    byId('method-draft-material-status').textContent=`已读取 ${draftState.excerpts.size} 条可选摘录，已明确选择 ${draftState.selected.size} 条。每次保存仍由服务端核当前权限。`;
  }
  async function draftTask(ticket,policy){
    const id=byId('method-draft-task').value;if(!validId(id))throw Error('请先选择一个已保存的流程。');
    const value=await draftFetch(`/api/research/${ticket.rid}?task_id=${id}`,{},ticket,'root');
    if(value.research?.id!==ticket.rid||value.task?.id!==id||!planInt(value.current_problem?.revision)||!planDigest(value.current_problem?.digest))throw Error('所选流程与本研究无法绑定。');
    if(!policy.includes(value.task.policy_revision))throw Error('所选流程没有这种材料，请选择相应的来源、计划或公式流程。');return value;
  }
  async function draftMaterials(){
    if(draftState.busy||busy||readOnlyView())return;const ticket=draftTicket(),operation=Symbol();draftState.busy=true;draftState.operation=operation;draftSync();
    try{
      if(!await draftSetActor(ticket))return;const view=await draftTask(ticket,['d1-source-only-v1']),task=view.task;const records={sources:[],excerpts:[]};
      for(const kind of ['sources','excerpts']){let cursor=null,pages=0;do{const data=await draftFetch(`/api/research/${ticket.rid}/records?task_id=${task.id}&kind=${kind}`+(cursor?'&cursor='+encodeURIComponent(cursor):''),{},ticket,'root');
        if(data.kind!==kind||!Array.isArray(data.items)||data.items.length>20||!planInt(data.research_version)||!planInt(data.task_version)||(data.next_cursor!==null&&typeof data.next_cursor!=='string'))throw Error('来源记录页无法完整核对。');
        records[kind].push(...data.items);cursor=data.next_cursor;if(++pages>20)throw Error('来源记录较多，请分批选择；未自动截断引用。');}while(cursor);}
      if(!draftActive(ticket)||!await draftAuth(ticket))return;
      for(const excerpt of records.excerpts){const source=records.sources.find(v=>v.id===excerpt.source_id&&v.revision===excerpt.source_revision);
        if(!source||!validId(excerpt.id)||excerpt.research_id!==ticket.rid||excerpt.task_id!==task.id||excerpt.input_revision!==task.input_revision||source.research_id!==ticket.rid||source.task_id!==task.id||source.input_revision!==task.input_revision||!planInt(excerpt.source_revision)||!planDigest(excerpt.text_digest)||excerpt.text_digest!==source.extracted_text_digest||!planText(excerpt.quote,1000)||!Number.isSafeInteger(excerpt.start)||!Number.isSafeInteger(excerpt.end)||excerpt.start<0||excerpt.end>200000||excerpt.end-excerpt.start!==Array.from(excerpt.quote).length||typeof source.title!=='string'||Array.from(source.title).length>500)throw Error('摘录与原来源的范围或提取文本摘要不匹配。');
        draftState.excerpts.set(excerpt.id,{...excerpt,title:source.title,execution_mode:source.execution_mode,ref:{excerpt_id:excerpt.id,source_revision:excerpt.source_revision,content_digest:excerpt.text_digest,start:excerpt.start,end:excerpt.end}});
      }
      draftRenderMaterials();
    }catch(error){if(draftActive(ticket)){draftHideMaterials('本次材料未完整核对，已隐藏缓存原文。请重新读取；手写内容保留。');byId('method-draft-status').textContent=draftError(error);}}
    finally{if(draftState.operation===operation){draftState.busy=false;draftState.operation=null;draftSync();}}
  }
  async function draftPlan(){
    if(draftState.busy||busy||readOnlyView())return;const ticket=draftTicket(),operation=Symbol();draftState.busy=true;draftState.operation=operation;draftSync();
    try{
      if(!await draftSetActor(ticket))return;const view=await draftTask(ticket,['native-plan-v1','funded-plan-v1']),anchor=planAnchor(view),legacy=view.task.policy_revision==='funded-plan-v1',meta=legacy?view.plan:view.native_plan;
      if(!anchor||!planMeta(meta,legacy))throw Error('原计划状态无法核对。');const value=await draftFetch(`/api/research/${ticket.rid}/plan-results/${meta.result_ref}`,{},ticket,legacy?'plan_v1':'plan_v2');const {content,...metadata}=value;
      if(!planMeta(metadata,legacy)||metadata.result_ref!==meta.result_ref||metadata.task_id!==anchor.task_id)throw Error('原计划引用无法核对。');const checked=planValidateResult(content,metadata,anchor,legacy,null);
      if(!draftActive(ticket)||!await draftAuth(ticket))return;const box=byId('method-draft-plan-choices'),previous=box.querySelector('input[name="method-draft-plan-origin"]:checked'),selected=previous&&draftState.plans.get(previous.value);box.replaceChildren();draftState.plans.clear();draftState.origin=null;draftClearView();
      checked.proposal.candidates.forEach((candidate,candidate_index)=>candidate.method_leads.forEach((lead,lead_index)=>{const key=meta.result_ref+':'+candidate_index+':'+lead_index;const origin={kind:'plan_lead',plan_contract:legacy?'funded-plan-v1':planContract,result_ref:meta.result_ref,candidate_index,lead_index};draftState.plans.set(key,origin);const label=formulaElement(box,'label','',{className:'check'});const radio=document.createElement('input');radio.type='radio';radio.name='method-draft-plan-origin';radio.value=key;if(selected&&formulaCanonical(selected)===formulaCanonical(origin)){radio.checked=true;draftState.origin=origin;}label.append(radio,document.createTextNode(`${candidate.label}：${lead}（原问题修订 ${checked.input_revision}，待核验线索）`));radio.addEventListener('change',()=>{draftState.origin=origin;draftChanged('已选择原计划线索；方法、条件与验证计划仍需自己填写。');});}));
      if(!box.children.length)formulaElement(box,'p','原计划没有可选择的方法线索，请使用人工提议。');
    }catch(error){if(draftActive(ticket)){draftState.origin=null;draftState.plans.clear();byId('method-draft-plan-choices').replaceChildren();byId('method-draft-status').textContent=draftError(error);}}
    finally{if(draftState.operation===operation){draftState.busy=false;draftState.operation=null;draftSync();}}
  }
  async function draftFormula(){
    if(draftState.busy||busy||readOnlyView())return;const ticket=draftTicket(),operation=Symbol();draftState.busy=true;draftState.operation=operation;draftSync();
    try{
      if(!await draftSetActor(ticket))return;const view=await draftTask(ticket,['local-formula-v1']),meta=view.formula_check;
      if(!validateFormulaMetadata(meta)||!meta.result_available)throw Error('该公式流程没有可读取的已存结果。');const data=await draftFetch(`/api/research/${ticket.rid}/formula-results/${meta.result_ref}`,{},ticket,'root');
      if(data.state!=='available'||!validateFormulaMetadata(data.metadata,meta.result_ref)||data.metadata.result_available!==true||!recordTime(data.metadata.formula_result_recorded_at)||data.metadata.formula_digest!==view.current_problem.formula_snapshot?.formula_digest||data.provenance?.problem_digest!==view.current_problem.digest||typeof data.provenance?.execution_attested!=='boolean')throw Error('原公式结果与问题快照无法核对。');
      if(!draftActive(ticket)||!await draftAuth(ticket))return;draftState.formulas.set(meta.result_ref,data.metadata);const select=byId('method-draft-formula');if(![...select.options].some(v=>v.value===meta.result_ref))formulaElement(select,'option',`公式记录 ${meta.result_ref} · 原保存时间 ${data.metadata.formula_result_recorded_at} · 原问题修订 ${view.current_problem.revision} · ${data.provenance.execution_attested?'原执行有证明':'原执行未获证明'}（不升级本草稿结论）`,{value:meta.result_ref});
      byId('method-draft-status').textContent='已读取原公式引用，可选关联；不会重新检查或把旧通过当新问题验证。';
    }catch(error){if(draftActive(ticket))byId('method-draft-status').textContent=draftError(error);}
    finally{if(draftState.operation===operation){draftState.busy=false;draftState.operation=null;draftSync();}}
  }
  function draftLines(id){const values=byId(id).value.split('\n').filter(v=>v.trim().length);if(!values.length||values.length>20||values.some(v=>!planText(v,2000)))throw Error('映射、不可迁移项和竞争解释各需1–20项，每项最多2000字。');return values;}
  function draftVisiblePlanOrigin(){
    const selected=byId('method-draft-plan-choices').querySelector('input[name="method-draft-plan-origin"]:checked');
    const origin=selected&&draftState.plans.get(selected.value);
    if(!origin||!draftState.origin||formulaCanonical(origin)!==formulaCanonical(draftState.origin))throw Error('请从当前显示的真实计划线索中明确选择一项。');
    return origin;
  }
  function draftPayload(){
    if(!editBase||!researchId||methodDirty||formulaState.dirty||(observed&&(observed.revision!==editBase.revision||observed.digest!==editBase.digest)))throw Error('请先保存并明确载入当前问题；方法文字未清空。');
    const selectedOrigin=byId('method-draft-origin').value==='plan_lead'?draftVisiblePlanOrigin():null;
    if(!draftState.selected.size||draftState.selected.size>20||[...draftState.selected.keys()].some(id=>!draftState.excerpts.has(id)))throw Error('请明确选择1–20条刚核对的已存摘录。');
    const method=byId('method-draft-method').value;if(!planText(method,2000))throw Error('请填写方法及适用条件（最多2000字）。');
    const origin=byId('method-draft-origin').value==='plan_lead'?selectedOrigin:{kind:'user_proposed',label:byId('method-draft-label').value,description:method};
    if(!origin||origin.kind==='user_proposed'&&!planText(origin.label,120))throw Error('请填写人工方法名称，或从真实已存计划中选择线索。');
    const data={input_revision:editBase.revision,expected_research_version:observed?.researchVersion||editBase.researchVersion,excerpt_refs:[...draftState.selected.values()],origin,method,mapping:draftLines('method-draft-mapping'),nontransferable:draftLines('method-draft-nontransferable'),competing_explanations:draftLines('method-draft-competing'),test_plan:{question:byId('method-draft-question').value,measurement:byId('method-draft-measurement').value,primary_outcome:byId('method-draft-outcome').value,falsification:byId('method-draft-falsification').value,stop_rule:byId('method-draft-stop').value},formula_result_ref:byId('method-draft-formula').value||null,supersedes_ref:draftState.supersedes};
    if(Object.values(data.test_plan).some(v=>!planText(v,2000)))throw Error('五项验证计划都需自己填写，每项最多2000字。');if(new TextEncoder().encode(formulaCanonical(data)).length>65536)throw Error('草稿请求超过64KiB，请减少文字或引用；未自动截断。');return draftCheckRequest(data);
  }
  function draftCheckRequest(value){
    const list=(items,max,check,min=1)=>Array.isArray(items)&&items.length>=min&&items.length<=max&&items.every(check);
    if(!planKeys(value,['input_revision','expected_research_version','excerpt_refs','origin','method','mapping','nontransferable','competing_explanations','test_plan','formula_result_ref','supersedes_ref'])||!planInt(value.input_revision)||!planInt(value.expected_research_version)||!planText(value.method,2000)||
      !list(value.excerpt_refs,20,ref=>planKeys(ref,['excerpt_id','source_revision','content_digest','start','end'])&&validId(ref.excerpt_id)&&planInt(ref.source_revision)&&planDigest(ref.content_digest)&&Number.isSafeInteger(ref.start)&&Number.isSafeInteger(ref.end)&&ref.start>=0&&ref.end<=200000&&ref.end>ref.start&&ref.end-ref.start<=1000)||new Set(value.excerpt_refs.map(ref=>ref.excerpt_id)).size!==value.excerpt_refs.length||
      !list(value.mapping,20,v=>planText(v,2000))||!list(value.nontransferable,20,v=>planText(v,2000))||!list(value.competing_explanations,20,v=>planText(v,2000))||!planKeys(value.test_plan,['question','measurement','primary_outcome','falsification','stop_rule'])||Object.values(value.test_plan).some(v=>!planText(v,2000))||
      (value.formula_result_ref!==null&&!validId(value.formula_result_ref))||(value.supersedes_ref!==null&&!validId(value.supersedes_ref)))throw Error('草稿字段、验证计划或引用范围不完整，未展示或发送。');
    const origin=value.origin;
    if(origin?.kind==='user_proposed'){
      if(!planKeys(origin,['kind','label','description'])||!planText(origin.label,120)||!planText(origin.description,2000))throw Error('人工提议字段无法核对。');
    }else if(origin?.kind==='plan_lead'){
      if(!planKeys(origin,['kind','plan_contract','result_ref','candidate_index','lead_index'])||!['funded-plan-v1','funded-plan-v2'].includes(origin.plan_contract)||!validId(origin.result_ref)||!Number.isSafeInteger(origin.candidate_index)||origin.candidate_index<0||origin.candidate_index>4||!Number.isSafeInteger(origin.lead_index)||origin.lead_index<0||origin.lead_index>1)throw Error('方法线索的原计划引用无法核对。');
    }else throw Error('当前没有可信知识库目录；只能选择人工提议或实际计划线索。');
    if(new TextEncoder().encode(formulaCanonical(value)).length>65536)throw Error('草稿请求超过64KiB，未自动截断。');return value;
  }
  function draftMetadata(meta,root){
    if(!planKeys(meta,['draft_ref','input_revision','problem_digest','research_version_before','research_version_after','created_at','content_digest','is_historical','origin_kind','validation_status','execution_status'])||!validId(meta.draft_ref)||!planInt(meta.input_revision)||!planDigest(meta.problem_digest)||!planInt(meta.research_version_before)||meta.research_version_after!==meta.research_version_before+1||!planInt(meta.research_version_after)||!recordTime(meta.created_at)||!planDigest(meta.content_digest)||typeof meta.is_historical!=='boolean'||!['plan_lead','user_proposed'].includes(meta.origin_kind)||meta.validation_status!=='unverified'||meta.execution_status!=='not_executed')throw Error('草稿元数据用途或状态无法核对。');
    const problem=root.revisions?.find(v=>v.revision===meta.input_revision);
    if(root.research?.id!==researchId||!problem||problem.digest!==meta.problem_digest||root.research_version<meta.research_version_after||meta.is_historical!==(meta.input_revision!==root.research.current_revision))throw Error('草稿与原问题修订无法绑定。');return meta;
  }
  async function draftValidate(value,ticket,ref=null,original=null){
    if(!planKeys(value,['metadata','content'])||!planKeys(value.content,['schema_version','contract_revision','request','sources','origin','formula']))throw Error('草稿正文格式无法核对。');
    const root=await draftFetch(`/api/research/${ticket.rid}`,{},ticket,'root');if(!draftActive(ticket))throw Error('原读取已失效。');const meta=draftMetadata(value.metadata,root),body=value.content,req=draftCheckRequest(body.request);
    if(ref&&meta.draft_ref!==ref||body.schema_version!==schema||body.contract_revision!==draftContract||!planObject(req)||req.input_revision!==meta.input_revision||req.expected_research_version!==meta.research_version_before||body.origin?.kind!==meta.origin_kind||body.origin?.verification!=='unverified'||!Array.isArray(body.sources)||body.sources.length!==req.excerpt_refs?.length||body.sources.length<1||body.sources.length>20||new TextEncoder().encode(formulaCanonical(body)).length>131072||await formulaHash(body)!==meta.content_digest)throw Error('草稿摘要、原时间或引用绑定无法核对。');
    if(original&&(formulaCanonical(req)!==formulaCanonical(original.data)||meta.problem_digest!==original.problem_digest))throw Error('保存回执与原提交内容不同，原操作保留。');
    for(let i=0;i<body.sources.length;i++){const source=body.sources[i],expect=req.excerpt_refs[i];if(!planKeys(source,['excerpt_id','snapshot_id','source_id','source_revision','content_digest','raw_digest','excerpt_digest','snapshot_digest','start','end','quote','title','canonical_url','licence_basis','task_id','attempt','input_revision'])||!validId(source.excerpt_id)||!validId(source.snapshot_id)||!validId(source.source_id)||!validId(source.task_id)||source.attempt!==1||!planInt(source.input_revision)||!planInt(source.source_revision)||!planDigest(source.raw_digest)||!planDigest(source.excerpt_digest)||!planDigest(source.snapshot_digest)||['excerpt_id','source_revision','content_digest','start','end'].some(key=>source[key]!==expect[key])||!planText(source.quote,1000)||Array.from(source.quote).length!==source.end-source.start||typeof source.title!=='string'||Array.from(source.title).length>500||typeof source.canonical_url!=='string'||Array.from(source.canonical_url).length>2048||typeof source.licence_basis!=='string'||Array.from(source.licence_basis).length>700)throw Error('原摘录范围、摘要或来源信息无法核对。');}
    if(body.origin.kind==='plan_lead'){if(!planKeys(body.origin,['kind','plan_contract','result_ref','candidate_index','lead_index','label','lead','mode','producer','result_digest','input_revision','verification'])||!['funded-plan-v1','funded-plan-v2'].includes(body.origin.plan_contract)||!validId(body.origin.result_ref)||!planDigest(body.origin.result_digest)||!planInt(body.origin.input_revision)||!planText(body.origin.label,2000)||!planText(body.origin.lead,2000)||!['fixture','controlled_fixture','native_live'].includes(body.origin.mode)||!['owned-plan-fixture-v1','core-controlled-native-v1','owned-native-plan-runtime-v1'].includes(body.origin.producer)||['kind','plan_contract','result_ref','candidate_index','lead_index'].some(key=>body.origin[key]!==req.origin?.[key]))throw Error('计划线索的原记录无法核对。');}
    else if(!planKeys(body.origin,['kind','label','description','mode','verification'])||body.origin.kind!=='user_proposed'||body.origin.mode!=='user_proposed'||body.origin.label!==req.origin?.label||body.origin.description!==req.origin?.description)throw Error('人工提议来源无法核对。');
    if(req.formula_result_ref===null){if(body.formula!==null)throw Error('未选择的公式被加入草稿。');}
    else if(!planKeys(body.formula,['result_ref','metadata','result_digest','input_revision','comparison_scope','outcomes','execution_attested'])||body.formula?.result_ref!==req.formula_result_ref||!validateFormulaMetadata(body.formula.metadata,req.formula_result_ref)||body.formula.metadata.result_available!==true||!recordTime(body.formula.metadata.formula_result_recorded_at)||!planDigest(body.formula.result_digest)||!planInt(body.formula.input_revision)||typeof body.formula.execution_attested!=='boolean'||!['expression','equation_form','initial_value_problem'].includes(body.formula.comparison_scope)||!Array.isArray(body.formula.outcomes)||body.formula.outcomes.length<1||body.formula.outcomes.length>4||body.formula.outcomes.some(outcome=>!planKeys(outcome,['check_kind','status','relation'])||!Object.hasOwn(formulaChecks,outcome.check_kind)||!['passed','failed','inconclusive','unsupported','resource_limit'].includes(outcome.status)||!['algebraic_identity','conditional_model_equivalence','local_approximation','partial_structure','not_equivalent','undetermined'].includes(outcome.relation)))throw Error('原公式关联无法核对。');
    if(!draftActive(ticket))throw Error('原读取已失效。');return {meta,body,root};
  }
  function draftShow({meta,body,root}){
    draftClearView();draftState.view=meta.draft_ref;const box=byId('method-draft-view'),add=(tag,text,options={})=>formulaElement(box,tag,text,options);add('h3','只读：未验证的方法草稿');add('p','人工整理 · 未执行验证；来源已链接不证明方法成熟、迁移有效或数学通过。',{className:'scope'});add('p',`目标问题修订 ${meta.input_revision}${meta.is_historical?'（以前的问题版本）':''} · 原保存时间 ${new Date(meta.created_at).toLocaleString('zh-CN')}`);
    const details=add('details','');formulaElement(details,'summary','记录编号与原保存时间');formulaElement(details,'p',meta.draft_ref,{id:'method-draft-view-ref'});const time=formulaElement(details,'time','',{id:'method-draft-view-time'});showTime(time,meta.created_at);
    const problem=root.revisions.find(v=>v.revision===meta.input_revision);add('h4','原问题');add('p',problem.original_input);add('h4','方法来源');add('p',body.origin.kind==='user_proposed'?`人工提议：${body.origin.label}`:`计划提名：${body.origin.label} / ${body.origin.lead}（原问题修订 ${body.origin.input_revision}，${body.origin.mode==='native_live'?'原生计划记录':body.origin.mode==='fixture'?'旧版夹具记录':'受控夹具记录'}，仍待核验）`);
    add('h4','方法与适用条件');add('p',body.request.method);
    for(const [title,values] of [['映射',body.request.mapping],['不可直接迁移',body.request.nontransferable],['竞争解释',body.request.competing_explanations]]){add('h4',title);const list=add('ul','');for(const value of values)formulaElement(list,'li',value);}
    for(const [title,key] of [['验证问题','question'],['测量方式','measurement'],['主要结果指标','primary_outcome'],['反证条件','falsification'],['停止条件','stop_rule']]){add('h4',title);add('p',body.request.test_plan[key]);}
    add('h4','原来源短摘录');for(const source of body.sources){add('p',`${source.title||'未提供标题'} · 原问题修订 ${source.input_revision} / 来源修订 ${source.source_revision}`);add('blockquote',source.quote);add('p',source.licence_basis,{className:'hint'});}
    if(body.formula){add('h4','关联的原公式检查');add('p','原公式结果编号与原保存时间');add('p',body.formula.result_ref,{id:'method-draft-view-formula-ref'});const formulaTime=add('time','',{id:'method-draft-view-formula-time'});showTime(formulaTime,body.formula.metadata.formula_result_recorded_at);add('p',`原问题修订 ${body.formula.input_revision} · ${{expression:'表达式',equation_form:'方程形式',initial_value_problem:'初值问题'}[body.formula.comparison_scope]} · ${body.formula.execution_attested?'原执行有证明':'原执行未获证明'}；不表示本方法通过验证。`);for(const outcome of body.formula.outcomes)add('p',`${formulaChecks[outcome.check_kind]||'原检查'}：${{passed:'该有限检查通过',failed:'该检查不通过',inconclusive:'不足以下判断',unsupported:'不支持',resource_limit:'达到资源边界'}[outcome.status]||'状态未核对'}；关系为 ${{algebraic_identity:'代数恒等关系',conditional_model_equivalence:'有条件的模型对应',local_approximation:'局部近似',partial_structure:'部分结构相似',not_equivalent:'不等价',undetermined:'尚未确定'}[outcome.relation]||'尚未确定'}`);}
    byId('method-draft-view-status').textContent='只读查看原稿；编辑区内容未替换。';
  }
  async function draftRead(ref){
    const ticket=draftReadTicket();draftClearView();byId('method-draft-view-status').textContent='正在按当前权限重读原稿与依赖…';
    try{if(!validId(ref)||!await draftSetActor(ticket))return;const checked=await draftValidate(await draftFetch(`/api/research/${ticket.rid}/method-drafts/${ref}`,{},ticket),ticket,ref);if(draftActive(ticket)&&await draftAuth(ticket))draftShow(checked);}
    catch(error){if(draftActive(ticket)){draftClearView();byId('method-draft-view-status').textContent=draftError(error);if(error.code==='DEPENDENCY_UNAVAILABLE')draftHideMaterials('原引用当前不可完整读取，缓存原文已隐藏；手写内容保留。');}}
  }
  async function draftHistory(cursor=null){
    const ticket=draftReadTicket();byId('method-draft-history').replaceChildren();byId('method-draft-history-status').textContent='正在核对草稿历史…';
    try{if(!await draftSetActor(ticket))return;const [page,root]=await Promise.all([draftFetch(`/api/research/${ticket.rid}/method-drafts?limit=20`+(cursor?'&cursor='+cursor:''),{},ticket),draftFetch(`/api/research/${ticket.rid}`,{},ticket,'root')]);
      if(!planKeys(page,['items','next_cursor'])||!Array.isArray(page.items)||page.items.length>20||(page.next_cursor!==null&&!validId(page.next_cursor)))throw Error('草稿列表页无法完整核对。');if(!draftActive(ticket)||!await draftAuth(ticket))return;draftState.history.clear();const box=byId('method-draft-history');
      for(const value of page.items){const meta=draftMetadata(value,root);draftState.history.set(meta.draft_ref,meta);const row=formulaElement(box,'li','');formulaElement(row,'p',`问题修订 ${meta.input_revision} · ${new Date(meta.created_at).toLocaleString('zh-CN')} · 未验证 / 未执行`);const read=formulaElement(row,'button','只读查看原稿',{type:'button',className:'secondary'});read.addEventListener('click',()=>draftRead(meta.draft_ref));const parent=formulaElement(row,'button','关联为上一稿（不填入答案）',{type:'button',className:'secondary'});parent.disabled=readOnlyView();parent.addEventListener('click',()=>{if(readOnlyView())return;draftState.supersedes=meta.draft_ref;byId('method-draft-parent').textContent=`已关联原问题修订 ${meta.input_revision} 的草稿；保存将生成新记录，不改旧稿。`;draftChanged();});}
      if(page.next_cursor){const more=formulaElement(box,'button','读取下一页草稿',{type:'button',className:'secondary'});more.addEventListener('click',()=>draftHistory(page.next_cursor));}
      byId('method-draft-history-status').textContent=page.items.length?`本页 ${page.items.length} 条；每次查看仍核当前引用权限。`:'此页没有已返回的草稿；不会自动创建。';draftRenderPending();
    }catch(error){if(draftActive(ticket)){draftClearView();draftState.history.clear();byId('method-draft-history').replaceChildren();byId('method-draft-history-status').textContent='历史未完整读取，不能据此判断没有记录。'+draftError(error);}}
  }
  function draftRenderPending(){
    const box=byId('method-draft-pending');box.replaceChildren();for(const pending of draftPending()){const row=formulaElement(box,'div','');formulaElement(row,'p',`仍有问题修订 ${pending.task_request?.data?.input_revision||'待核对'} 的原保存待确认；新输入不会替换原提交。`,{className:'hint'});const button=formulaElement(row,'button','核对这一笔原保存',{type:'button',className:'secondary'});button.disabled=readOnlyView()||draftState.busy;button.addEventListener('click',()=>draftSave(pending));}
  }
  async function draftSave(recover=null){
    if(draftState.busy||busy||readOnlyView())return;let ticket=draftTicket(),pending,original;const operation=Symbol();draftState.busy=true;draftState.operation=operation;draftSync();
    try{
      if(!await draftSetActor(ticket))return;
      if(draftState.casRejected)throw Error('本次保存已明确未写入，请先核对当前问题版本，再主动保存。');
      let scope;
      if(recover){if(!draftPending().some(v=>v.slot===recover.slot&&v.key===recover.key))throw Error('原保存不属于当前账户读取范围。');original=recover.task_request;scope=recover.slot.slice('structure-research-pending:'.length);}
      else{
        const data=draftPayload(),semantic={...data};delete semantic.expected_research_version;const intent=await formulaHash(semantic);if(!draftActive(ticket))return;
        scope=`method-draft-v1:${draftState.actor}:${researchId}:${data.input_revision}:${intent}`;const cached=sessionStorage.getItem('structure-research-pending:'+scope);
        if(cached)original=JSON.parse(cached).task_request;
        else{const root=await draftFetch(`/api/research/${ticket.rid}`,{},ticket,'root');if(root.current_problem?.revision!==data.input_revision||root.current_problem.digest!==editBase.digest)throw Error('当前问题已更新，请明确载入后再保存，手写内容已保留。');data.expected_research_version=root.research_version;original={data,problem_digest:root.current_problem.digest};}
      }
      if(!planObject(original?.data)||original.data.input_revision<1||!planDigest(original.problem_digest))throw Error('原保存绑定无法核对，未发送新请求。');
      draftCheckRequest(original.data);
      const body=JSON.stringify({schema_version:schema,contract_revision:draftContract,data:original.data});pending=await operationKey(scope,body,original.data.input_revision,original);if(!draftActive(ticket))return;
      byId('method-draft-status').textContent='正在保存这份人工未验证草稿；不会执行研究或改写旧稿。';
      const ack=await draftValidate(await draftFetch(`/api/research/${ticket.rid}/method-drafts`,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':pending.key},body},ticket,'save_post'),ticket,null,original);
      const checked=await draftValidate(await draftFetch(`/api/research/${ticket.rid}/method-drafts/${ack.meta.draft_ref}`,{},ticket),ticket,ack.meta.draft_ref,original);
      if(['created_at','content_digest','problem_digest','input_revision','research_version_before','research_version_after'].some(key=>checked.meta[key]!==ack.meta[key]))throw Error('原稿标识或原保存时间无法独立核对，key保留。');
      if(!await draftAuth(ticket)||!draftActive(ticket))return;formulaRetire(pending);
      if(!recover){draftState.dirty=false;draftShow(checked);}byId('method-draft-status').textContent=recover?'原保存已确认；当前编辑区未替换，记录仍未验证/未执行。':'已保存新的验证草稿；未验证、未执行，不代表研究完成。';
      if(observed&&observed.revision===checked.meta.input_revision&&observed.digest===checked.meta.problem_digest&&observed.researchVersion<checked.meta.research_version_after)observed.researchVersion=checked.meta.research_version_after;
    }catch(error){if(draftActive(ticket)){
      if(pending&&original&&error[draftCasRejection]===true&&await draftAuth(ticket)&&draftActive(ticket)){
        formulaRetire(pending);draftState.casRejected={input_revision:original.data.input_revision,problem_digest:original.problem_digest,expected_research_version:original.data.expected_research_version};
        byId('method-draft-status').textContent='本次保存被明确拒绝，未写入；手写内容保留。请先核对当前问题版本，再主动保存为新操作。';
      }else if(draftActive(ticket)){byId('method-draft-status').textContent=draftError(error)+' 输入与原保存意图仍保留。';if(error.code==='DEPENDENCY_UNAVAILABLE')draftHideMaterials('引用当前不可完整读取，原文缓存已隐藏；手写内容保留，请重新选择。');}
    }}
    finally{if(draftState.operation===operation){draftState.busy=false;draftState.operation=null;draftRenderPending();draftSync();}}
  }
  async function draftRefreshBase(){
    if(!draftState.casRejected||draftState.busy||busy||readOnlyView())return;
    const rejected=draftState.casRejected,ticket=draftTicket(),operation=Symbol();draftState.busy=true;draftState.operation=operation;draftSync();
    try{
      if(!await draftAuth(ticket))return;const root=await draftFetch(`/api/research/${ticket.rid}`,{},ticket,'root');
      if(root.research?.id!==ticket.rid||root.current_problem?.revision!==rejected.input_revision||root.current_problem.digest!==rejected.problem_digest||editBase?.revision!==rejected.input_revision||editBase.digest!==rejected.problem_digest||!planInt(root.research_version)||root.research_version<=rejected.expected_research_version||root.research_version>=2147483647)throw Error('问题版本或内容已变化，请明确载入当前问题后重新核对引用；手写内容保留。');
      if(!await draftAuth(ticket)||!draftActive(ticket)||draftState.casRejected!==rejected)return;
      if(!observed||observed.revision!==rejected.input_revision||observed.digest!==rejected.problem_digest)throw Error('当前问题基准无法核对，未刷新或再次保存。');
      observed.researchVersion=Math.max(observed.researchVersion,root.research_version);draftState.casRejected=null;
      byId('method-draft-status').textContent='已核对当前问题内容与版本，手写内容保留。可主动再次保存；尚未提交新操作。';
    }catch(error){if(draftActive(ticket))byId('method-draft-status').textContent=draftError(error);}
    finally{if(draftState.operation===operation){draftState.busy=false;draftState.operation=null;draftSync();}}
  }
  function initDraft(){
    byId('method-draft-refresh-base').addEventListener('click',draftRefreshBase);
    for(const id of draftFields)byId(id).addEventListener('input',()=>draftChanged());
    byId('method-draft-origin').addEventListener('change',()=>{draftState.origin=null;for(const radio of byId('method-draft-plan-choices').querySelectorAll('input'))radio.checked=false;draftChanged();});byId('method-draft-formula').addEventListener('change',()=>draftChanged());
    byId('method-draft-task').addEventListener('change',()=>{draftState.epoch++;byId('method-draft-material-status').textContent='选择仅改变待读取流程，不会启动任何任务。';draftSync();});
    byId('method-draft-read-tasks').addEventListener('click',()=>draftTasks());byId('method-draft-more-tasks').addEventListener('click',()=>draftTasks(true));byId('method-draft-read-sources').addEventListener('click',draftMaterials);byId('method-draft-read-plan').addEventListener('click',draftPlan);byId('method-draft-read-formula').addEventListener('click',draftFormula);byId('method-draft-read-history').addEventListener('click',()=>draftHistory());
    byId('method-draft-clear-parent').addEventListener('click',()=>{draftState.supersedes=null;byId('method-draft-parent').textContent='未关联上一稿。';draftChanged();});byId('method-draft-form').addEventListener('submit',event=>{event.preventDefault();draftSave();});
  }

  function status(message, error = false) {
    byId('status').textContent = message;
    byId('status').dataset.error = String(error);
  }
  function setBusy(value) {
    busy = value;
    // Freeze the submitted draft until the receipt is handled. Otherwise a
    // late render could silently replace edits made while fetch was pending.
    for (const control of form.querySelectorAll('input, textarea, select, button')) control.disabled = value || (readOnlyView() && !['reload','advanced-tools-toggle'].includes(control.id));
    observationSync();
    syncTaskButtons();
    syncFormulaControls();
    planSync();
    draftSync();
    financialSync();
    evidenceUI?.observe();
  }
  function normalizeProblem(problem) {
    // Match ProblemInput exactly; original_input intentionally stays verbatim.
    return {...problem, objective:problem.objective.normalize('NFC'), summary:problem.summary.normalize('NFC'),
      constraints:problem.constraints.map(value => value.normalize('NFC')),
      unknowns:problem.unknowns.map(value => value.normalize('NFC')),
      variables:problem.variables.map(variable => ({...variable, label:variable.label.normalize('NFC'),
        observation:variable.observation === null ? null : variable.observation.normalize('NFC')}))};
  }
  function clearPrivateView(cause = 'inflight_navigation') {
    registryUI?.reset(cause);
    scenarioUI?.reset(cause);
    evidenceUI?.reset();
    financialReset();
    draftReset();
    planReset();
    formulaReset();
    historySeen = false; clearTaskHistory();
    byId('view-context').hidden = true; byId('view-context').textContent = '';
    byId('problem-meta').hidden = true; showTime(byId('problem-created'),null);
    invalidateMethod(); methodSeen = false; methodDirty = false; clearMethod('',true);
    accountScope = null;
    privateGeneration++;
    listGeneration++;
    listCursor = null;
    listBusy = false;
    listSeen.clear();
    byId('my-research').hidden = true;
    byId('research-list-items').replaceChildren();
    byId('research-list-status').textContent = '';
    byId('research-list-more').hidden = true;
    invalidateKB();
    summaryEdited = false;
    current = null;
    editBase = null;
    observed = null;
    variables = [];
    form.reset();
    observationReset();
    showAdvanced(false);
    form.hidden = true;
    byId('history').hidden = true;
    byId('history-items').replaceChildren();
    byId('variables').textContent = '';
    byId('access').hidden = false;
    taskData = null;
    byId('task-section').hidden = true;
    byId('task-notes').replaceChildren();
    sourcePreview = null;
    sourceApproval = null;
    sourcePreviewGeneration++;
    byId('source-section').hidden = true;
    byId('source-plan').textContent = '';
    byId('source-query').value = '';
    byId('source-status').textContent = '';
    byId('source-confirm').hidden = true;
    byId('source-records').replaceChildren();
    sourceRecordScope = null;
    sourceRecordGeneration++;
    registryUI?.observe();
    scenarioUI?.observe();
  }
  async function request(url, options = {}, isCurrent = () => true) {
    const privateScope = privateGeneration;
    const active = response => privateScope === privateGeneration && isCurrent(response);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, {...options, credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
      if (!active(response)) throw new Error('较早的来源读取已失效。');
      const payload = await response.json();
      if (!active(response)) throw new Error('较早的来源读取已失效。');
      if (!response.ok) {
        const error = new Error(payload.error?.message || '操作暂时无法完成，请保留当前内容。');
        error.status = response.status;
        error.code = payload.error?.code;
        if (response.status === 401 || response.status === 404 || payload.error?.code === 'AUTHORIZATION_STALE') {
          clearPrivateView(response.status === 401 ? 'confirmed_logout' : 'auth_unknown');
          status(error.message, true);
        }
        throw error;
      }
      if (payload.schema_version !== schema || payload.contract_revision !== revision || !payload.data) {
        throw new Error('读取到不支持的数据版本，请保留当前内容并稍后重试。');
      }
      return payload.data;
    } finally { clearTimeout(timer); }
  }
  function render(data, methodToken) {
    observationReset();
    planReset();
    methodDirty = false;
    invalidateKB();
    summaryEdited = true;
    sourceRecordGeneration++;
    current = data;
    researchId = data.research.id;
    const problem = data.current_problem;
    // Only a full, explicit problem load/save establishes the editing base.
    // Task responses may observe newer server state but never rebase this form.
    editBase = {revision:problem.revision, digest:problem.digest, researchVersion:data.research_version,
      historical:Boolean(data.is_historical || selectedTask)};
    sourcePreview = null;
    sourceApproval = null;
    sourcePreviewGeneration++;
    byId('source-confirm').hidden = true;
    byId('source-plan').textContent = '';
    for (const [id, key] of [['entry','entry'],['original-input','original_input'],['objective','objective'],['summary','summary']]) {
      byId(id).value = problem[key];
    }
    byId('constraints').value = problem.constraints.join('\n');
    byId('unknowns').value = problem.unknowns.join('\n');
    byId('confirmed').checked = problem.confirmed;
    echoDraft();
    variables = problem.variables;
    byId('problem-meta').hidden = !recordTime(problem.created_at);
    showTime(byId('problem-created'),problem.created_at);
    byId('variables').hidden = variables.length === 0;
    const roles = {state:'状态',parameter:'参数',input:'输入',constraint:'约束',output:'输出'};
    const origins = {user_observed:'用户观察',user_assumed:'用户假设',system_proposed:'系统提议'};
    byId('variables').textContent = variables.map(v => `${v.label} (${v.id}) · 角色：${roles[v.role]} · 单位：${v.unit_id || '待确认'} · 观测：${v.observation ?? '待补充'} · 来源：${origins[v.provenance]}`).join('\n');
    byId('revision-label').textContent = readOnlyView() ? `原问题修订 ${problem.revision}（只读）` : `当前修订 ${problem.revision}`;
    byId('save').textContent = '保存为新修订';
    byId('reload').hidden = false;
    byId('access').hidden = true;
    byId('history-items').replaceChildren();
    for (const item of [...data.revisions].reverse()) {
      const detail = document.createElement('details');
      const title = document.createElement('summary');
      title.textContent = `修订 ${item.revision} · ${item.summary}`;
      const content = document.createElement('pre');
      content.textContent = `原始问题\n${item.original_input}\n\n目标\n${item.objective}\n\n摘要\n${item.summary}\n\n约束\n${item.constraints.join('\n') || '未填写'}\n\n未知\n${item.unknowns.join('\n') || '未填写'}`;
      detail.append(title, content);
      byId('history-items').append(detail);
    }
    form.hidden = false;
    byId('history').hidden = false;
    renderTask(data,{methodToken});
    formulaHydrate(data);
    setBusy(busy);
    // A fixed record must show the entire original text, including long inputs.
    for (const field of form.querySelectorAll('textarea')) {
      field.style.height = '';
      if (readOnlyView()) field.style.height = `${field.scrollHeight + 2}px`;
    }
  }
  function observeServer(data) {
    if (!observed || data.research_version >= observed.researchVersion) {
      const latest = data.revisions.find(item => item.revision === data.research.current_revision);
      observed = {researchVersion:data.research_version, revision:data.research.current_revision, digest:latest?.digest};
    }
  }
  function editNotice() {
    const conflict = editBase && observed && !editBase.historical &&
      (observed.revision !== editBase.revision || observed.digest !== editBase.digest);
    if (conflict) {
      status(`服务端已有修订 ${observed.revision}；表单仍基于修订 ${editBase.revision}，草稿已保留。保存与启动仍检查原基准；采用最新内容须明确载入。`, true);
      byId('reload').textContent = '明确载入最新修订（替换表单）';
    } else {
      byId('reload').textContent = '重新读取已存版本';
    }
    return Boolean(conflict);
  }
  function syncTaskButtons() {
    const actions = taskData?.allowed_next_actions || [];
    const map = {start:'start', cancel:'cancel', reconcile:'request_reconciliation', resume:'resume'};
    for (const [operation, action] of Object.entries(map)) {
      const button = byId('task-' + operation);
      button.hidden = readOnlyView() || Boolean(taskData?.is_historical) || !actions.includes(action) || (['native-plan-v1','funded-plan-v1'].includes(taskData?.task?.policy_revision)&&operation!=='cancel');
      button.disabled = taskBusy || (operation === 'start' && busy);
    }
    byId('task-refresh').disabled = taskBusy;
    byId('task-refresh').textContent=['native-plan-v1','funded-plan-v1'].includes(taskData?.task?.policy_revision)?'刷新计划流程状态':'刷新演练状态';
    syncSourceAccess();
  }
  function renderTask(data, context = {}) {
    if (data.research?.id !== researchId || (selectedTask !== null && selectedTask !== data.task?.id)) return false;
    const olderResearch = observed && data.research_version < observed.researchVersion;
    const sameTask = taskData?.task?.id === data.task?.id;
    observeServer(data);
    editNotice();
    if (olderResearch && (!sameTask || (!selectedTask && data.current_problem.revision !== observed.revision))) return false;
    if (sameTask && taskData?.task_version > data.task_version) return false;
    // A response to task1 cannot replace the task2 already shown by a newer
    // real view, even when both tasks use the same problem revision.
    if (context.targetTask && !selectedTask && taskData?.task?.id !== context.targetTask) return false;
    if (context.operation === 'start' && taskData?.task && !sameTask && data.research_version <= taskData.research_version) return false;
    const recordScope = `${data.research.id}:${data.current_problem.revision}:${data.task?.id || 'none'}`;
    if (sourceRecordScope !== recordScope) {
      sourceRecordScope = recordScope;
      sourceRecordGeneration++;
      byId('source-records').replaceChildren();
      byId('source-status').textContent = '';
    }
    taskData = data;
    formulaObserve(data);
    draftObserve(data);
    evidenceUI?.observe();
    financialObserve();
    registryUI?.observe();
    scenarioUI?.observe();
    planObserve(data,context.nativePlanRead!==false);
    byId('view-context').hidden = !readOnlyView();
    byId('view-context').textContent = data.is_historical ? '历史流程，只读查看原问题与原记录；不代表当前修订的研究结果。' : selectedTask ? '固定任务只读查看。这是当前任务，不是历史结果；返回当前问题后才能编辑。' : '';
    if (selectedTask) status(data.is_historical ? '已读取历史流程的原问题，只读查看；方法正文以下方状态为准。' : '已读取固定任务，只读查看；该任务仍是当前任务。');
    renderTaskHistory(data);
    syncSourceAccess();
    byId('task-title').textContent = '本机流程演练';
    byId('task-scope').textContent = '仅验证保存、调用与对账流程，不访问真实供应端、不扣真实费用，也不代表研究成果。';
    byId('task-section').hidden = !data.capabilities?.execution && !data.task && !data.other_active_task_id;
    const labels = {QUEUED:'等待本机执行', RUNNING:'本机演练处理中', WAITING_EXTERNAL:'等待演练响应', RECONCILING:'调用结果待核对', COMPLETED:'本机演练结束；尚无真实研究结论', FAILED:'演练未完成', CANCELLED:'已停止后续步骤', ACCESS_REVOKED:'访问已停止'};
    byId('task-phase').textContent = data.task ? labels[data.execution] : '尚未启动演练。启动后进入队列，仅在本机实际执行时推进，可刷新查看状态。';
    byId('task-budget').textContent = data.budget ? `已确认 ${data.budget.known_text}；预留 ${data.budget.held_text}；未确认调用 ${data.budget.unknown_count} 笔。` : '';
    const details = {reconciliation_required:'调用与费用仍待确认，预留保持占用；核对前不会重复调用。', waiting_external:'请求可能仍在处理中；停止只阻断后续步骤，不承诺撤回已经发出的请求。', budget_unverified:'演练额度或费率尚未核实，未发起新的调用。', budget_exhausted:'演练可用额度不足，未发起新的调用。', partial_results:'只保存本机合成笔记，不能当作真实取证或研究成果。'};
    byId('task-message').textContent = data.budget?.anomaly ? '演练费用出现异常，已停止新增调用，需要核对。' : (details[data.detail] || '');
    if (data.detail === 'reconciliation_required' && data.budget?.unknown_count === 0 && !data.budget?.anomaly) byId('task-message').textContent = '费用已确认，输出仍待核对；核对不会重复发送原调用。';
    byId('task-saved-scope').textContent = data.task
      ? `此流程绑定已保存的修订 ${data.task.input_revision}；本页表单基于修订 ${editBase?.revision}，未保存输入不进入演练。`
      : `本页表单基于已载入的修订 ${editBase?.revision}；任务刷新不会载入或覆盖问题。`;
    byId('task-other').hidden = !data.other_active_task_id;
    if (data.other_active_task_id) byId('task-other').href = `/research/${data.research.id}?task_id=${encodeURIComponent(data.other_active_task_id)}`;
    byId('task-current').hidden = !selectedTask && !data.is_historical;
    byId('task-current').href = `/research/${data.research.id}`;
    byId('task-notes').replaceChildren();
    for (const note of data.notes || []) {
      const element = document.createElement('pre'); element.textContent = note; byId('task-notes').append(element);
    }
    for (const observation of data.source_observations || []) {
      const element = document.createElement('p');
      element.textContent = `原读取 ${observation.started_at}；${observation.execution_closed ? '执行已闭合，结果仍未知' : '执行尚未闭合，结果待核对'}。未恢复旧结果。`;
      byId('task-notes').append(element);
    }
    if (data.source_quota) {
      byId('task-title').textContent = '来源读取流程';
      byId('task-scope').textContent = data.execution_mode === 'offline_probe' ? '当前使用本机合成来源验证流程；未访问公网，不构成真实研究证据。' : '按已确认的关键词读取固定学术来源；仅整理方法笔记，研究结论仍需验证。';
      byId('task-phase').textContent = data.execution === 'COMPLETED' ? '来源整理结束；研究证据仍不足。' : data.execution === 'FAILED' ? '来源读取未完成。' : data.execution === 'CANCELLED' ? '已停止后续来源读取。' : '来源流程状态：' + data.execution;
      byId('task-budget').textContent = `同一观测链已读取 ${data.source_quota.used} / ${data.source_quota.limit} 次；结果未知 ${data.source_quota.unknown_count} 次，其中执行已闭合 ${data.source_quota.unknown_closed} 次，尚未闭合 ${data.source_quota.unknown_unclosed} 次。`;
      byId('task-message').textContent = '尚未运行模型分析、行情计算或统计检验；短摘录不代表已验证结论。';
      if (data.source_quota.unknown_closed) byId('task-message').textContent += ' 旧读取执行已闭合，但原结果仍未知；后续读取是新观测，未恢复旧结果。';
    }
    if(data.task?.policy_revision==='local-formula-v1') {
      byId('task-title').textContent='本地公式检查任务';byId('task-scope').textContent='任务状态只说明检查流程，不等于数学通过。执行证明与四项结论在公式验证记录中分别展示。';
      byId('task-budget').textContent='此流程不调用模型；不把本地成本字段当供应商账单。';
    }
    if(['native-plan-v1','funded-plan-v1'].includes(data.task?.policy_revision)){
      byId('task-title').textContent='研究计划流程';byId('task-scope').textContent='计划执行与费用分别核对；生成计划不代表文献、数学关系或现实机制已验证。';
      byId('task-phase').textContent=planStates[planState.meta?.state]||'计划状态待核对';byId('task-budget').textContent='本流程不提供已核实的实扣费用或可用余额。';
      byId('task-saved-scope').textContent=`本次计划绑定已保存修订 ${data.task.input_revision}；本页表单仍基于修订 ${editBase?.revision}，未保存草稿不会混入原外发范围。`;
      byId('task-message').textContent='计划正文、执行来源和待核验边界请在上方计划记录中分别核对。';
    }
    syncTaskButtons();
    renderMethod(data,context.methodToken);
    return true;
  }
  function clearTaskHistory(message = '') {
    byId('task-history-section').hidden = !historySeen;
    byId('task-history-items').replaceChildren();
    byId('task-history-more').hidden = true; byId('task-history-more').removeAttribute('href');
    byId('task-history-refresh').hidden = true; byId('task-history-refresh').removeAttribute('href');
    byId('task-history-status').textContent = message;
  }
  function validTaskHistory(data) {
    const fields = ['task_id','input_revision','input_digest','start_version','execution','is_historical','received_at','result_status'];
    if (data.research?.id !== researchId || !Number.isSafeInteger(data.research.current_revision) || data.research.current_revision < 1 || data.research.current_revision > 2147483647 ||
        !Number.isSafeInteger(data.research_version) || data.research_version < 1 || data.research_version > 2147483647 || data.research.version !== data.research_version ||
        typeof data.is_historical !== 'boolean' || !Array.isArray(data.task_history) || data.task_history.length > 20 ||
        (selectedTask !== null && (data.task?.id !== selectedTask || data.task_history[0]?.task_id !== selectedTask))) return null;
    const seen = new Set(); let version = Infinity; let prior = null;
    for (const item of data.task_history) {
      if (!item || Object.keys(item).sort().join('|') !== fields.slice().sort().join('|') || !validId(item.task_id) ||
          seen.has(item.task_id) || !Number.isSafeInteger(item.input_revision) || item.input_revision < 1 || item.input_revision > data.research.current_revision ||
          !/^[a-f0-9]{64}$/.test(item.input_digest) || !Number.isSafeInteger(item.start_version) || item.start_version < 1 ||
          item.start_version > data.research_version || item.start_version > version || (item.start_version === version && item.task_id >= prior) ||
          !['QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING','COMPLETED','FAILED','CANCELLED','ACCESS_REVOKED'].includes(item.execution) ||
          typeof item.is_historical !== 'boolean' || !['stored','unavailable','none'].includes(item.result_status) ||
          (item.received_at !== null && !recordTime(item.received_at))) return null;
      seen.add(item.task_id); version = item.start_version; prior = item.task_id;
    }
    if (data.next_task_id !== null && (!validId(data.next_task_id) || seen.has(data.next_task_id) || data.task_history.length !== 20)) return null;
    return data.task_history;
  }
  function renderTaskHistory(data) {
    if (!Object.hasOwn(data,'task_history')) {
      clearTaskHistory('流程记录列表尚待重新读取；不会沿用操作前的旧列表。');
      if (historySeen) { byId('task-history-refresh').hidden = false; byId('task-history-refresh').href = `/research/${researchId}`; }
      return;
    }
    historySeen = true; clearTaskHistory();
    const items = validTaskHistory(data);
    if (!items) { byId('task-history-status').textContent = '流程记录列表暂时无法核对，请重新读取。'; return; }
    byId('task-history-status').textContent = items.length ? `本页 ${items.length} 条流程；选择后只读查看对应原问题。` : '尚无已保存的流程记录。';
    const results = {stored:'已保存记录，正文需读取时核对',unavailable:'原正文已不可用',none:'尚无已保存方法正文'};
    const states = {QUEUED:'等待执行',RUNNING:'处理中',WAITING_EXTERNAL:'等待响应',RECONCILING:'待核对',COMPLETED:'已结束',FAILED:'未完成',CANCELLED:'已停止',ACCESS_REVOKED:'访问已停止'};
    for (const item of items) {
      const row = document.createElement('li'); const link = document.createElement('a');
      link.href = `/research/${researchId}?task_id=${encodeURIComponent(item.task_id)}`; link.target = '_blank'; link.rel = 'noopener';
      link.textContent = `修订 ${item.input_revision} · ${item.is_historical ? '历史流程' : '当前流程'} · ${states[item.execution]}（新标签页，只读）`;
      if (item.task_id === selectedTask) link.setAttribute('aria-current','page');
      const note = document.createElement('p'); note.className = 'hint'; note.textContent = results[item.result_status];
      if (item.received_at !== null) { const time = document.createElement('time'); showTime(time,item.received_at); note.append(' · 原记录时间 ',time); }
      row.append(link,note); byId('task-history-items').append(row);
    }
    if (data.next_task_id !== null) { byId('task-history-more').href = `/research/${researchId}?task_id=${encodeURIComponent(data.next_task_id)}`; byId('task-history-more').hidden = false; }
  }
  function viewUrl() { return `/api/research/${researchId}` + (selectedTask ? `?task_id=${encodeURIComponent(selectedTask)}` : ''); }
  function invalidateKB() {
    kbGeneration++;
    kbBusy = false;
    byId('kb-results').replaceChildren();
    byId('kb-status').textContent = '填写现象后可查询；不会自动开始研究。';
    byId('kb-search').disabled = busy || Boolean(editBase?.historical);
  }
  function echoDraft() {
    const length = Array.from(byId('original-input').value).length;
    if (!summaryEdited && !editBase) byId('summary').value = length <= 1000 ? byId('original-input').value : '';
    byId('summary-hint').textContent = length > 1000
      ? '原文已完整保留。当前人工工作台仅接受 8–1000 字摘要；自动整理尚未开放，不会截断、填充或代你确认。'
      : '人工维护区：这里只回显原话，不是系统结构化草案；不会自动确认。';
  }
  function showAdvanced(open) {
    document.body.classList.toggle('advanced-closed', !open);
    byId('problem-advanced').hidden = !open;
    byId('advanced-tools').hidden = !open;
    byId('advanced-tools-toggle').setAttribute('aria-expanded', String(open));
    if (open && readOnlyView()) {
      for (const field of form.querySelectorAll('textarea')) {
        field.style.height = '';
        field.style.height = `${field.scrollHeight + 2}px`;
      }
    }
  }
  byId('advanced-tools-toggle').addEventListener('click', () => {
    showAdvanced(byId('problem-advanced').hidden);
  });
  function observationProblem(raw, declared) {
    if (declared !== true) throw Error('请先作出本人现象自述与权属声明。');
    const length = Array.from(raw).length;
    if (length < 8 || length > 1000 || Array.from(raw.normalize('NFC')).length < 8)
      throw Error('当前规划仅支持 8–1000 字的本人现象自述。原话已完整保留；不会截断、补字或要求你重抄摘要。');
    const view = raw.normalize('NFKC');
    // Same finite refusal classes as phenomenon_plan._STRUCTURES; this is not ownership verification.
    const structures = new RegExp("(?:\\b[a-z][a-z0-9+.-]{1,24}://|\\b(?:https?|file|data|javascript|mailto):|\\bwww\\.|\\bdoi\\s*:|\\b10\\.\\d{4,9}/\\S+)|(?:`|\\$\\(|\\$\\{|#!\\s*/|<\\s*/?\\s*(?:script|iframe|object|embed)\\b)|(?:\\b(?:curl|wget|rm|chmod|chown|ssh|scp)\\s+-[A-Za-z]|\\b(?:bash|sh|zsh|pwsh|powershell)\\s+-[A-Za-z])|(?:\\b(?:python3?|node)\\s+-(?:c|e)\\b|\\b(?:pip3?|npm|npx)\\s+(?:install|exec|run)\\b)|(?:\\b(?:eval|exec|__import__)\\s*\\(|\\b(?:Invoke-WebRequest|Invoke-Expression|Start-Process)\\b)|(?:\\bSELECT\\s+\\*\\s+FROM\\b|\\b(?:DROP|ALTER|CREATE)\\s+TABLE\\b|\\bINSERT\\s+INTO\\b|\\bDELETE\\s+FROM\\b)|(?:\\[[0-9]+\\]|\\bet\\s+al\\.)|(?:[\\\"']?(?:verified|checked|trusted|copyright_verified|mathematically_verified)[\\\"']?\\s*[:=]\\s*(?:true|1|yes)\\b)", 'i');
    if (!planText(raw,1000,8) || structures.test(view))
      throw Error('这段内容含链接、代码或不适用结构，不能声明为本入口的本人现象自述。原文保留，可在高级工具中按资料用途处理。');
    return {entry:'phenomenon',original_input:raw,objective:'',summary:raw.normalize('NFC'),
      variables:[],constraints:[],unknowns:[],confirmed:true};
  }
  function observationReset() {
    observationReview = null;
    byId('observation-card').hidden = true;
    byId('observation-exact').textContent = '';
    byId('observation-own').checked = false;
    observationSync();
  }
  function observationSync() {
    const locked = busy || readOnlyView() || form.hidden;
    byId('start-research').disabled = locked || !byId('original-input').value.trim();
    byId('observation-own').disabled = locked;
    let eligible = false;
    try { if(observationReview === byId('original-input').value) { observationProblem(observationReview,true); eligible=true; } } catch {}
    byId('observation-adopt').disabled = locked || !eligible || !byId('observation-own').checked;
  }
  byId('start-research').addEventListener('click', () => {
    if (busy || readOnlyView() || !byId('original-input').reportValidity()) return;
    byId('native-plan-own').checked = false;
    planInvalidate('正在核对原话；本次尚未预览或外发。');
    observationReview = byId('original-input').value;
    byId('observation-exact').textContent = observationReview;
    byId('observation-card').hidden = false;
    byId('observation-own').checked = false;
    byId('observation-save-status').textContent = '采用后保存问题；不会自动外发或扣费。记录标题会按已有规则规范化文字，逐字原话始终以上面的原文为准。';
    try { observationProblem(observationReview,true); byId('observation-scope').textContent = '请核对完整原话与下方声明。采用后先保存，再单独核对研究计划的外发范围与费用；未填写的目标、变量和未知项保持为空。'; }
    catch(error) { byId('observation-scope').textContent = error.message; }
    observationSync();
  });
  byId('observation-own').addEventListener('change',observationSync);
  byId('observation-adopt').addEventListener('click', async () => {
    if(busy || readOnlyView()) return;
    try {
      if(observationReview !== byId('original-input').value) throw Error('原话已变化，请先重新核对原话卡。');
      const problem = observationProblem(observationReview,byId('observation-own').checked);
      const same = current?.current_problem?.original_input === problem.original_input;
      if(same && current.current_problem.confirmed === true) {
        if(current.current_problem.entry !== 'phenomenon' || methodDirty || formulaState.dirty || editNotice() || sessionStorage.getItem('structure-research-pending:'+researchId))
          throw Error('当前记录有其他用途、改动或待核对保存操作，请保留原文并先核对已存版本。');
        // Reuse the saved revision: never mint a new revision to bypass known Source provenance.
        byId('native-plan-own').checked = true;
        byId('observation-save-status').textContent = '已采用当前已保存修订的本人自述声明。没有另存修订或外发；下一步请预览原文与费用，来源限制仍由服务端核对。';
        planSync();
        return;
      }
      if(same && current?.task?.policy_revision === 'd1-source-only-v1') throw Error('当前修订已有来源流程，不能重新标为本人现象自述。原文与来源记录保留。');
      await saveProblem(problem);
    } catch(error) { byId('observation-save-status').textContent = error.message; }
  });
  async function authenticated(isCurrent, signal) {
    const unavailable = () => {
      const planWasCurrent=isCurrent();
      if (isCurrent()) { invalidateMethod('账户状态暂时无法核对，已收起旧方法记录；草稿仍保留。'); formulaAuthUncertain(); clearTaskHistory('账户状态暂时无法核对，流程列表已收起；请稍后主动读取。'); }
      if (isCurrent()) status('账户状态暂时无法核对；草稿与待核对操作已保留，本次后续请求已停止。请稍后主动重试。', true);
      if(planWasCurrent){scenarioUI?.invalidate('auth_unknown','账户状态待核对，私有计算结果已收起；原操作保留。');registryUI?.invalidate('auth_unknown','账户状态尚待核对，已隐藏私有材料；原操作保留。');evidenceUI?.invalidate('账户状态尚待核对，已隐藏方法综合与引用正文；原确认操作保留。',true);financialInvalidate('账户状态尚待核对，旧财务预览已收起；CSV 仍暂存在本页。');planInvalidate('账户状态尚待核对，计划正文已收起；草稿与原操作保留。');byId('native-plan-history').replaceChildren();draftHideMaterials('账户状态尚待核对，已隐藏引用原文；手写内容与原操作保留。');}
      return false;
    };
    try {
      const response = await fetch('/api/auth/me', {cache:'no-store', credentials:'same-origin', signal});
      if (!isCurrent()) return false;
      // /auth/me confirms missing, invalid or revoked sessions with 401.
      // Other HTTP failures alone say nothing about the account's authority.
      if (response.status === 401) {
        clearPrivateView('confirmed_logout'); status('账户访问已失效，请重新登录。', true); return false;
      }
      if (!response.ok && response.status !== 409) return unavailable();
      const payload = await response.json();
      if (!isCurrent()) return false;
      if (response.status === 409 && payload?.ok === false && payload.error === 'credential_conflict') {
        clearPrivateView('credential_conflict'); status('账户凭据存在冲突，请重新确认账户。', true); return false;
      }
      if (!response.ok || payload?.ok !== true || typeof payload.user?.email !== 'string' || !payload.user.email.trim() ||
          typeof payload.user.created_at !== 'string' || !payload.user.created_at.trim()) return unavailable();
      const identity = JSON.stringify([payload.user.email, payload.user.created_at]);
      if (accountScope && accountScope !== identity) {
        clearPrivateView('actor_changed'); status('账户已变化，请重新打开研究页面。', true); return false;
      }
      accountScope = identity;
      if (registryUI && !await registryUI.activateVerifiedAccount(identity, isCurrent)) return false;
      if (scenarioUI && !await scenarioUI.activateVerifiedAccount(identity, isCurrent)) return false;
      return isCurrent();
    } catch (error) {
      return unavailable();
    }
  }
  function positionInitialSection() {
    if (entryPositioned || !initialSection || form.hidden) return;
    const section = byId(initialSection);
    if (!section || section.hidden) return;
    entryPositioned = true;
    if (initialSection === 'kb-section') showAdvanced(true);
    section.scrollIntoView({block:'start'});
  }
  async function loadResearchList(more = false, positionEntry = false) {
    if (more && (listBusy || !listCursor)) return;
    const generation = ++listGeneration;
    const privateScope = privateGeneration;
    const active = () => generation === listGeneration && privateScope === privateGeneration;
    const cursor = more ? listCursor : null;
    listBusy = true;
    byId('research-list-refresh').disabled = false;
    byId('research-list-more').disabled = true;
    if (!more) {
      listCursor = null;
      listSeen = new Set();
      byId('research-list-items').replaceChildren();
      byId('research-list-more').hidden = true;
    }
    byId('research-list-status').textContent = '正在读取当前账户的研究…';
    try {
      if (!await authenticated(active)) {
        if (active()) byId('research-list-status').textContent = '账户状态尚待核对，列表已停止更新；草稿保持不变。';
        return;
      }
      const data = await request('/api/research?limit=20' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), {}, active);
      if (!active()) return;
      if (!await authenticated(active)) {
        if (active()) byId('research-list-status').textContent = '账户状态尚待核对，列表已停止更新；草稿保持不变。';
        return;
      }
      if (!Array.isArray(data.items) || !(data.next_cursor === null || typeof data.next_cursor === 'string')) throw new Error('列表格式暂时无法核对，请刷新列表。');
      byId('my-research').hidden = false;
      for (const item of data.items) {
        if (!validId(item.research_id) || listSeen.has(item.research_id)) continue;
        listSeen.add(item.research_id);
        const article = document.createElement('article');
        const title = document.createElement('h3');
        const link = document.createElement('a');
        link.href = '/research/' + item.research_id;
        link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.textContent = item.title;
        title.append(link);
        const meta = document.createElement('p'); meta.className = 'hint';
        const states = {QUEUED:'等待执行', RUNNING:'处理中', WAITING_EXTERNAL:'等待响应', RECONCILING:'结果待核对', COMPLETED:'流程已结束，结论待验证', FAILED:'流程未完成', CANCELLED:'已停止', ACCESS_REVOKED:'访问已停止'};
        meta.textContent = `修订 ${item.current_input_revision} · ${item.current_task ? (states[item.current_task.execution] || '状态待核对') : '已保存，尚未执行'} · 在新标签页打开`;
        article.append(title, meta); byId('research-list-items').append(article);
      }
      listCursor = data.next_cursor;
      byId('research-list-more').hidden = !listCursor;
      byId('research-list-status').textContent = listSeen.size ? `已读取 ${listSeen.size} 条研究${listCursor ? '，可加载更多。' : '。'}` : '还没有保存的研究。从上方的现象开始即可。';
      if (positionEntry && initialSection === 'my-research') positionInitialSection();
    } catch (error) {
      if (!active()) return;
      if (cursor && (error.status === 409 || error.status === 422)) {
        listCursor = null; listSeen.clear();
        byId('research-list-items').replaceChildren();
        byId('research-list-more').hidden = true;
        byId('research-list-status').textContent = '列表已变化，分页位置失效。请刷新列表；当前问题草稿保持不变。';
      } else byId('research-list-status').textContent = '列表暂时无法读取，请刷新列表；当前问题草稿保持不变。';
    } finally {
      if (active()) { listBusy = false; byId('research-list-more').disabled = false; }
    }
  }
  byId('research-list-refresh').addEventListener('click', () => loadResearchList());
  byId('research-list-more').addEventListener('click', () => loadResearchList(true));
  for (const id of ['original-input','objective','entry','summary','constraints','unknowns','confirmed']) {
    byId(id).addEventListener('input', () => {
      methodDirty = true; invalidateMethod('表单有未保存改动，已收起旧方法记录。');
      evidenceUI?.invalidate('问题有未保存改动，请保存并核对后重新选材预览。',true);
      formulaProblemEdited();
      planInvalidate('本页草稿有修改，旧计划已收起；请保存后重新预览。');
      draftChanged('问题有未保存改动；此处方法文字保留，保存前先核对问题。');
      financialInvalidate('问题有未保存改动，旧预览已失效；CSV 仍暂存在本页。');
      if (id === 'summary') summaryEdited = true;
      if (id === 'original-input') { observationReset(); echoDraft(); }
      observationSync();
      invalidateKB();
    });
  }
  byId('kb-search').addEventListener('click', async () => {
    if (kbBusy || busy || form.hidden || editBase?.historical) return;
    const query = byId('original-input').value.trim();
    invalidateKB();
    if (!query) { byId('kb-status').textContent = '请先填写观察到的现象。'; return; }
    const generation = kbGeneration;
    const privateScope = privateGeneration;
    const scope = researchId;
    const active = () => generation === kbGeneration && privateScope === privateGeneration && scope === researchId;
    kbBusy = true; byId('kb-search').disabled = true;
    byId('kb-status').textContent = '正在查找本地知识库线索…';
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      if (!await authenticated(active, controller.signal)) {
        if (active()) byId('kb-status').textContent = '账户状态尚待核对，未更新线索；请稍后主动重试。';
        return;
      }
      const response = await fetch('/api/search', {method:'POST', credentials:'same-origin', cache:'no-store', signal:controller.signal,
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({query, top_k:12, rewrite:false, lang:'zh'})});
      if (!active()) return;
      const data = await response.json();
      if (!active()) return;
      if (response.status === 401 || response.status === 404 || data.error?.code === 'AUTHORIZATION_STALE') { clearPrivateView(response.status === 401 ? 'confirmed_logout' : 'auth_unknown'); status('账户访问已失效，请重新登录。', true); return; }
      if (!response.ok) throw new Error(response.status === 503 ? '知识库当前不可用；当前问题仍可保存。未启动模型或收费研究。' : '知识库查询未完成；当前输入已保留。');
      if (!Array.isArray(data.results)) throw new Error('知识库返回格式暂时无法核对。');
      if (!await authenticated(active, controller.signal)) {
        if (active()) byId('kb-status').textContent = '账户状态尚待核对，未更新线索；请稍后主动重试。';
        return;
      }
      for (const item of data.results) {
        const article = document.createElement('article');
        const title = document.createElement('h3'); title.textContent = item.name;
        const meta = document.createElement('p'); meta.className = 'hint'; meta.textContent = `${item.domain || '领域未标注'} · 待核验的知识库线索 · 本次本地排序`;
        const description = document.createElement('p'); description.textContent = item.description;
        article.append(title, meta, description); byId('kb-results').append(article);
      }
      byId('kb-status').textContent = data.results.length ? `找到 ${data.results.length} 条待核验线索。尚未检验变量、机制与适用条件；未写入研究或读取外部来源。` : '未找到本地线索。可以调整现象描述，或先保存问题；尚未查询外部文献。';
    } catch (error) {
      if (active()) byId('kb-status').textContent = error.name === 'AbortError' || error.name === 'TypeError' ? '知识库查询未完成，当前输入已保留；可主动重试。' : error.message;
    } finally {
      clearTimeout(timer);
      if (active()) { kbBusy = false; byId('kb-search').disabled = busy; }
    }
  });
  async function load() {
    const methodToken = beginMethodRead();
    const positionEntry = initialLoad;
    initialLoad = false;
    const privateScope = privateGeneration;
    if (!await authenticated(() => privateScope === privateGeneration)) return;
    if (selectedTask !== null && (!researchId || !validId(selectedTask) || new URLSearchParams(location.search).getAll('task_id').length !== 1)) { clearPrivateView(); status('流程链接无效。', true); return; }
    if (!researchId) {
      // An authenticated read is still required: the account endpoint performs
      // actual session validation; the research API revalidates on every save.
      form.hidden = false;
      observationSync();
      planSync();
      draftSync();
      byId('native-plan-status').textContent='问题尚未保存；没有生成或外发计划。';
      status('新问题尚未保存。');
      byId('my-research').hidden = false;
      loadResearchList(false, positionEntry);
      if (positionEntry && initialSection === 'kb-section') positionInitialSection();
      return;
    }
    if (!validId(researchId)) { clearPrivateView(); status('研究链接无效。', true); return; }
    const data = await methodRequest(viewUrl(),{},methodToken);
    if (methodToken.generation !== methodGeneration) return;
    if (selectedTask && data.task?.id !== selectedTask) { clearPrivateView(); status('无法核对所选流程，请重新打开研究记录。',true); return; }
    render(data,methodToken);
    byId('my-research').hidden = false;
    loadResearchList(false, positionEntry);
    if (positionEntry && initialSection === 'kb-section') positionInitialSection();
    await recoverSourceIntent();
    if (data.method_result_state !== 'unavailable' && !editNotice()) status(data.is_historical ? '已读取历史流程的原问题，只读查看；方法正文以下方状态为准。' : selectedTask ? '已读取固定任务，只读查看；该任务仍是当前任务。' : '已从账户读取保存的问题；尚未执行研究。');
  }
  async function operationKey(scope, body, expectedRevision, taskRequest = null) {
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body));
    const hash = Array.from(new Uint8Array(bytes), n => n.toString(16).padStart(2,'0')).join('');
    const slot = 'structure-research-pending:' + scope;
    const existing = sessionStorage.getItem(slot);
    if (existing) {
      const pending = JSON.parse(existing);
      if (pending.digest !== hash) throw new Error('上次保存的结果尚未确认。请先用上次相同内容再次保存，或重新读取已存版本。');
      return {key:pending.key, slot};
    }
    const key = crypto.randomUUID();
    sessionStorage.setItem(slot, JSON.stringify({key, digest:hash, expected_revision:expectedRevision, task_request:taskRequest}));
    return {key, slot};
  }
  function lines(id) {
    const values = byId(id).value.split('\n').filter(line => line.length > 0);
    if (values.length > 12 || values.some(line => Array.from(line).length > 120)) {
      throw new Error('约束与未知各最多 12 项，每项最多 120 字。');
    }
    return values;
  }
  function sourceWritesAllowed(){return !readOnlyView()&&Boolean(taskData?.capabilities?.source_evidence);}
  function syncSourceAccess(){
    const writable=sourceWritesAllowed(),stored=taskData?.task?.policy_revision==='d1-source-only-v1';
    byId('source-section').hidden=!taskData||form.hidden;
    byId('source-title').textContent=writable?'可选：继续查找方法来源':'已有来源笔记';
    for(const node of byId('source-section').querySelectorAll('.source-write-ui'))node.hidden=!writable;
    byId('source-query').disabled=!writable||sourceBusy||busy||taskBusy;
    byId('source-preview').hidden=!writable;byId('source-preview').disabled=!writable||sourceBusy||busy||taskBusy;
    if(!writable){sourcePreview=null;sourceApproval=null;byId('source-plan').textContent='';}
    byId('source-confirm').hidden=!writable||!sourcePreview;byId('source-confirm').disabled=!writable||sourceBusy||busy||taskBusy;
    byId('source-refresh').hidden=!stored;byId('source-refresh').disabled=!stored||sourceBusy||busy||taskBusy;
    byId('source-reopen-hint').textContent=writable?'已有来源需手动读取；预览和确认后才会尝试新采集。':stored?'可以读取已有来源；当前不能采集新资料。':'当前未选中已有来源，且暂不能采集新资料。可从已有资料目录或历史记录选择来源。';
  }
  async function sourcePost(operation, data, isCurrent = () => true) {
    if (!sourceWritesAllowed()) throw new Error('当前不能采集新资料；已有来源仍可按权限读取。');
    const privateScope = privateGeneration;
    const body = JSON.stringify({schema_version:schema, contract_revision:revision, data});
    if (operation === 'source-preview') return request(`/api/research/${researchId}/${operation}`, {method:'POST', headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()}, body}, isCurrent);
    const pending = await operationKey(`source:${operation}:${researchId}`, body, data.input_revision, data);
    if (privateScope !== privateGeneration) throw new Error('账户访问已变化，请重新打开研究页面。');
    try {
      const result = await request(`/api/research/${researchId}/${operation}`, {method:'POST', headers:{'Content-Type':'application/json','Idempotency-Key':pending.key}, body});
      sessionStorage.removeItem(pending.slot);
      return result;
    } catch (error) {
      if (error.status >= 400 && error.status < 500) sessionStorage.removeItem(pending.slot);
      throw error;
    }
  }
  async function recoverSourceIntent() {
    if (readOnlyView() || !researchId || !taskData?.capabilities?.source_evidence) return;
    const pendingStart = sessionStorage.getItem(`structure-research-pending:source:source-tasks:${researchId}`);
    const pendingApproval = sessionStorage.getItem(`structure-research-pending:source:source-approvals:${researchId}`);
    if (!pendingStart && !pendingApproval) return;
    const methodToken = beginMethodRead();
    sourceBusy = true;
    try {
      let data;
      if (pendingStart) data = JSON.parse(pendingStart).task_request;
      else {
        const original = JSON.parse(pendingApproval).task_request;
        const approved = await sourcePost('source-approvals',original);
        data = {input_revision:original.input_revision,expected_research_version:original.expected_research_version,approval_ref:approved.approval_ref};
      }
      const result = await sourcePost('source-tasks',data);
      renderTask(result,{operation:'start',methodToken});
      byId('source-status').textContent = '已核对上次确认的原操作；没有另启重复流程。';
    } catch (error) { methodFailure(methodToken); byId('source-status').textContent = error.message; }
    finally { sourceBusy = false; syncSourceAccess(); }
  }
  async function sourceRecords() {
    const task = taskData?.task;
    if (!task || task.policy_revision !== 'd1-source-only-v1') return;
    const taskId = task.id;
    const scope = sourceRecordScope;
    const generation = sourceRecordGeneration;
    const items = [];
    for (const kind of ['sources','excerpts','claims','reports']) {
      let cursor = null;
      do {
        let data;
        try { data = await request(`/api/research/${researchId}/records?task_id=${encodeURIComponent(taskId)}&kind=${kind}` + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), {}, () => sourceRecordGeneration === generation && sourceRecordScope === scope); }
        catch (error) { if (sourceRecordGeneration !== generation) return; throw error; }
        if (sourceRecordGeneration !== generation || sourceRecordScope !== scope || taskData?.task?.id !== taskId || taskData.task_version > data.task_version || observed?.researchVersion > data.research_version) return;
        items.push(...data.items.map(item => ({...item,recordKind:kind})));
        cursor = data.next_cursor;
      } while (cursor);
    }
    if (sourceRecordGeneration !== generation || sourceRecordScope !== scope || taskData?.task?.id !== taskId) return;
    byId('source-records').replaceChildren();
    for (const item of items) {
      const article = document.createElement('article');
      const title = document.createElement('h3');
      title.textContent = {sources:'来源',excerpts:'短摘录',claims:'待验证判断',reports:'研究缺口'}[item.recordKind];
      const content = document.createElement('p');
      content.textContent = item.title || item.quote || item.text || item.outstanding_requirements.join('；');
      article.append(title,content);
      if (item.recordKind === 'sources') {
        const link = document.createElement('a'); link.href = item.canonical_url; link.textContent = item.canonical_url; link.rel = 'noreferrer'; article.append(link);
        const provenance = document.createElement('p'); provenance.className = 'hint'; provenance.textContent = `${item.execution_mode} · ${item.accessed_at} · ${item.license_note}`; article.append(provenance);
      }
      byId('source-records').append(article);
    }
    byId('source-status').textContent = items.length ? '已从账户读取来源与笔记；证据仍不足。' : '当前尚无可展示的来源材料。';
  }
  byId('source-preview').addEventListener('click', async () => {
    if (sourceBusy || busy || taskBusy || !editBase || !sourceWritesAllowed()) return;
    sourceBusy = true;
    byId('source-preview').disabled = true;
    byId('source-status').textContent = '正在预览关键词；尚未开始读取来源。';
    sourcePreview = null;
    sourceApproval = null;
    byId('source-confirm').hidden = true;
    const generation = ++sourcePreviewGeneration;
    const privateScope = privateGeneration;
    const researchScope = researchId;
    const savedVersion = editBase.researchVersion;
    const active = () => generation === sourcePreviewGeneration && privateScope === privateGeneration && researchScope === researchId && savedVersion === editBase?.researchVersion;
    try {
      const data = {input_revision:editBase.revision,expected_research_version:editBase.researchVersion,query:byId('source-query').value};
      const result = await sourcePost('source-preview',data, active);
      if (!active()||!sourceWritesAllowed()) return;
      sourcePreview = {...data,preview_digest:result.preview_digest};
      byId('source-plan').textContent = `实际对外关键词：${result.query}\n绑定已保存修订 ${result.input_revision}（不含表单中的未保存修改）\n最多读取 ${result.plan.max_requests} 次 GET 来源；不会发送现象原文、目标或私有标签。`;
      byId('source-status').textContent = '预览完成；尚未开始读取来源。';
      byId('source-confirm').hidden = false;
    } catch (error) { if (active()) byId('source-status').textContent = error.message; }
    finally { sourceBusy = false; syncSourceAccess(); }
  });
  byId('source-query').addEventListener('input', () => { sourcePreviewGeneration++; sourcePreview = null; sourceApproval = null; byId('source-confirm').hidden = true; byId('source-plan').textContent = ''; byId('source-status').textContent = '关键词已变化，请重新预览；尚未开始读取来源。'; });
  byId('source-confirm').addEventListener('click', async () => {
    if (sourceBusy || busy || taskBusy || !sourcePreview || !sourceWritesAllowed()) return;
    sourceBusy = true;
    const methodToken = beginMethodRead();
    const approvedPreview = {...sourcePreview};
    try {
      const approved = sourceApproval || await sourcePost('source-approvals',{...approvedPreview,confirm_external:true});
      sourceApproval = approved;
      const result = await sourcePost('source-tasks',{input_revision:approvedPreview.input_revision,expected_research_version:approvedPreview.expected_research_version,approval_ref:approved.approval_ref});
      renderTask(result,{operation:'start',methodToken});
      sourceApproval = null;
      byId('source-confirm').hidden = true;
      byId('source-status').textContent = '来源流程已排队；刷新可读取实际执行状态。';
    } catch (error) { methodFailure(methodToken); byId('source-status').textContent = error.message; }
    finally { sourceBusy = false; syncSourceAccess(); }
  });
  byId('source-refresh').addEventListener('click', async () => {
    if (sourceBusy || busy || taskBusy || !researchId) return;
    sourceBusy = true;
    const methodToken = beginMethodRead();
    try { renderTask(await methodRequest(viewUrl(),{},methodToken),{methodToken}); await sourceRecords(); }
    catch (error) { byId('source-status').textContent = error.message; }
    finally { sourceBusy = false; syncSourceAccess(); }
  });
  function validateObservationReceipt(saved, problem, targetId, expectedRevision, minimumVersion) {
    const fail = () => { throw Error('采用回执无法完整核对；原保存操作保留，请保留输入并用相同内容核对原操作。'); };
    const integer = value => Number.isSafeInteger(value) && value >= 1 && value <= 2147483647;
    const row = saved?.research, value = saved?.current_problem;
    const wantedRevision = expectedRevision === null ? 1 : expectedRevision + 1;
    if (!planObject(saved) || !planObject(row) || !validId(row.id) || (targetId !== null && row.id !== targetId) ||
        row.current_revision !== wantedRevision || !integer(row.version) || row.version !== saved.research_version || row.version < minimumVersion ||
        !planObject(value) || value.research_id !== row.id || value.revision !== wantedRevision ||
        !formulaDigest(value.digest) || !recordTime(value.created_at) || value.entry !== 'phenomenon' ||
        value.original_input !== problem.original_input || value.summary !== problem.summary || value.objective !== '' || value.confirmed !== true ||
        !['variables','constraints','unknowns'].every(key => Array.isArray(value[key]) && value[key].length === 0) ||
        (value.formula_snapshot !== undefined && value.formula_snapshot !== null) ||
        !Array.isArray(saved.revisions) || saved.revisions.length !== wantedRevision || saved.is_historical !== false ||
        saved.task !== null || saved.task_version !== null || saved.execution !== null || row.current_task_id !== null ||
        !planObject(saved.capabilities) || !Array.isArray(saved.allowed_next_actions) || !saved.allowed_next_actions.every(item => typeof item === 'string') ||
        (saved.notes != null && (!Array.isArray(saved.notes) || !saved.notes.every(item => typeof item === 'string'))) ||
        (saved.source_observations !== undefined && (!Array.isArray(saved.source_observations) || saved.source_observations.length !== 0))) fail();
    for (let index = 0; index < saved.revisions.length; index++) {
      const item = saved.revisions[index];
      if (!planObject(item) || item.research_id !== row.id || item.revision !== index + 1 || !formulaDigest(item.digest) || !recordTime(item.created_at) ||
          !['phenomenon','formula','research'].includes(item.entry) || typeof item.original_input !== 'string' || typeof item.objective !== 'string' ||
          typeof item.summary !== 'string' || typeof item.confirmed !== 'boolean' || !Array.isArray(item.variables) ||
          !['constraints','unknowns'].every(key => Array.isArray(item[key]) && item[key].every(text => typeof text === 'string'))) fail();
    }
    const latest = saved.revisions[saved.revisions.length - 1];
    for (const key of ['research_id','revision','digest','created_at','entry','original_input','objective','summary','confirmed']) if (latest[key] !== value[key]) fail();
    if (!['variables','constraints','unknowns'].every(key => latest[key].length === 0)) fail();
  }
  async function saveProblem(adoptedProblem = null) {
    if (busy || readOnlyView()) return;
    const methodToken = beginMethodRead();
    setBusy(true);
    status('正在保存，请保留当前页面…');
    let pending;
    const privateScope = privateGeneration;
    try {
      const problem = adoptedProblem || normalizeProblem({entry:byId('entry').value, original_input:byId('original-input').value,
        objective:byId('objective').value, summary:byId('summary').value, variables,
        constraints:lines('constraints'), unknowns:lines('unknowns'), confirmed:byId('confirmed').checked,
        ...(byId('formula-enable').checked?{formula_draft:formulaTakeDraft()}: {})});
      const scope = researchId || 'new';
      const prior = sessionStorage.getItem('structure-research-pending:' + scope);
      const priorOperation = prior ? JSON.parse(prior) : null;
      // Reopening a committed revision must not silently change the body of an
      // unresolved operation. Retain its original CAS revision when confirming.
      const expectedRevision = current ? (priorOperation?.expected_revision ?? editBase.revision) : null;
      const data = current ? {expected_revision:expectedRevision, problem} : {problem};
      const body = JSON.stringify({schema_version:schema, contract_revision:revision, data});
      pending = await operationKey(scope, body, expectedRevision);
      if (privateScope !== privateGeneration) throw new Error('账户访问已变化，请重新登录后核对原操作。');
      const url = researchId ? `/api/research/${researchId}/revisions` : '/api/research';
      const saved = await methodRequest(url, {method:'POST', headers:{'Content-Type':'application/json', 'Idempotency-Key':pending.key}, body},methodToken);
      if (adoptedProblem) validateObservationReceipt(saved, adoptedProblem, researchId, expectedRevision, current ? editBase.researchVersion + 1 : 1);
      render(saved,methodToken);
      history.replaceState(null, '', `/research/${saved.research.id}`);
      sessionStorage.removeItem(pending.slot);
      if (adoptedProblem) {
        byId('native-plan-own').checked = true;
        byId('observation-save-status').textContent = '本人自述已采用并保存。尚未外发；下一步请预览原话与费用。';
        planSync();
        byId('native-plan-section').scrollIntoView({block:'start'});
      }
      loadResearchList();
      status(`已保存修订 ${saved.current_problem.revision}。这是一条问题记录，尚未执行研究。`);
    } catch (error) {
      // 4xx proves rejection; transport/5xx outcomes keep the original key.
      if (pending && error.status >= 400 && error.status < 500) sessionStorage.removeItem(pending.slot);
      const transportFailure = error.name === 'AbortError' || error.name === 'TypeError' || error.name === 'SyntaxError';
      status(transportFailure ? '保存结果尚未确认。请保留输入，用相同内容再次保存以核对原操作。' : error.message, true);
    } finally {
      setBusy(false);
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); void saveProblem(); });
  async function taskAction(operation) {
    if (readOnlyView() || taskData?.is_historical || taskBusy || !taskData || (operation === 'start' && busy)) return;
    taskBusy = true; syncTaskButtons();
    const methodToken = beginMethodRead();
    let pending;
    const privateScope = privateGeneration;
    try {
      const scope = `task:${operation}:${researchId}:${operation === 'start' ? editBase.revision : taskData.task.id}`;
      const prior = sessionStorage.getItem('structure-research-pending:' + scope);
      const data = prior && JSON.parse(prior).task_request || (operation === 'start'
        ? {input_revision:editBase.revision, expected_research_version:editBase.researchVersion, mode:'research'}
        : {task_id:taskData.task.id, expected_task_version:taskData.task_version});
      const body = JSON.stringify({schema_version:schema, contract_revision:revision, data});
      pending = await operationKey(scope, body, null, data);
      if (privateScope !== privateGeneration) throw new Error('账户访问已变化，请重新打开研究页面。');
      const result = await methodRequest(`/api/research/${researchId}/${operation === 'start' ? 'tasks' : operation}`, {method:'POST', headers:{'Content-Type':'application/json','Idempotency-Key':pending.key}, body},methodToken);
      sessionStorage.removeItem(pending.slot);
      if (!renderTask(result, {operation, targetTask:operation === 'start' ? null : data.task_id,methodToken})) {
        byId('task-message').textContent = '较早流程的操作已确认；当前问题保持不变，可从历史流程查看。';
      }
    } catch (error) {
      if (pending && error.status >= 400 && error.status < 500) sessionStorage.removeItem(pending.slot);
      byId('task-message').textContent = error.code === 'REVISION_CONFLICT'
        ? '问题版本已变化，当前草稿和已载入修订保持不变；请明确载入最新修订后再启动。'
        : error.status ? error.message : '操作结果尚未确认，请刷新演练状态，再用原操作核对；不要重复启动。';
    } finally { taskBusy = false; syncTaskButtons(); }
  }
  for (const operation of ['start','cancel','reconcile','resume']) byId('task-' + operation).addEventListener('click', () => taskAction(operation));
  byId('task-refresh').addEventListener('click', async () => {
    if (taskBusy || !researchId) return;
    taskBusy = true; syncTaskButtons();
    const methodToken = beginMethodRead();
    try {
      const result = await methodRequest(viewUrl(),{},methodToken);
      renderTask(result,{methodToken});
    } catch (error) { byId('task-message').textContent = error.message; }
    finally { taskBusy = false; syncTaskButtons(); }
  });
  byId('reload').addEventListener('click', async () => {
    if (busy) return;
    setBusy(true);
    try { await load(); }
    catch (error) { status(error.message, true); }
    finally { setBusy(false); }
  });
  // Clear existing private DOM on restored bfcache pages before revalidating.
  window.addEventListener('pagehide', () => { registryUI?.invalidate('page_suspended','页面已暂离，请重新核对账户后主动读取。'); scenarioUI?.invalidate('page_suspended','页面已暂离，结果已收起；原操作保留。'); });
  window.addEventListener('pageshow', event => {
    if (event.persisted) { clearPrivateView('bfcache_restore'); load().catch(error => status(error.message, true)); }
  });
  initFormula();
  initPlan();
  initDraft();
  initFinancialPreview();
  if (window.EvidenceMethodPlan) evidenceUI = window.EvidenceMethodPlan.mount({document,
    getScope:()=>({account:accountScope,privateGeneration,rid:researchId,revision:editBase?.revision,digest:editBase?.digest,
      version:observed?.researchVersion??editBase?.researchVersion,dirty:methodDirty||formulaState.dirty,readonly:readOnlyView(),busy,visible:!form.hidden&&Boolean(researchId)}),
    authenticate:authenticated,fetchRoot:request,onDenied:clearPrivateView});
  if (window.FinancialRegistry) registryUI = window.FinancialRegistry.mount({document,
    getScope:()=>({account:accountScope,privateGeneration,rid:researchId,revision:editBase?.revision,digest:editBase?.digest,
      version:observed?.researchVersion??editBase?.researchVersion,dirty:methodDirty||formulaState.dirty,readonly:readOnlyView(),busy,visible:!form.hidden&&Boolean(researchId)}),
    authenticate:authenticated,fetchRoot:request,onObservedRoot:data=>observeFinancialRoot(data,'registry')});
  if (window.FinancialScenario) scenarioUI = window.FinancialScenario.mount({document,
    getScope:()=>({account:accountScope,privateGeneration,rid:researchId,revision:editBase?.revision,digest:editBase?.digest,
      version:observed?.researchVersion??editBase?.researchVersion,dirty:methodDirty||formulaState.dirty,readonly:readOnlyView(),busy,visible:!form.hidden&&Boolean(researchId)}),
    getSelectedRegistry:()=>registryUI?.getSelectedRegistry()||null,
    authenticate:authenticated,fetchRoot:request,onObservedRoot:data=>observeFinancialRoot(data,'scenario')});
  for(const id of ['financial-registry-choose','financial-registry-history','financial-registry-reopen','financial-preview-csv'])
    byId(id).addEventListener(id==='financial-preview-csv'?'input':'click',()=>queueMicrotask(()=>scenarioUI?.observeRegistrySelection()));
  function observeFinancialRoot(data,origin){
    const before=observed?.researchVersion||0;observeServer(data);
    if(observed.researchVersion>before){
      financialInvalidate('研究版本已变化，旧预览已失效；CSV 仍暂存在本页。',false);
      financialState.basis=financialBasis();evidenceUI?.observe();
      if(planState.preview&&planState.preview.expected_research_version!==observed.researchVersion)planInvalidate('研究版本已变化，请重新核对外发预览。');
      if(origin!=='registry')registryUI?.observe();
      if(origin!=='scenario')scenarioUI?.observe();
      editNotice();
    }
  }
  load().catch(error => status(error.message, true));
})();
