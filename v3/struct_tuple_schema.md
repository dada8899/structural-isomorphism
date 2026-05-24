# StructTuple Schema v0.1

## 设计原则

1. **字段受控词表**（enum），不是自由文本——便于硬约束匹配
2. **从 description 可直接读出**，不要求 LLM 做创造性推断
3. **每个字段都有 unknown 逃生通道**，避免强行填充

## 完整 Schema

```jsonc
{
  // ==== 元信息 ====
  "phenomenon_id": "sci-001",
  "name": "放射性衰变",
  "domain": "核物理",
  
  // ==== 核心结构（必填，决定匹配） ====
  
  // 状态变量：这个系统随时间变化的是什么
  "state_vars": [
    {"symbol": "N", "meaning": "剩余原子数", "type": "count"}
  ],
  // type enum: count/concentration/position/temperature/price/population/
  //            energy/probability/pressure/velocity/field/other
  
  // 动力学族：最关键的结构分类
  "dynamics_family": "ODE1_exponential_decay",
  // enum:
  //   ODE1_linear, ODE1_exponential_growth, ODE1_exponential_decay,
  //   ODE1_logistic, ODE1_saturating,
  //   ODE2_damped_oscillation, ODE2_undamped_oscillation,
  //   DDE_delayed_feedback,
  //   PDE_reaction_diffusion, PDE_wave, PDE_diffusion,
  //   Markov_chain, Markov_decision,
  //   Percolation_threshold, Phase_transition_1st, Phase_transition_2nd,
  //   Game_theoretic_equilibrium, Self_fulfilling_prophecy,
  //   Power_law_distribution, Heavy_tail_extremal,
  //   Network_cascade, Percolation_network,
  //   Hysteresis_loop, Bistable_switch, Fold_bifurcation, Hopf_bifurcation,
  //   Stochastic_process, Random_walk,
  //   Unknown
  
  // 反馈拓扑
  "feedback_topology": "none",
  // enum: positive_loop/negative_loop/delayed_positive/delayed_negative/
  //       bistable/multistable/none/unknown
  
  // 边界/长期行为
  "boundary_behavior": "decay_to_zero",
  // enum: runaway/saturation/limit_cycle/fixed_point/decay_to_zero/
  //       fold_bifurcation/hopf_bifurcation/phase_transition/
  //       power_law_tail/unknown
  
  // 时间尺度（对数秒；用于过滤尺度差距过大的假同构）
  "timescale_log10_s": 10,
  // -6=μs, -3=ms, 0=s, 3=千秒(~15min), 6=月, 9=30年, 12=3万年
  // 若未知填 null
  
  // ==== 可选结构（用于二次验证） ====
  
  // 守恒量/不变量
  "invariants": ["mass_conservation"],
  // 常见: mass_conservation/energy_conservation/charge_conservation/
  //       number_conservation/symmetry_group/scale_invariance/
  //       power_law_exponent/other
  
  // 典型方程（自然语言形式，用于人工核验）
  "canonical_equation": "dN/dt = -λN",
  
  // 关键参数（驱动动力学的参数）
  "key_parameters": [
    {"symbol": "λ", "meaning": "衰变常数"}
  ],
  
  // 临界点/相变点
  "critical_points": [],
  
  // ==== LLM 自评 ====
  "extraction_confidence": 0.95,
  "notes": ""  // 抽取中的疑点或歧义
}
```

## Phase 0 验证重点

1. **dynamics_family 覆盖率**：50 个样本中能填的比例，unknown 比例
2. **硬约束一致性**：同一现象跑两次，dynamics_family 是否一致
3. **跨现象匹配意义**：能否用 dynamics_family 找出真正的跨域候选对
4. **schema 缺失**：50 个样本中有多少现象没法用现有 enum 表达
