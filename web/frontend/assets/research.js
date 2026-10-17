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
  const initialSection = ['#my-research', '#kb-section'].includes(location.hash) ? location.hash.slice(1) : null;
  let initialLoad = true;
  let entryPositioned = false;
  const initialPath = location.pathname.split('/').filter(Boolean);
  let researchId = initialPath.length === 2 ? initialPath[1] : null;
  const selectedTask = new URLSearchParams(location.search).get('task_id');
  const validId = value => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);

  function clearMethod(message, hide = false) {
    byId('method-body').replaceChildren();
    byId('method-citations').replaceChildren();
    byId('method-meta').hidden = true;
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
    try { return await request(url,options); }
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
          !digest(value.candidate_digest) || !digest(value.envelope_digest) || value.is_historical !== false ||
          value.execution_mode !== 'offline_probe' || value.model_analysis_ran !== false || value.status !== 'qualified_report' ||
          value.evidence !== 'INSUFFICIENT' || value.assessment !== 'llm_inference' || value.review !== 'unreviewed' ||
          typeof value.received_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(value.received_at) || !Number.isFinite(Date.parse(value.received_at)) ||
          data.research?.id !== researchId || data.is_historical === true || !integer(data.research_version) || !integer(data.task_version) ||
          data.research.version !== data.research_version || !validId(data.task?.id) || data.task.version !== data.task_version ||
          data.task?.policy_revision !== 'bounded_usage_upper_v2' || data.execution !== 'COMPLETED' || data.task.execution !== 'COMPLETED' || data.task.stop_requested !== false ||
          data.research.current_task_id !== data.task.id || data.evidence !== 'INSUFFICIENT' || data.report_status !== 'qualified_report' || data.execution_mode !== 'offline_probe' ||
          value.input_revision !== data.research.current_revision || value.input_revision !== data.current_problem?.revision ||
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
    byId('method-time').dateTime = value.received_at;
    byId('method-time').textContent = new Intl.DateTimeFormat('zh-CN', {dateStyle:'medium',timeStyle:'long'}).format(new Date(value.received_at));
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

  function status(message, error = false) {
    byId('status').textContent = message;
    byId('status').dataset.error = String(error);
  }
  function setBusy(value) {
    busy = value;
    // Freeze the submitted draft until the receipt is handled. Otherwise a
    // late render could silently replace edits made while fetch was pending.
    for (const control of form.querySelectorAll('input, textarea, select, button')) control.disabled = value || (Boolean(editBase?.historical) && control.id !== 'reload');
    syncTaskButtons();
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
    const active = () => privateScope === privateGeneration && isCurrent();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, {...options, credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
      if (!active()) throw new Error('较早的来源读取已失效。');
      const payload = await response.json();
      if (!active()) throw new Error('较早的来源读取已失效。');
      if (!response.ok) {
        if (response.status === 401 || response.status === 404 || payload.error?.code === 'AUTHORIZATION_STALE') clearPrivateView();
        const error = new Error(payload.error?.message || '操作暂时无法完成，请保留当前内容。');
        error.status = response.status;
        error.code = payload.error?.code;
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
    byId('variables').hidden = variables.length === 0;
    byId('variables').textContent = variables.map(v => `${v.label} (${v.id}) · ${v.unit_id || '单位待确认'} · ${v.observation || '观测待补充'}`).join('\n');
    byId('revision-label').textContent = `当前修订 ${problem.revision}`;
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
    setBusy(busy);
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
      button.hidden = !actions.includes(action) || (operation === 'start' && Boolean(taskData?.is_historical));
      button.disabled = taskBusy || (operation === 'start' && busy);
    }
    byId('task-refresh').disabled = taskBusy;
  }
  function renderTask(data, context = {}) {
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
    byId('task-current').hidden = !data.is_historical;
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
    syncTaskButtons();
    renderMethod(data,context.methodToken);
    return true;
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
      if (isCurrent()) invalidateMethod('账户状态暂时无法核对，已收起旧方法记录；草稿仍保留。');
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
    if (selectedTask && !validId(selectedTask)) { clearPrivateView(); status('流程链接无效。', true); return; }
    const data = await methodRequest(viewUrl(),{},methodToken);
    if (methodToken.generation !== methodGeneration) return;
    render(data,methodToken);
    byId('my-research').hidden = false;
    loadResearchList(false, positionEntry);
    if (positionEntry && initialSection === 'kb-section') positionInitialSection();
    await recoverSourceIntent();
    if (!editNotice()) status('已从账户读取保存的问题；尚未执行研究。');
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
    if (!researchId || !taskData?.capabilities?.source_evidence) return;
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
    if (busy || editBase?.historical) return;
    const methodToken = beginMethodRead();
    setBusy(true);
    status('正在保存，请保留当前页面…');
    let pending;
    const privateScope = privateGeneration;
    try {
      const problem = normalizeProblem({entry:byId('entry').value, original_input:byId('original-input').value,
        objective:byId('objective').value, summary:byId('summary').value, variables,
        constraints:lines('constraints'), unknowns:lines('unknowns'), confirmed:byId('confirmed').checked});
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
    if (taskBusy || !taskData || (operation === 'start' && busy)) return;
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
  load().catch(error => status(error.message, true));
})();
