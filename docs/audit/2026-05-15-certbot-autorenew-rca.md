# Certbot Auto-Renew Failure — Root Cause Analysis

**Date**: 2026-05-15
**Severity**: P0 (3 prod sites had expired certs: bytedance.city / cc / monitor — manually force-renewed earlier today)
**Status**: Root cause confirmed + fix applied + auto-renew now active
**Owner**: wanqh (B 机 session #9 follow-up)

---

## 1. Root Cause（一句话）

**`certbot-renew.timer` 从未被 `systemctl enable`**。VPS 上 34 个 Let's Encrypt 证书完全没有任何自动续期机制在跑——既没有 systemd timer，也没有 cron job。所有续期一直是手动触发的，迟早撞过期墙。

---

## 2. 证据链

### 2.1 Timer 状态（修复前）

```
$ systemctl list-unit-files | grep -i cert
certbot-renew.service       static          -
certbot-renew.timer         disabled        disabled    ← 关键
```

- timer unit 由 `certbot-2.8.0-4.oc9.noarch` 包提供（dnf 装的，不是 snap）
- 包默认 preset = `disabled`（OpenCloudOS 9 上游策略）
- 安装时 dnf 不会自动 enable timer（与 Ubuntu 的 snap 装法不同——snap 自带 systemd-timer wrapper 默认 active）

### 2.2 Cron 也空

```
$ ls /etc/cron.d/certbot         → No such file
$ ls /etc/cron.daily/certbot     → No such file
$ crontab -l | grep -i 'cert|renew|letsencrypt'   → (空)
```

无 systemd timer + 无 cron = 完全没有自动续期路径。

### 2.3 Journal 零历史

```
$ journalctl -u certbot-renew.timer -u certbot-renew.service --since '30 days ago'
-- No entries --
```

证明 timer 自系统启动以来从未触发过（不是触发了失败，是从未触发）。

### 2.4 LE 日志佐证

`/var/log/letsencrypt/letsencrypt.log` 历史 rotate（每 6-7 天一段）说明 certbot 在历史上确实跑过，但全是手动 `certbot renew` / `certbot --nginx -d ...` 命令触发——不是 timer。

---

## 3. 历史时间线

| 日期 | 事件 |
|---|---|
| 2026-02-21 起 | letsencrypt.log 开始 rotate，证明每周仍有人手动 `certbot renew` |
| 2026-05-13 13:20 | VPS 重启（crond active since 此时刻）；timer 仍 disabled，无人注意 |
| 2026-05-15 之前 | bytedance.city / cc / monitor 3 个证书走到过期窗口（< 30 天） |
| 2026-05-15 11:48 | 主 session 手动 `certbot renew --force-renewal` 救活 3 个证书 |
| 2026-05-15 11:53 | 本 session 执行 `systemctl enable --now certbot-renew.timer`，timer 上线 |
| 2026-05-15 16:51 | 首次自动触发预定时间（CST） |

**关键观察**：手动续期文化已经维持了至少 3 个月，靠人肉记忆 / 收到 LE 即将过期邮件触发。这次三个域名同时过期说明：
- 邮件提醒没收到 / 没看到 / LE 邮件可能进了 spam
- 没有任何监控告警在证书 < 7 天时报警
- 人肉触发存在系统性遗忘风险

---

## 4. 当前修复状态

### 已完成（2026-05-15 11:53 CST）

```bash
ssh vps "systemctl enable --now certbot-renew.timer"
# Created symlink /etc/systemd/system/timers.target.wants/certbot-renew.timer
#                  → /usr/lib/systemd/system/certbot-renew.timer

ssh vps "systemctl status certbot-renew.timer"
# ● certbot-renew.timer
#      Loaded: loaded (...; enabled; preset: disabled)    ← enabled ✓
#      Active: active (waiting) since 2026-05-15 11:53:35 CST  ← active ✓
#     Trigger: 2026-05-15 16:51:41 CST                    ← 4h 58min later
```

Timer schedule（来自 `/usr/lib/systemd/system/certbot-renew.timer`）：
- `OnCalendar=*-*-* 00/12:00:00` → 每天 00:00 和 12:00
- `RandomizedDelaySec=12hours` → 实际触发在 0-12h 随机偏移内（避开 LE 同步雪崩）
- `Persistent=true` → 关机错过的触发，开机后补跑一次

每天会跑 2 次 `certbot renew`，每证书过期 30 天内自动续。

### 待验证（dry-run 进行中）

```bash
ssh vps "certbot renew --dry-run --no-random-sleep-on-renew"
```

dry-run 跨 34 个证书走完整 LE staging 流程，验证：
- 所有 renewal config 文件未损坏
- nginx hook 正常
- 没有 SAN 域名 DNS 错误（multi-domain cert 如果某 SAN 指错 IP 会整 cert renew 失败）

dry-run 完成后会在 LE 日志看到 "Congratulations, all simulated renewals succeeded" 或失败列表。

---

## 5. 防再发措施（系统性根因修复）

按 CLAUDE.md「四层分析」第 3 层（系统性根因）+ 第 4 层（全局影响评估）思路：

### M1. 监控层补告警（最高优先级）

**问题**：当前无任何证书过期告警，靠 LE 邮件 + 人脑提醒。

**方案**：
- 在 `monitor.bytedance.city`（AI Monitor）的 Projects 区为每个站点增加证书过期检测：调 `openssl s_client -servername <d> -connect <d>:443 | openssl x509 -noout -enddate`
- 剩余 < 14 天 → 黄色告警；< 7 天 → 红色 + 企微 Bot push
- 实施位置：`/root/Projects/ai-monitor/ai-monitor.py` 的 site check 区
- 工作量：~30min

### M2. cc-daemon 增加 weekly self-check（次优先级）

每周一 09:00 跑 `systemctl is-enabled certbot-renew.timer && systemctl is-active certbot-renew.timer`，二者必须都返回 enabled/active，否则飞书 Bot 报警。

**为什么**：systemd timer 可能被无意 disable（升级 / 误操作），需要持续校验"自动机制本身仍在跑"。

### M3. 新 VPS 部署 checklist 加一条（防未来重装）

在 `~/Vault/重要信息/` 或部署 skill 中加入：

> VPS 装完 certbot 包后，必须 `systemctl enable --now certbot-renew.timer` 并 `systemctl list-timers | grep certbot` 验证。

避免下次重装服务器再踩同样的坑。

### M4. dry-run 纳入月度运维（可选，低优先级）

每月 1 号自动跑 `certbot renew --dry-run` 探测续期路径健康（renewal conf 损坏 / nginx 配置变动导致 hook 失败 / DNS 改了 SAN 失效等）。
集成位置：cc-daemon 调度。

### 全局影响评估

- M1（监控告警）：纯增量，无副作用
- M2（systemd self-check）：依赖 cc-daemon 已经在跑，注入一条 weekly task 即可，无破坏面
- M3（checklist）：文档更新，0 风险
- M4（月度 dry-run）：dry-run 走 LE staging 不消耗真 quota，但跨 34 域 + nginx reload 会有 1-2 分钟轻微负载，挑业务低峰时段（如周日 04:00）执行

---

## 6. 经验沉淀（写入 Memory）

候选 memory entries：

1. **knowledge_certbot_dnf_timer_disabled_default.md**: OpenCloudOS 9 dnf 装 certbot 包后 timer 默认 disabled，必须手动 enable；与 Ubuntu snap 装法行为不同
2. **feedback_no_monitoring_no_alerts.md**: 任何"长期靠人肉记忆触发的运维动作"都是定时炸弹，必须有自动告警兜底（这次 3 cert 同时过期就是这种炸弹引爆）
3. **knowledge_systemd_timer_enable_vs_start.md**: `systemctl enable` 注册开机自启 + `--now` 立即激活，二者要一起才能让 timer 持续运行

---

## 7. 回滚预案

如果 timer 引入意外问题（极不可能，但留预案）：

```bash
ssh vps "systemctl disable --now certbot-renew.timer"
# 回到原始状态，再用临时 cron 救场：
ssh vps 'echo "0 4 * * * /usr/bin/certbot renew --quiet" | crontab -'
```

---

## Appendix A: 验证命令

```bash
# Timer 状态
ssh vps "systemctl is-enabled certbot-renew.timer && systemctl is-active certbot-renew.timer"

# 下次触发时间
ssh vps "systemctl list-timers certbot-renew.timer"

# 历史触发日志
ssh vps "journalctl -u certbot-renew.timer -u certbot-renew.service --since '7 days ago'"

# 证书过期速查
ssh vps "for d in bytedance.city cc.bytedance.city monitor.bytedance.city; do echo -n \"\$d: \"; echo | openssl s_client -servername \$d -connect \$d:443 2>/dev/null | openssl x509 -noout -enddate; done"
```

## Appendix B: 完整证书清单（34 个）

见 `ls /etc/letsencrypt/renewal/` 输出，覆盖所有 bytedance.city 子域 + structural-isomorphism beta 子域 + routify 子域 + jbd/fjd/renai 等。
