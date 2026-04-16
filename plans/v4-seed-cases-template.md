# V3 种子案例填写模板

> 这份文件给**用户**填。目标：20-30 条经典科学史跨域迁移案例，作为 V3 变形预测器的训练数据种子。
> 填好后，交给另一个 session 跑 `scripts/v4_expand_seeds.py` 扩展到 200 条。

## 为什么需要你填

LLM 扩展数据的质量取决于种子分布。你的种子案例决定了：
1. **覆盖哪些变形类型**（见 `v4-variant-types.yaml`）
2. **覆盖哪些领域对**（物理↔生物↔经济↔信息↔社会）
3. **标注的"变形序列"是否真能代表该迁移的本质**

填 20-30 条就够，不求全，但求准。

## Schema

每条种子包含以下字段：

```yaml
- id: seed-01
  source_domain: 经典力学           # 源领域
  source_concept: 简谐振子          # 源概念
  source_equation: "m·ẍ + k·x = 0"  # 源方程（纯文本，可用 unicode）
  target_domain: 电路理论            # 目标领域
  target_concept: LC 振荡回路        # 目标概念
  target_equation: "L·Q̈ + (1/C)·Q = 0"
  transformations:                  # 变形序列，按顺序
    - type: dim_subst                # 对照 v4-variant-types.yaml 的 id
      mapping: "m → L"
      reason: "惯性量类比：机械质量 ↔ 电感"
    - type: dim_subst
      mapping: "k → 1/C"
      reason: "恢复力/电容的对偶"
    - type: dim_subst
      mapping: "x → Q"
      reason: "位移 ↔ 电荷"
  historical_note: "19 世纪电磁学发展中由 Maxwell 等显式建立"
  source_refs:
    - "Maxwell 1873 — A Treatise on Electricity and Magnetism"
```

## 填写建议

**领域分布**（建议至少覆盖以下 pair）：
- [ ] 物理 ↔ 信息论（Maxwell 妖 / Landauer / Shannon 熵）
- [ ] 物理 ↔ 经济（Lotka-Volterra / 布朗运动 / 期权定价）
- [ ] 生物 ↔ 计算机（神经网络 / 遗传算法 / 免疫系统）
- [ ] 化学 ↔ 社会学（反应扩散 / 意见动力学）
- [ ] 力学 ↔ 电磁学（振荡 / 波动）
- [ ] 统计力学 ↔ 机器学习（Ising / RBM / 能量模型）
- [ ] 控制论 ↔ 生物调节（反馈 / homeostasis）

**质量标准**：
- 优先选**已被明确建立**的经典类比，不选你自己新发现的
- 源方程和目标方程要能写出来（至少是核心结构），不要只有自然语言描述
- 变形序列尽量用 `v4-variant-types.yaml` 里定义的 7 种基元；如果必须用新基元，在 `historical_note` 里标明

---

## 填写区（以下是你要填的部分）

```yaml
seeds:
  - id: seed-01
    source_domain: ""
    source_concept: ""
    source_equation: ""
    target_domain: ""
    target_concept: ""
    target_equation: ""
    transformations:
      - type: ""
        mapping: ""
        reason: ""
    historical_note: ""
    source_refs: []

  - id: seed-02
    # ...
```

> 填完后，保存为 `plans/v4-seed-cases.yaml`（去掉 `-template` 后缀）。
