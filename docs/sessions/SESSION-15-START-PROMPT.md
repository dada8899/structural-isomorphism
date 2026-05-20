# 起手:structural-isomorphism / M1.2-M1.3 实测后续

> Session #15 起手 prompt(浓缩版)。完整交接见 `SESSION-14-HANDOFF.md`,M1 实施依据见 `SESSION-13-M1-experience-fix-research.md`。

**项目**:`~/Projects/structural-isomorphism/`(repo: `dada8899/structural-isomorphism`, PUBLIC)
**上一 session**:#14。

## 当前状态

- **PR #224**(session #14, `feat/m1-ask-experience-fix`, 5 commits, 47 测试全绿):
  M1.2 fix1(`ASK_MODEL` → `:nitro`) + M1.3(本地拒答短路) + M1.2 fix4(`llm_start` 事件)+ 死代码清理 + session 文档归档
- **PR #222**(CI 修复, 全绿)、**PR #223**(首页搜索框)同样 OPEN
- main HEAD 仍是 session #12 的 commit

## 用户应已完成(起手先确认)

```bash
cd ~/Projects/structural-isomorphism && git fetch && git log --oneline origin/main -5
```

若 #222/#223/#224 已 merge:✅ 进入"下一步";若未 merge:停下提醒用户先 squash merge,不要在过期 base 上开新工作。

## 下一步分叉(看 :nitro 实测 TTFT 数据)

跑 dogfood 7 条 query(q1-q4 in-scope / q5-q7 out-of-scope),记录首 `answer_chunk` 延迟分布。

| TTFT 分布 | 走向 |
|---|---|
| in-scope ≤6s 无长尾 | **跳 M1.2 Fix2/3**,转 **M1.4 报告生成器后端**(复用 `analyze.py` query-mode + cross-judge) |
| in-scope 有 >10s 长尾 | 启 **M1.2 Fix2**(去 `json_object` 模式)+ **Fix3**(prompt 瘦身)。followups 来源推荐:答案后加 `---FOLLOWUPS---` 分隔符让 LLM 续写(单次调用、保留质量) |
| out-of-scope q5-q7 未走拒答路径 | 回看 `_evaluate_relevance` 阈值校准,可能需要降 `ASK_RELEVANCE_TOP1_MIN`(env override) |

## 工作纪律(项目级)

- `scripts/train_v2.py` 是别 session 的 in-flight 改动,**不要动**(commit 边界铁律)
- `.claude/worktrees/agent-a3e2f585dec5d670b/` 残留 worktree harness 自己回收,**不要清**
- 每个模块完成立即 commit + push(不积累)
- 显式 `git add <file>`,**禁** `git add -A` / `commit -a`

## 实测脚本骨架(可选,VPS 上跑)

```bash
# 7 条 dogfood query 跑 :nitro 后的 TTFT
for q in "SVB 怎么倒的" "团队为什么散" "用户流失原因" "传言怎么扩散" \
         "女朋友为什么生气" "1+1=?" "BTC 明天涨跌"; do
  time curl -N "https://structural.../api/ask/stream?q=$(jq -rn --arg x "$q" '$x|@uri')" \
    | head -c 200
done
```

记录:首 `answer_chunk` 出现时间 + q5-q7 是否 emit `refused:true`。

## 关键文件路径

- `docs/sessions/SESSION-14-HANDOFF.md` — 完整版交接
- `docs/sessions/SESSION-13-M1-experience-fix-research.md` — M1 实施 spec(Fix2/3 也按这个做)
- `web/backend/services/ask_orchestrator.py` — 主战场(`stream()` + `_build_refusal_payload` + `_build_prompt`)
- `web/backend/tests/test_out_of_scope.py` — M1.3 测试参考
- `web/backend/tests/test_ask_streaming.py` / `test_ask_endpoint.py` — in-scope 测试参考
