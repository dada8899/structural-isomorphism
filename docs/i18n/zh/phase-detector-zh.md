# Phase Detector

[English](../../phase-detector.md) | **简体中文**

Phase Detector（项目代号 **D1**）将共享流水线封装成一个可查询的服务。目标用户是希望把一个 size 向量或时间序列扔进托管 endpoint，就能拿回判定结果（PASS / INCONCLUSIVE / FAIL）、带置信区间的拟合指数、以及替代分布拟合的诊断比较——**而无需在本地搭起完整 Python 流水线**的研究人员和工程师。

## 架构

Phase Detector 是 `web/backend/` 下的一个薄层 FastAPI 服务，封装了共享分析库。请求路径是：

```
client  ──POST /api/ask──▶  编排器  ──▶  soc_pipeline.fit_*
                                │
                                └──▶  vuong_lr  ──▶  判定  ──▶  JSON
```

对于耗时较长的拟合，编排器会向客户端流式推送 7 个 Server-Sent Events（即"7 事件 SSE 编排器"）：

1. `task_received` — 请求被接收。
2. `data_ingested` — size 向量已解析；基础合法性校验通过。
3. `xmin_search_start` — Clauset KS 最优 $x_{\mathrm{min}}$ 搜索开始。
4. `xmin_found` — 搜索收敛；$x_{\mathrm{min}}$ 上报。
5. `bootstrap_running` — 块自助法正在运行，附带进度分数。
6. `vuong_complete` — 似然比检验完成。
7. `verdict` — 最终 PASS / INCONCLUSIVE / FAIL，附完整结果表。

SSE 设计与 Perplexity 风格答案流式器使用的是同一套；事件 schema 的权威实现见 `web/backend/services/ask_orchestrator.py`。

## 用法

托管 endpoint 按 tier 限流。免费 tier 接受 size 向量长度 $n \leq 5000$；付费 tier 接受 $n \leq 50000$，并把 bootstrap 迭代次数作为请求参数暴露出来。

### 流式 endpoint

```bash
curl -N -X POST https://api.structural-isomorphism.org/api/ask/stream \
    -H "Content-Type: application/json" \
    -d '{
        "sizes": [3, 5, 8, 13, 21, 34, 55, 89, 144, 233],
        "discrete": true,
        "alternatives": ["lognormal", "exponential"]
    }'
```

响应是一个 `event-stream`，按上述 7 个事件顺序推送。

### 同步 endpoint

对于较小输入和快速测试，同步 endpoint 一次返回完整结果表：

```bash
curl -X POST https://api.structural-isomorphism.org/api/ask \
    -H "Content-Type: application/json" \
    -d '{
        "sizes": [3, 5, 8, 13, 21, 34, 55, 89, 144, 233],
        "discrete": true
    }'
```

```json
{
    "verdict": "INCONCLUSIVE",
    "alpha": 1.92,
    "ci": [1.55, 2.31],
    "x_min": 8,
    "n_tail": 7,
    "vuong": {
        "lognormal": {"R": -0.41, "p": 0.68},
        "exponential": {"R": 0.34, "p": 0.73}
    },
    "comment": "n_tail < 50; Vuong test 在 Clauset 2009 §6.3 中已记载功效有限。"
}
```

## Phase Detector 不做的事

- **它不替你预注册预测**。如果你需要预注册判定，请按 `v4/preregistration/` 中的 schema 写一个 YAML，并在拉取数据**之前**提交。然后 Phase Detector 会消费这个 YAML；参见 [预注册方法论](../../methodology/pre-registration.md)。
- **它不裁决普适类归属**。一个系统是否属于某个普适类，需要的不仅是一条幂律尾巴——参见 [跨判评审集成](../../methodology/cross-judge.md) 中分类法 review 的流程，Phase Detector 明确把这件事委托出去。

## 自托管

Phase Detector 是开源的。本地运行方式：

```bash
cd web/backend
uvicorn main:app --reload --port 8000
```

SSE endpoint 即可通过 `http://localhost:8000/api/ask/stream` 访问。
