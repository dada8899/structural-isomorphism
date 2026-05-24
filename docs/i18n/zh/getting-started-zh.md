# 快速开始

[English](../../getting-started.md) | **简体中文**

本文将带你完成 **Structural Isomorphism** 的本地安装，并在本地运行第一个预注册验证。

## 前置依赖

- Python 3.12 或更新版本（开发目标是 3.14）。
- macOS 或 Linux。Windows 未做测试。
- 大约 5 GB 的磁盘空间，用于缓存数据集。

## 安装

=== "从源码（推荐）"

    ```bash
    git clone https://github.com/dada8899/structural-isomorphism.git
    cd structural-isomorphism
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
    ```

=== "仅安装流水线包"

    共享分析栈将以 `soc-pipeline` 的名字发布到 PyPI。在此之前，请按上面的方式从克隆的仓库做可编辑安装。

    ```bash
    # 占位——即将上线
    pip install soc-pipeline
    ```

共享分析栈位于 `v4/lib/soc_pipeline.py`，没有重的 PyPI 之外的依赖。Web 后端（位于 `web/backend/`）额外依赖 FastAPI 和少量异步客户端库；详见 `web/backend/requirements.txt`。

## 入门示例——地震数据

```bash
v4 status              # 展示 13 个系统 + 4 个空对照的 PASS / FAIL
```

编程方式调用示例：

```python
from v4.lib.soc_pipeline import fit_clauset_powerlaw, vuong_lr

result = fit_clauset_powerlaw(sizes, discrete=True)
print(result.alpha, result.x_min, result.n_tail)

lr_ln  = vuong_lr(sizes, result, alternative="lognormal")
lr_exp = vuong_lr(sizes, result, alternative="exponential")
print(lr_ln.R, lr_ln.p, lr_exp.R, lr_exp.p)
```

完整 API 参见 [Pipeline](../../pipeline.md)。

## 跑一个已有的验证

每个系统在 `v4/validation/` 下都有自己的文件夹。要重放一次拟合：

```bash
.venv/bin/python v4/scripts/run_preregistered_validation.py \
    v4/preregistration/cve-vulnerabilities.yaml
```

这一步将：

1. 读取预注册的 YAML 文件；
2. 消费缓存在 `v4/validation/cve-vulnerabilities/burst_sizes.json` 中的爆发规模数据；
3. 运行 Clauset MLE + Vuong 似然比 + 块自助置信区间；
4. 把判定结果写入 `fit_result.json`。

判定结果分为 PASS、INCONCLUSIVE 或 FAIL，依据是 YAML 中声明的预注册规则。**流水线不做任何按系统调优的特殊处理**：所有判定都由同一段代码路径产出。

## 测试

```bash
PYTHONPATH=. .venv/bin/python -m pytest web/backend/tests/ -q
```

在撰写本文档时，Web 后端测试套件包含 30+ 个通过的测试，覆盖 SSE 编排器、限流 API endpoint，以及流水线结果的序列化层。

## 下一步去哪里

- 阅读 [Pipeline](../../pipeline.md) 概览，理解共享库暴露的七个核心分析操作。
- 阅读 [预注册方法论](../../methodology/pre-registration.md)，理解指数区间是如何在数据采集前就被锁死的。
- 浏览 [Papers](../../papers.md)，看 13 系统统一预印本与 CVE 证伪两份代表作。
- 试一下在线版的 [Phase Detector](https://phase.bytedance.city)——往 `/api/ask/stream` 提交一个 size 向量，看七事件 SSE 编排器实时返回判定。
