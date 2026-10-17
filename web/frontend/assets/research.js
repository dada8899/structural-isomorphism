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
  let accountScope = null;
  let methodGeneration = 0;
  let methodSeen = false;
  let methodDirty = false;
  let historySeen = false;
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

  function status(message, error = false) {
    byId('status').textContent = message;
    byId('status').dataset.error = String(error);
  }
  function setBusy(value) {
    busy = value;
    // Freeze the submitted draft until the receipt is handled. Otherwise a
    // late render could silently replace edits made while fetch was pending.
    for (const control of form.querySelectorAll('input, textarea, select, button')) control.disabled = value || (readOnlyView() && control.id !== 'reload');
    syncTaskButtons();
    syncFormulaControls();
  }
  function normalizeProblem(problem) {
    // Match ProblemInput exactly; original_input intentionally stays verbatim.
    return {...problem, objective:problem.objective.normalize('NFC'), summary:problem.summary.normalize('NFC'),
      constraints:problem.constraints.map(value => value.normalize('NFC')),
      unknowns:problem.unknowns.map(value => value.normalize('NFC')),
      variables:problem.variables.map(variable => ({...variable, label:variable.label.normalize('NFC'),
        observation:variable.observation === null ? null : variable.observation.normalize('NFC')}))};
  }
  function clearPrivateView() {
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
          clearPrivateView();
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
      button.hidden = readOnlyView() || Boolean(taskData?.is_historical) || !actions.includes(action);
      button.disabled = taskBusy || (operation === 'start' && busy);
    }
    byId('task-refresh').disabled = taskBusy;
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
    byId('view-context').hidden = !readOnlyView();
    byId('view-context').textContent = data.is_historical ? '历史流程，只读查看原问题与原记录；不代表当前修订的研究结果。' : selectedTask ? '固定任务只读查看。这是当前任务，不是历史结果；返回当前问题后才能编辑。' : '';
    if (selectedTask) status(data.is_historical ? '已读取历史流程的原问题，只读查看；方法正文以下方状态为准。' : '已读取固定任务，只读查看；该任务仍是当前任务。');
    renderTaskHistory(data);
    byId('source-query').disabled = readOnlyView();
    for (const node of byId('source-section').querySelectorAll('.source-write-ui')) node.hidden = readOnlyView();
    byId('source-title').textContent = readOnlyView() ? '来源笔记（只读）' : '可选：继续查找方法来源';
    byId('source-preview').hidden = readOnlyView();
    if (readOnlyView()) byId('source-confirm').hidden = true;
    byId('task-title').textContent = '本机流程演练';
    byId('task-scope').textContent = '仅验证保存、调用与对账流程，不访问真实供应端、不扣真实费用，也不代表研究成果。';
    byId('source-section').hidden = !data.capabilities?.source_evidence;
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
    const original = byId('original-input').value;
    const length = Array.from(original).length;
    if (!summaryEdited && !editBase) byId('summary').value = length <= 1000 ? original : '';
    byId('summary-hint').textContent = length > 1000
      ? '原文超过 1000 字，已完整保留。请另写 8–1000 字摘要；不会截断原文或自动生成摘要。'
      : '待核验草稿：这里只回显原话，可直接编辑；尚未进行模型结构化或确认。';
  }
  async function authenticated(isCurrent, signal) {
    const unavailable = () => {
      if (isCurrent()) { invalidateMethod('账户状态暂时无法核对，已收起旧方法记录；草稿仍保留。'); formulaAuthUncertain(); clearTaskHistory('账户状态暂时无法核对，流程列表已收起；请稍后主动读取。'); }
      if (isCurrent()) status('账户状态暂时无法核对；草稿与待核对操作已保留，本次后续请求已停止。请稍后主动重试。', true);
      return false;
    };
    try {
      const response = await fetch('/api/auth/me', {cache:'no-store', credentials:'same-origin', signal});
      if (!isCurrent()) return false;
      // /auth/me confirms missing, invalid or revoked sessions with 401.
      // Other HTTP failures alone say nothing about the account's authority.
      if (response.status === 401) {
        clearPrivateView(); status('账户访问已失效，请重新登录。', true); return false;
      }
      if (!response.ok && response.status !== 409) return unavailable();
      const payload = await response.json();
      if (!isCurrent()) return false;
      if (response.status === 409 && payload?.ok === false && payload.error === 'credential_conflict') {
        clearPrivateView(); status('账户凭据存在冲突，请重新确认账户。', true); return false;
      }
      if (!response.ok || payload?.ok !== true || typeof payload.user?.email !== 'string' || !payload.user.email.trim() ||
          typeof payload.user.created_at !== 'string' || !payload.user.created_at.trim()) return unavailable();
      const identity = JSON.stringify([payload.user.email, payload.user.created_at]);
      if (accountScope && accountScope !== identity) {
        clearPrivateView(); status('账户已变化，请重新打开研究页面。', true); return false;
      }
      accountScope = identity;
      return true;
    } catch (error) {
      return unavailable();
    }
  }
  function positionInitialSection() {
    if (entryPositioned || !initialSection || form.hidden) return;
    const section = byId(initialSection);
    if (!section || section.hidden) return;
    entryPositioned = true;
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
      formulaProblemEdited();
      if (id === 'summary') summaryEdited = true;
      if (id === 'original-input') echoDraft();
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
      if (response.status === 401 || response.status === 404 || data.error?.code === 'AUTHORIZATION_STALE') { clearPrivateView(); status('账户访问已失效，请重新登录。', true); return; }
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
  async function sourcePost(operation, data, isCurrent = () => true) {
    if (readOnlyView()) throw new Error('此页只读，请返回当前问题后操作。');
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
    finally { sourceBusy = false; }
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
    if (sourceBusy || busy || taskBusy || !editBase || editBase.historical) return;
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
      if (!active()) return;
      sourcePreview = {...data,preview_digest:result.preview_digest};
      byId('source-plan').textContent = `实际对外关键词：${result.query}\n绑定已保存修订 ${result.input_revision}（不含表单中的未保存修改）\n最多读取 ${result.plan.max_requests} 次 GET 来源；不会发送现象原文、目标或私有标签。`;
      byId('source-status').textContent = '预览完成；尚未开始读取来源。';
      byId('source-confirm').hidden = false;
    } catch (error) { if (active()) byId('source-status').textContent = error.message; }
    finally { sourceBusy = false; byId('source-preview').disabled = false; }
  });
  byId('source-query').addEventListener('input', () => { sourcePreviewGeneration++; sourcePreview = null; sourceApproval = null; byId('source-confirm').hidden = true; byId('source-plan').textContent = ''; byId('source-status').textContent = '关键词已变化，请重新预览；尚未开始读取来源。'; });
  byId('source-confirm').addEventListener('click', async () => {
    if (sourceBusy || busy || taskBusy || !sourcePreview || editBase?.historical) return;
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
    finally { sourceBusy = false; }
  });
  byId('source-refresh').addEventListener('click', async () => {
    if (sourceBusy || busy || taskBusy || !researchId) return;
    sourceBusy = true;
    const methodToken = beginMethodRead();
    try { renderTask(await methodRequest(viewUrl(),{},methodToken),{methodToken}); await sourceRecords(); }
    catch (error) { byId('source-status').textContent = error.message; }
    finally { sourceBusy = false; }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || readOnlyView()) return;
    const methodToken = beginMethodRead();
    setBusy(true);
    status('正在保存，请保留当前页面…');
    let pending;
    const privateScope = privateGeneration;
    try {
      const problem = normalizeProblem({entry:byId('entry').value, original_input:byId('original-input').value,
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
      sessionStorage.removeItem(pending.slot);
      history.replaceState(null, '', `/research/${saved.research.id}`);
      render(saved,methodToken);
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
  });
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
  window.addEventListener('pageshow', event => {
    if (event.persisted) { clearPrivateView(); load().catch(error => status(error.message, true)); }
  });
  initFormula();
  load().catch(error => status(error.message, true));
})();
