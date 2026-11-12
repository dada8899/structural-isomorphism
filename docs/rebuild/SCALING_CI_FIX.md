# LLM 学习曲线产物 CI 修复候选

日期：2026-10-16。任务 STRUCTURE-SCALING-CI / attempt 1，Issue #252；基线 `be3a3c6b5de19f2508335519d01240077bb591ec`。以下为作者证据，待独立数学／代码审查和 Linux 当前 SHA CI，不是最终通过。

## 原失败与本地复现

GitHub sanity run `38911548818` 在 Python 3.11.17、13 个精确依赖安装后，比较 `$.fits.pythia-2.8b.A` 失败。旧日志无具体 expected/observed，不能断言仅 A 漂移或唯一 Linux 根因。本地 macOS arm64／Python 3.11.15 与全部锁版本匹配，旧九组拟合所有浮点在12位canonical下与旧提交一致；原2.8b向下1ULP输入扰动使A相对变化0.0019166283，预测最大变化仅1.3515242e-7。不是简单旧产物过期。

未发现可调用的 Docker／Podman 入口，未安装或使用 VPS；Linux 实际值和跨平台结果未验。新增只读 `run_validation.py --diagnose` 输出 Python patch、CPU／BLAS简要、13锁版本、输入／实现摘要和九组expected/observed；门禁失败保留完整诊断；成功的`--check`也把该次已生成的完整诊断以strict JSON写stderr，stdout仍只给原summary，返回值不变，不重拟合第二次。不读环境秘密或输出账号配置。

## 固定数值实现与原边界

仍最小化原损失空间SSE。参数为 `(log(A), alpha, L_inf)`；以中心化 `x=log(C)-mean(log(C))` 计算派生幅值B，B不另设边界，原A界在log坐标严格对应。解析导数为 `(t,-log(C)*t,1)`，`t=A*C^(-alpha)`。按 `(C,L)` 排序；默认固定alpha starts `(0.1,0.3,0.6,1.0)`（裁至原界），只按四次原SSE最低选取，不看来源或科学结论。显式initial_guess仍使用单初值；不声称全局最优。

协方差在实际优化坐标中用SVD计算再映射至A。触界、秩不足或条件数超过`1/sqrt(machine epsilon)`时，不报告无约束标准误；SE为null，附bound_hit、active_bounds、weak_or_unestablished及原因。其他SE也只标局部线性诊断，不作为真实参数置信区间。图注明缺失误差条表示不可用，不是零误差。

原比较容差rel=1e-4／abs=1e-10、13依赖锁、原始CSV、来源归类、科学分类规则和指数推断样本边界未改。原A乘1.001及语义篡改仍失败，保留metadata的PNG像素篡改也失败。

## 原参数与新参数

| 系列 | A 原→新 | alpha 原→新 | L_inf 原→新 | 分类 原→新 |
| --- | --- | --- | --- | --- |
| pythia-1.4b | 1e+12 → 1e+12 | 1.9999 → 0.578230593 | 1.81789641 → 1.21501832 | rejected → descriptive_only |
| pythia-160m | 20.3026667 → 20.3026091 | 0.0949112284 → 0.0949111415 | 1.99977485 → 1.99977455 | fit_quality_eligible → fit_quality_eligible |
| pythia-1b | 57.4792277 → 57.4791272 | 0.116413936 → 0.116413888 | 1.71566885 → 1.71566873 | fit_quality_eligible → fit_quality_eligible |
| pythia-2.8b | 58101487.9 → 1e+12 | 0.399692275 → 0.60343936 | 1.61913901 → 1.66200968 | descriptive_only → descriptive_only |
| pythia-410m | 7.35429164e+10 → 7.35452939e+10 | 0.575658313 → 0.575659055 | 2.00068335 → 2.00068371 | fit_quality_eligible → fit_quality_eligible |
| pythia-6.9b | 190.720574 → 190.720324 | 0.134789616 → 0.134789583 | 1.45681606 → 1.45681598 | fit_quality_eligible → fit_quality_eligible |
| pythia-70m | 1111008.07 → 1110996.33 | 0.311882473 → 0.311882196 | 1.71222258 → 1.71222056 | fit_quality_eligible → fit_quality_eligible |
| kaplan2020-gpt | 24.9343411 → 24.9343411 | 0.0495220405 → 0.0495220406 | 5.70760417e-12 → 8.24068668e-18 | fit_quality_eligible → fit_quality_eligible |
| hoffmann2022-chinchilla | 1468.34556 → 1468.34439 | 0.161264068 → 0.161264048 | 1.71142824 → 1.71142817 | fit_quality_eligible → fit_quality_eligible |

## 原目标、预测与辨识

| 系列 | SSE 原→新 | R² 原→新 | 最大预测差 | 界命中／辨识 | 推断边界 |
| --- | --- | --- | --- | --- | --- |
| pythia-1.4b | 0.0206821203 → 0.0179242216 | -0.00760810804 → 0.126753411 | 0.0157038144 | A；weak_or_unestablished | 窄尾，仍不入指数推断 |
| pythia-160m | 0.000610536088 → 0.000610536088 | 0.99190171 → 0.99190171 | 1.10795351e-08 | 无；local_linearized_diagnostic_only | 合成／文献锚点，不充当真实宽样本 |
| pythia-1b | 0.000141395886 → 0.000141395886 | 0.998455168 → 0.998455168 | 7.82255638e-09 | 无；local_linearized_diagnostic_only | 合成／文献锚点，不充当真实宽样本 |
| pythia-2.8b | 0.0141664612 → 0.0141663696 | 0.0127984979 → 0.0128048847 | 1.81973621e-05 | A；weak_or_unestablished | 窄尾，仍不入指数推断 |
| pythia-410m | 0.0270754254 → 0.0270754254 | 0.985609255 → 0.985609255 | 2.14593525e-07 | 无；local_linearized_diagnostic_only | 真实宽范围，仍仅两组 |
| pythia-6.9b | 0.000231843021 → 0.000231843021 | 0.998493436 → 0.998493436 | 6.95923053e-09 | 无；local_linearized_diagnostic_only | 合成／文献锚点，不充当真实宽样本 |
| pythia-70m | 2.30472993 → 2.30472993 | 0.973249707 → 0.973249707 | 1.19809218e-06 | 无；local_linearized_diagnostic_only | 真实宽范围，仍仅两组 |
| kaplan2020-gpt | 0.00015067825 → 0.00015067825 | 0.998040802 → 0.998040802 | 9.12804277e-11 | L_inf；weak_or_unestablished | 合成／文献锚点，不充当真实宽样本 |
| hoffmann2022-chinchilla | 0.00436091403 → 0.00436091403 | 0.998831105 → 0.998831105 | 3.45897653e-08 | 无；local_linearized_diagnostic_only | 合成／文献锚点，不充当真实宽样本 |

2.8b新A触及原1e12上界，不能当作可识别真实最优或高精度证据。固定alpha=0.1和0.6的profile在原A／L_inf界内仍可取得接近SSE而A相差多个数量级；稳定求解没有消除数据不可辨识性。

1.4b旧求解器停在alpha≈1.9999、R²<0；新实现降低相同目标后R²≈0.12675，按未改的规则从rejected转为descriptive_only。它仍是REAL_TAIL_NARROW，不是新增实验或增强机制证据。真实宽范围仍为70m和410m两组，科学结论仍为`INSUFFICIENT_REAL_WIDE_SERIES_FOR_UNIVERSALITY_INFERENCE`，不增加推断样本或普适结论。

## 新生成合同与验证

主schema1.4注明重新分析日期2026-10-16与旧产物日期2026-05-25；记录estimator、三份原始CSV完整摘要、拟合器／主生成器／锁文件摘要。cross-source JSON与12b spotlight绑定三份输入JSON和派生实现摘要；PNG绑定完整summary摘要，并按metadata、尺寸、解码RGBA像素检查。旧产物可从基线Git定位，不覆盖历史。

- 锁匹配环境为macOS arm64／Python3.11.15、NumPy1.26.3、SciPy1.16.3、openblas64 0.3.23.dev；13精确依赖符合原锁。
- 原31项验证、19项数值／绑定反例及1项成功检查协议对照，51 passed，无skip。覆盖宽范围已知参数、解析Jacobian独立中心差分、固定starts和原A约束、近常数／触界、行序／1ULP、不同初值／profile、material／语义及PNG像素篡改。
- 两fresh子进程，BLAS／OMP线程分别1和2：五项产物逐字节相同，原locked full artifact gate两次通过。这不是Linux或跨架构证据。
- PNG已目视检查可读，未更改图中科学阈值，缺失误差条含明确说明。
- 未执行SSH、付费／模型API、产品或迁移；不碰B0 workflow和PMO文件，不commit／push。停写后由PMO绑定精确HEAD安排独立数学／代码审查与Linux完整observed及必要CI。

## 成功检查取证补齐

本次补丁只让成功的原必要CI也留下同一次拟合的九组observed。对照验证`main(write=False)`仅调用一次，stderr能严格JSON解析且expected/observed各九组，CLI stdout仍等于原summary。完整fits与summary数值同补丁前逐项一致；只是生成器实现摘要与对应JSON／PNG绑定更新，不是新的科学再分析证据。

## 五项统一产物

| 产物 | SHA-256 |
| --- | --- |
| `results.json` | `892f07fd3a4dfe74027a12ca6c55c105880491096b741154a2c07e57195f0580` |
| `summary.md` | `bd066d46c023c2a38c248159307488845c6a98a08fe533bd50f4bfb38ff5c24f` |
| `cross_source_summary.json` | `2ac85f9aaa650732d8ef2828e218278bb8c6c3a3da8334fe5c2d0caff2133655` |
| `pythia_12b_cross_source.json` | `f20fdcb63dfa2fad0c3d6ab6bc2fed8554f2ef8ed23e0b70e0a511a65fb21ef7` |
| `figures/cross_source_alpha.png` | `ad89a712fa83d342bc8da7146778f5452fecbedaea8b36c1b0ab6f3129e0c3c4` |

## 原始输入保留

三份CSV在Git中为LFS pointer，以下按payload摘要和size核验，不把pointer文字与展开数据当作字节差异。

- `pythia_checkpoints_combined.csv`：payload与基线完全一致，18681 bytes，SHA-256 `5c68ba65c7b2b787827580c64cdcddf2895e78445365e1f1ebcae63325de0a15`。
- `kaplan2020_compute.csv`：payload与基线完全一致，553 bytes，SHA-256 `fa78385fddff969ee2b1e6f18261534e12e709a5d3b3048297b2e27ad83223da`。
- `hoffmann2022_compute.csv`：payload与基线完全一致，768 bytes，SHA-256 `31dc2e0d76cf23e192ab2fb6e7993b4be2d89c9b79408001782d7690df28527d`。

## P2 调用方回归返修

独立Astra审查候选`72e9e61d65fb9c54b6f6de21a192142a36d08572`发现：新拟合器在触界时诚实返回`alpha_se=None`，两个既有LAMBADA生成器却直接使用`a_se:.4f`。真实8组数据下，两调用方都先写JSON、再在Markdown格式化时TypeError，留下半套新产物。原基线两调用方能完成，故这是本次引入的消费回归；该候选未push、未接受。

返修只改两调用方的标准误消费：null显示`unavailable`并包含covariance_status、active_bounds和parameter_identifiability，合法数值仍按原四位格式显示，合法0不变成缺失。JSON与Markdown全部序列化／渲染完成后才进行任一写入；这防止渲染异常造成半更新，不承诺磁盘故障时双文件事务原子性。

回归在测试自有临时输出运行两套真实8组main，检查JSON null与Markdown不可用原因一致；另有正常数值／0控制和强制渲染失败旧JSON／MD同时不变。本轮锁环境原51项、8项调用方回归及4项R²控制合计63 passed、无skip。未重生成`results_lambada*.json`或`summary_lambada*.md`；原数据、阈值、边界、主3源码及五项绑定产物均未更改。本轮仍待新SHA受影响独审与Linux CI。

相关摘要一致性还补一处已存在的v1字段问题：原Markdown只读旧名`r_squared`，而JSON的规范字段为`R2`，导致正常R²显示nan。按PMO批准仅改单行，优先规范`R2`，仅缺字段时回退旧名，不用truthiness，故0和负值保持。四项受控消费者对照覆盖规范字段优先、0、负值和旧别名；两套真实调用同时核对JSON与Markdown的R²。该问题在旧基线已存在，不是本次None回归或原CI失败根因，未改变拟合值、来源、统计阈值或科学结论。
