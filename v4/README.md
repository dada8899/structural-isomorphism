# V4: Universality Class Discovery Engine

> Status: **Feasibility CONFIRMED** (2026-04-15), moving to full pipeline build
> Plan: [`plans/v4-universality-class-engine.md`](../plans/v4-universality-class-engine.md)
> Findings: [`v4/results/FINDINGS-2026-04-15.md`](results/FINDINGS-2026-04-15.md)

## 一句话

把 V1/V2/V3 积累的 63 + 191 pair 级同构发现升级为**等价类/普适类地图**——从"发现 A≅B 的个别 pair"跃迁到"发现 M 个跨领域普适类，每个带共享方程 + 不变量 + 可验证预测"。

## 为什么这是正确的 V4

老 V4（`plans/v4-solver-direction.md`，已标记 DEPRECATED）试图做 retrieve+transform 求解器，在 04-14 被 Direct Opus 打穿 9/10。被打穿的真正原因不是方向错，而是**在错误的抽象层上和 Opus 竞争**。新 V4 换到更高抽象层：**把 Opus 当成 pipeline 里的一道工序**，不正面竞争。

## 目录结构

```
v4/
├── README.md                    ← 本文件
├── taxonomy/
│   └── universality_classes.yaml ← 12 个手工 seed 的物理学普适类
├── scripts/
│   ├── build_graph.py           ← Layer 1: V1/V2/V3 → 等价类图
│   └── hub_detect.py            ← Layer 2: 社区发现 + 等价类输出
├── results/
│   ├── graph.json               ← 180 节点, 143 边
│   ├── candidate_classes.jsonl  ← 23 个候选等价类
│   └── FINDINGS-2026-04-15.md   ← 可行性验证报告
└── validation/                  ← P6 实证验证工作区 (未启动)
```

## 当前状态（2026-04-15）

- [x] **P0**：物理普适类 taxonomy seed (12 类) 
- [x] **P1**：Layer 1 图构建脚本 + 运行 → 180 nodes, 143 edges
- [x] **P2**：Layer 2 hub 检测 + Louvain 社区发现 → 23 候选等价类
- [x] **可行性验证**：top-3 等价类浮现，对应 SOC / Hysteresis / Fold bifurcation 三个已知普适类，**方向坐实**
- [ ] **P3**：Layer 3 不变量提取（LLM generator + critic + taxonomy match）
- [ ] **P4**：Layer 4 可验证预测生成
- [ ] **P5**：discoveries 页面普适类视图
- [ ] **P6**：第一个实证验证（SOC × DeFi 清算）
- [ ] **P7**：论文初稿 + 投稿

## 快速复现

```bash
cd ~/Projects/structural-isomorphism
python3 v4/scripts/build_graph.py    # ~2 seconds, outputs v4/results/graph.json
python3 v4/scripts/hub_detect.py     # ~3 seconds, outputs v4/results/candidate_classes.jsonl
```

依赖：`networkx>=2.8`（Python 标准库之外只这一个）

## 前 5 个等价类（来自第一次运行）

| # | Hub 节点 | 成员数 | 领域数 | 物理学对应 |
|---|---|---|---|---|
| 1 | 清算级联的链上流动性危机 | 21 | 12 | **SOC / threshold cascade** |
| 2 | 热固性树脂凝胶点渗流相变 | 14 | 12 | **Hysteresis / Preisach** |
| 3 | 蛋白质相分离临界浓度阈值 | 10 | 8 | **Scheffer fold bifurcation** |
| 4 | 建筑结构的渐进倒塌 | 9 | 8 | **Motter-Lai network cascade** |
| 5 | 银行挤兑 | 8 | 5 | **Diamond-Dybvig self-fulfilling runs** |

详情见 [`results/FINDINGS-2026-04-15.md`](results/FINDINGS-2026-04-15.md)
