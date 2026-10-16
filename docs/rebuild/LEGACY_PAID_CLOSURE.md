# A006 旧 Web 计费出口关闭候选

日期：2026-10-17；基线：`fbd0b9ee01e6c0036e042ba2a4e58e7e0fadc6d8`。本轮仅旧 Web 发送与 admission，不接新 provider，不是全运行制品／VPS费用验收。

## 实际代码边界

- `LegacyPaidUnavailable` 复用 ProblemDetail，统一503／FEATURE_UNAVAILABLE／不可自动重试；flat/package导入共用异常类型。
- `_get_http_client` 无条件拒绝，不返回裸 client；旧 LLMService 不加载 key，llm_available 固定 false，model、URL、key 或环境变量不能恢复旧付款路径。
- 六个 LLMService 发送方法、三 llm_client 方法、两 Ask 发送与重试入口、旧翻译 batch 均在网络准备／吞异常前拒绝。四工具 service 只对可能吞掉该 typed 异常的调用链重抛，不改候选检索／推理算法。
- Ask、Synthesize、Search rewrite/assess、Method/Stress/Lint/Diagnose直接 admission；Analyze/Mapping仅允许已有受检公共配对缓存，其余在构造生成 SSE 前拒绝。不会因 None/fallback 显示“已生成”。
- Phase 七个动态POST在prod/dev均503，直接helper及三个stream也拒绝；不扩大关闭auth、静态或原读取路径。已存在的其他生产路由策略保持。

## 保留的读取

- 中文rewrite=false走原 SearchService 本地向量／KB排序，未改检索算法。
- Mapping除schema/lang/公共KB配对外，必须匹配产生时冻结的两侧公共源摘要与artifact；新固定持久行保存binding，读时只比较。旧无binding行不追认、不写回，源／artifact改后及重启仍拒；Analyze保持已有强绑定，失配不回退生成。
- 缓存响应明确from_cache；Analyze缓存回放不新建报告、不刷新取得时间或伪发persisted事件。新保存能力由新研究流程另接，不在此补丁扩建。
- 英文详情／搜索只读取source-bound的公共翻译缓存，miss保留原文，HTTP头明确cache-only/original-on-miss。无版本／源摘要的旧翻译条目不冒充当前翻译。
- 私有报告、账户读取与新研究Core保持原代码；本轮没有读取真实账户或验证其全部生命周期。

## 实际消费者与后续提示

只读确认：浏览器api.js搜索明确rewrite=false；search.js独立await搜索，assess失败转null，不会连带关闭普通排序结果。MCP搜索仅query/top_k，后端默认rewrite=false。

搜索页仍默认发assess和synthesis，比较失败组件仍有重试按钮。需Product/UI owner在后续限定前端范围识别FEATURE_UNAVAILABLE并说明旧动态比较停用／保留本地候选／引导研究；本轮不改前端，不把API正例当完整用户入口已验收。

## 验证与未覆盖

新测试使用真实FastAPI路由和ProblemDetail处理器、真实本地检索数学、磁盘缓存与严格报告绑定；embedding／KB输入、日志和dotenv loader为固定边界。仅合成key与最小测试环境，禁止任何真实网络、凭据／邮件或模型加载。

测试覆盖16个旧Web发送site的入口、prod/dev Phase七路由、直接client/helper、SSE头前503、flat/package异常、合法本地检索／静态／授权公共缓存与失配缓存拒绝；实际测试数／环境见当前回执，独审和Linux组合另记。

作者最终在发布匹配Python3.11.15／FastAPI0.135.0／Pydantic2.7.4／Starlette1.3.1运行：新测试28通过，旧Mapping28通过。旧文件仅获准三函数修订：miss在SSE前typed拒绝且无partial／rewrite／done，严格候选及score结构转由真实版本配对cache命中承接，语言失配／非公开KB拒绝；其余AST节点不变。

缓存边界返修新增两侧源摘要／artifact持久绑定，当前新增测试40通过，旧Mapping28通过；旧文件仅在原两个缓存正例的合成数据产生时冻结binding，其他函数／断言保留。同步及SSE分别覆盖源／target名称描述和artifact改变、内存及重启读取拒绝、unbound拒绝及合法bound重启读取；不读时补签或改旧行。

24个独立SDK／CLI发送site、真实launchd安装状态、Nightly代码分支和实际发布制品／凭据继承隔离由既定owner另证。本轮不改公共SDK、CLI、CI或部署，不因“没key／没安装／未运行／改manifest”登记关闭，也不删除研究资产。

新DeepSeek公开paid_disabled与C0 fixture字节保持；它们不是旧Web闭合的替身。未执行真实调用、扣费、SSH、旧请求撤回、VPS部署或费用对账；本补丁不证明旧进程／旧版本已退出，发布恢复仍须核真实版本与未结调用。

## 2026-10-17 输入检查顺序检查点

- 八个 API 在关闭动态生成前执行纯输入检查；Ask/Analyze 有效形状先校验调用身份，再判定范围，非法身份保持 HTTP 401。
- Analyze 查询与 lint 流式入口在 SSE/meta 前返回 HTTP 400/422；所有模型、检索准备及生成写入仍处于关闭检查之后。强绑定公开 pair 缓存和免费原文检索保留。
- 同一既有 Python 3.11 运行环境：关闭与准入测试 59 通过；原 Mapping 契约 28 通过。新增准备步骤 spy 与发送 spy 均零调用。
- 原 98 项未闭合旧测试尚未适配，九个原测试文件本轮未修改；本检查点等待精确差异独审，不能据此宣布整体回归通过。
