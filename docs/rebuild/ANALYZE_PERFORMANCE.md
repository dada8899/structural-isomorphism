# Analyze 移动端阻塞诊断

日期：2026-10-16。任务：STRUCTURE-PERF-255 attempt1，Issue #255。源码基线 `044e08c612dc69aa7d3b78887d4a303446be4cef`；改动前业务页面、assets和两份审计脚本与故障头 `31f8680` 相同。状态：完成一次基线和一次修复对照trace，侧栏视口检测的最小业务补丁及针对性回归就绪；尚未提交、独审或通过当前候选CI，不构成发布放行。

## 已确认的 CI 失败

PR beta-perf run `38914802182` attempt1 的 analyze/mobile 三次TBT为212、209、216 ms，中位数212，均超过原200 ms预算。三次测量与清理完成，无页面/请求错误。另一次push成功不抵消该失败，不因接近阈值判为噪声。

实际TBT算法保持原样：对`[FCP,FCP+5000ms]`内裁剪后的longtask，累加超过50ms的部分。mobile为CPU4倍降速和原慢4G配置；原fixture、ready/page/post-interaction验证器及简报按钮可信点击不变。受控API只命中鉴权、收藏和分析流各一次，不存在真实模型请求或费用。

## 一次本机 trace 与边界

本次使用Python 3.11.15、Playwright1.59.0及对应Chromium147／revision1217，Mac本机执行analyze/mobile一次。通过原audit_one的page_setup附加CDP CPU/timeline；原指标计算后，在cleanup pending回调读取原longTasks、资源时序并结束采证，然后由原审计关闭浏览器。脚本未改源码/测量/fixture/profile/阈值。附加Profiler会有开销，Mac也不等同CI runner，诊断分数不得作为门禁或修复验收。

| 本次指标 | 值 |
| --- | ---: |
| FCP | 1808 ms |
| TBT | 184 ms |
| LCP | 1808 ms |
| INP代理 | 24 ms |
| 审计及浏览器cleanup | passed |
| 专属静态服务收尾 | shutdown，线程已结束 |

本机184没有复现CI212，没有追加基线采样寻找红色或绿色。仅用这次轨迹定位本机的直接工作，不冒充对历史CI四个任务的逐栈证明。

原longTasks如下；trace时间轴与PerformanceObserver时间约有2ms偏移，数值分别报告，不能混作同一精度。

| Observer任务开始/时长 | 与本次TBT窗口关系 | 阻塞贡献 |
| --- | --- | ---: |
| 1625.3 / 173 ms | 结束1798.3，早于FCP1808 | 0 |
| 3270.1 / 136 ms | 完整位于窗口 | 86 ms |
| 3637.1 / 148 ms | 完整位于窗口 | 98 ms |

两段贡献86+98=184，与原审计结果一致。不是把全部457ms长任务时长当作TBT。

## 直接工作与尚未证明的部分

第一段trace RunTask约136.89ms，包含DOMContentLoaded处理。`history-sidebar.js:init`下的`syncSidebarAccessibility→isMobile`调用约80.34ms，内含约74.32ms Layout；CPU采样同一isMobile栈约77.89ms。源码在init中依次插入style、侧栏/遮罩/按钮并添加body类，然后syncSidebarAccessibility读取`window.innerWidth < 1024`；轨迹显示该读取在脏布局之后触发同步布局。此路径证据比此前“可能是语义校验/术语全树扫描”的推断更直接。

该文件最初不在允许范围，首次采证后已停写报告；PMO随后精确扩展授权，只允许修复侧栏isMobile/单一断点检测。没有改analyze或glossary绕过侧栏，也没有为凑性能同时改多个业务文件。

第二段trace RunTask约148.53ms，主要为Layout约78.19ms、PrePaint约52.39ms，dirtyObjects648、totalObjects844，是报告出现后的集中布局/绘制前工作。当前采证未提供足以将它唯一归因到某一个业务写入函数的invalidation栈，不能把“发生在报告后”写成已证明是revealFinalReport或语言重渲染造成。

候选语义校验在此次CPU采样中仍有工作，但已跨yield分散，未成为上述两段的主要直接函数；已有缓存和协作让出，不应不看轨迹重复加缓存/yield或削弱校验。glossary全窗口采样栈约24.42ms，不能据旧先验把它当184ms主要来源。六份历史CI加载片段及本次加载没有窗口内KaTeX请求；8秒背景数学定时器也不能当当前已证原因。

## 最小变更和第二次对照

原CSS断点为移动`max-width:1023px`、桌面`min-width:1024px`；原JS为`innerWidth<1024`。本次仅在`history-sidebar.js`中创建一个`window.matchMedia('(max-width: 1023px)')`的live查询，让isMobile读取matches；未新增定时器、延迟工作或第二套resize处理。已有resize事件、焦点、aria/inert和折叠逻辑不变。对本轮验证的整数CSS视口1023/1024边界，两侧含义一致；不声称本轮验证了所有缩放和浏览器组合。

功能回归通过后才使用剩余一次同profiletrace。对照脚本只补记录变更业务asset的前后摘要，测量、CPU/网络profile、fixture、validator、交互、采证hook与窗口不变；两次都带Profiler开销，仍仅是本机诊断。

| 本机诊断 | 基线一次 | 修复一次 |
| --- | ---: | ---: |
| TBT | 184 ms | 118 ms |
| FCP / LCP | 1808 ms | 1616 ms |
| INP代理 | 24 ms | 16 ms |
| history init FunctionCall | 80.343 ms | 1.794 ms |
| 含DOMContentLoaded的长RunTask | 136.892 ms | 73.087 ms |
| 后续报告布局/绘制前RunTask | 148.525 ms | 145.890 ms |
| 对应Layout / PrePaint | 78.191 / 52.387 ms | 82.758 / 47.303 ms |

修复后Observer任务为1532.5/75ms（结束早于FCP1616，不计TBT）、3199.9/73ms、3480/145ms；阻塞贡献23+95=118。与基线86+98对照，侧栏所在DOMContentLoaded任务的阻塞下降63ms，后续帧下降3ms；不能把全部时序变化当成跨环境可重复收益。轨迹直接支持的是：侧栏init中的原强制布局消失，init降到约1.8ms；报告后的大布局仍在，未声称唯一根因全部消除。

三项受控API在两次均各命中一次，无未知/非法API、页面异常或坏静态响应。原六项审计快照前后相同，变更的侧栏文件另外记录摘要：基线Git文件`5fc272c03ec22e15f4e74b32e32d0501ed6874de339f188fdfe7989f8795a2ac`，候选`262c38698adeaeb2831a2ebf4bdefc0a5651bed7308889434869f42a1e0daa6f`。候选尚未提交，不能把基线HEAD冒充补丁的冻结SHA。

## 功能回归

新增Node回归运行完整侧栏脚本，以会抛错的innerWidth/style几何getter作为失败边界，通过公开open/close API验证live查询在1023→1024→390→1280下的角色和inert变化；没有时间阈值或性能数值断言。新增Python回归以真实Chromium147读取实际analyze静态页面（不带分析ID），鉴权/收藏受控、不允许模型或外网请求。

最终Python结果为4 passed，含Node契约封装及三个浏览器用例：断点/移动桌面resize、打开焦点与Tab/Shift+Tab约束、Escape/遮罩关闭和焦点恢复、aria/inert、折叠偏好经过reload保留、历史私有handoff与实际工具/主页导航。历史目标是受控静态接收页，证明handoff构造且问题不进入URL；完整搜索消费继续由既有私有导航回归和后续整体浏览器检查覆盖，不冒充真实搜索质量验收。

既有`test_historyPrivacy.js`、`test_privateNavigation.js`均通过；`test_analyzeTrust.js`47项、`test_reportTrust.js`6项通过且未修改。新增测试草稿曾有一次把页脚“我的研究”误作主导航定位、一次在CSS已切换但resize处理尚未完成时过早断言；已分别依据真实NAV和完整a11y状态就绪条件纠正，没有改变业务来迁就测试，没有用固定sleep掩盖失败。

本机命令（工作目录为本性能树，`STRUCTURE_PERF_PY`指已核Python3.11/Playwright1.59环境）：

```sh
node web/frontend/tests/test_historySidebarPerformance.js
node web/frontend/tests/test_historyPrivacy.js
node web/frontend/tests/test_privateNavigation.js
node web/frontend/tests/test_analyzeTrust.js
node web/frontend/tests/test_reportTrust.js
PYTHONDONTWRITEBYTECODE=1 "$STRUCTURE_PERF_PY" -B -m pytest -p no:cacheprovider tests/test_history_sidebar.py -q
```

实际解释器路径、两次采证完整命令及所有测试尝试结果在私有commands证据中登记。Python浏览器用例标e2e，不因本机执行就宣称现有CI已运行这些新增用例。

## 采证、范围和下一动作

私有采证脚本、原始CPU/timeline、longTasks/资源时序、两阶段原审计样本、源码快照和派生分析保存在本任务批准的输出目录；目录700、文件600，不提交到公开仓库。基线/修复各有一次started标记，采证名额已用完，无额外采样。浏览器cleanup均passed，专属静态服务均shutdown、线程结束、端口关闭；功能测试也以finally关闭context/browser和服务。

本轮只修改已批准的侧栏JS一处，新增两份针对性测试及本文；AGENTS保持未跟踪不提交。HTML/CSS、analyze/glossary、预算、测量脚本、fixture、workflow、后端及其他模块均未修改。下一动作由PMO组织精确补丁独审和最终候选当前CI，正式原八页面×两viewport×三runs门禁仍须通过；不能用trace分数、独立run成功或缩短窗口替代。未验证CI runner复现、其他浏览器及VPS真实用户体验，不继续扩修第二段未唯一归因布局。

完整报告校验、来源/hash/section绑定、过期generation拒绝、九节内容、语言切换、术语键盘行为、简报、分享、收藏、保存及主导航/历史访问均须保留。若后续修复不能维持这些行为，先返修而不是降低验收标准。
