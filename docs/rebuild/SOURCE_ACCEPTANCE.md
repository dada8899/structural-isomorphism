# PLOS 许可措辞与叙述子集接纳

日期：2026-10-17。基线：`fb8491e772fb996c0819494a1e8e88ce77b3d92f`。
分支：`codex/structure-source-acceptance-20261017`。本轮为独立候选，尚未提交、发布或再次真实取证。

## 取舍与版本

许可仅兼容 `open-access article distributed under the terms of the Creative Commons Attribution License` 与空格版完整固定措辞，仍须完整 unrestricted／credit 句联立。
Crossref CC BY 4.0、DOI／title／citation、唯一闭合当前 articleinfo、原版权冲突／限制／taint 条件保持；显式 `quoted-other` 同现有 blockquote 一样不能冒当前版权声明。
没有全局去连字符、模糊猜许可或由元数据单独授权。

新派生版本为 `plos-author-narrative-subset-v2`，只取唯一、正确闭合的当前 `artText` 与 `article-body` 交集，可支持二者合法的两种嵌套顺序。
排除站点块、articleinfo／元信息、评论、显式他人引文及参考列表；许可范围判断和正文范围判断使用独立状态。
保留普通行内引用链接文字、作者段落上下文及科学 Discussion，不将有引用的整段或 Discussion 一律当成评论删除。
未标明的转述／引用没有语义归属审查；这是有限叙述子集，不是全文或已确认作者主张。
内联文字保持连续，块边界及被省略的显式他人内容用边界空白分隔；新提取文本统一空白后重算 UTF-8 摘要和 Unicode 短引偏移。
空、重复或不正确闭合的正文容器不能产生新快照。许可未知时原否定探针仍得到 unknown，fetch 在缓存／快照创建前拒绝。

原始响应字节及 raw_digest 完整保留且私有，包含排除出的引文、参考和站点文本；不销毁原证据。
private_cache／display／export 沿原各自许可，不由 raw 缓存推导 may_send_to_provider；没有模型调用或新增外发授权。

## 共享端口

DataSnapshot 仅在原 parser_version allowlist 增加 v2；无新增存储字段、SQL 或迁移。
现有公开 SourceRecord 和报告 SourceVersion 派生 `read_scope`：v1=`legacy_page_unverified`，v2=`author_narrative_subset`。
映射严格来自已解码的版本，不能由客户端自报或把旧 v1 自动升为 v2／模型资格；未知版本仍拒绝。
旧 snapshot、raw／extracted 摘要、偏移、payload 与版本不改写；新抓取创建新不可变记录。
报告投影沿原算法将新增 scope 纳入派生 DTO 摘要，不修改旧数据库 payload 摘要。
公开白名单仅新增 scope，不泄漏原缓存、提取全文、发现响应、内部 snapshot_id、provider_ref 或执行控制。
契约仅 SourceRecord／SourceVersion 两处说明增量，API／ORM／资金／配额／gate／SourcePolicy／前端保持不变。

## 本轮验证

两份原正 fixture 只将原唯一叙述句移入合法容器，原 outside-only 形态另作拒绝对照；没有删除原反例。
原 root 所有测试方法 AST 保持；新增两种完整许可、缺 credit／不完整措辞、显式他人版权、容器／Unicode／内联／引文与 Discussion 对照。
Backend 原测试仅严格 SourceRecord key 集合增加 read_scope，原迁移／时序断言保持。
新增真实 loopback HTTP→授权→同库→records 对照：raw 完整、正文与默认前20词不混外部内容、source/report scope 相等、准确短引与摘要可核。
旧 v1 合成快照与新 v2 同研究对照逐行比较旧证据表和公开记录，保持旧数据，模型／统计仍未运行。
所有真实 socket 均为本任务合成 loopback，进程／服务沿原 finally 收束，无公开 GET、自动重试、依赖安装或费用。
最终 root source＋evidence 独立进程 **58 passed、58 subtests passed、退出0（1.38秒）**；backend 完整 D1 集成文件独立进程 **43 passed、退出0（50.36秒）**，两条既有依赖 warning。
AST／精确路径／差异检查通过；八文件摘要见停写回执。仍须 PMO 当前 SHA 独审后，才做一次真实全链接纳验证；本机合成结果不冒真实公开研究已完成。
