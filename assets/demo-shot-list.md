# 线上预演分镜 — 全功能对照

原则：**先列齐项目做到现在的能力，再决定每条成片拍什么。**  
Fiverr 75s / Upwork 90s 不可能全活拍；该展示的必须在 **YouTube 2–3min** 里出现（真跑或画布闪一下）。本页同时是预演 checklist。

对准 VO：[demo-video-script.md](demo-video-script.md)

**本轮只录 gig：Fiverr ≤75s + Upwork ≤90s。YouTube / 日报 / Jaeger / Insights / Marketing / Keepalive 全部跳过**（深入做完 ecom 再拍 Y）。

| 项 | 值 |
|----|-----|
| Shopify | `nans-automation-store`（master） |
| Woo | `https://woo.nanlin-portfolio.xyz`（slave） |
| SKU | `SNOWBOARD-LIQUID` |
| store_id | `e865c466-5397-418a-a1d9-21b6dc6a6a11` |
| n8n | `https://n8n.nanlin-portfolio.xyz` |
| Slack | `n8n crm workflow bot` |
| 退款门槛 | `returns_max_auto_approve_amount=50` → **退 >$50 才 Slack 人工审核** |

**F** = Fiverr ≤75s · **U** = Upwork ≤90s · **Y** = YouTube 2–3 min

图例：**活拍** = 真操作 + 结果入镜 · **闪** = n8n 画布 / execution / Slack 已有卡 3–8s · **不入镜** = 预演可跑，成片不讲

---

## 1. 全功能盘点（P0–P3b）

### 横切（13 条工作流共用，成片用一眼证明）

| 能力 | 证明什么 | F | U | Y |
|------|----------|---|---|---|
| 共享 n8n + sidecar + `ecom_postgres` | 不是一张 Google Sheet 玩具 | 闪 Ingest 画布 | 闪 | 闪架构 |
| HMAC / webhook 接入 | Shopify + Woo 进同一条 Ingest | 隐含 | 闪 Woo 路径 | 闪双 webhook |
| `correlation_id` | 一张 Slack 卡能追到 n8n / Jaeger | 卡上有 id | 同 | **活拍** Jaeger 搜 id |
| `mode=production` 门控 | 回写/邮件/摘要可关 | 一句 VO | 一句 | 闪 config 或口播 |
| 节点级 error handler + 全局 Error Handler | 第三方挂了不吞错 | 不入镜 | 不入镜 | **闪** Error Handler 画布 |
| 生成器 JSON | 模板可交付 | CTA 列表 | CTA | CTA |

### P1 信任（买家怕亏钱的环）

| 能力 | 工作流 | 线上怎么证 | F | U | Y |
|------|--------|------------|---|---|---|
| Shopify 下单 → PG | Ingest → **Order Tracker** | Create order（带邮箱、Mark paid） | **活拍** | **活拍** | **活拍** |
| 正常单无 Slack | Order Tracker | execution `ok`，频道无 anomaly | **活拍** | **活拍** | **活拍** |
| 退款规则 → 老板可见 | **Returns Automation** | 同单 Refund **>$50** | **活拍** Slack | **活拍** | **活拍** |
| 订单异常告警 | Order Tracker Slack | 预演不要故意造（无邮箱才告警） | 不入镜 | 不入镜 | 口播「anomaly 另有卡」 |
| 库存 master/slave | **Inventory Sync** | 只改 Shopify `SNOWBOARD-LIQUID` | 时间不够可砍 | **活拍** | **活拍** |
| P3b 库存 live 回写 Woo | Inventory Sync | Slack `applied` + Woo 数量对齐 | 可 8s 闪 | **活拍** | **活拍** |
| Woo ingest 不二次 Sync | Ingest `dispatch.inventory=false` | 回写后不应连环刷卡 | 预演观察 | 预演观察 | 口播一句 |

### P2 智能（wow，短片只闪）

| 能力 | 工作流 | 线上怎么证 | F | U | Y |
|------|--------|------------|---|---|---|
| 竞品抓取 + LLM parse | **Competitor Price Crawl** | Execute Workflow 或已有 snapshot | 不入镜 | 闪画布 | **闪** execution |
| 定价建议 | **Pricing Engine** | Execute → Slack Approve/Reject | 可选 3s 按钮 | **活拍卡** | **活拍卡** |
| Slack 人审（不自动改价） | **Slack Actions** | 预演 **Reject**（Approve 会改店面价） | 不点 | **Reject** | **Reject**（录 U 可另拍 Approve 再改回） |
| Langfuse 定价 trace | sidecar | tag `ecom-workflow` | 不入镜 | 闪 | **闪** |
| RFM / 流失 | **Customer Insights** | Execute，看 sidecar/PG | 不入镜 | 不入镜 | **闪** execution 成功 |
| 弃购序列 + Resend | **Marketing Orchestrator** | Execute；production 才真发信 | 不入镜 | 不入镜 | **闪** + 口播门控（不要真发客户邮件） |

### P3 运维

| 能力 | 工作流 | 线上怎么证 | F | U | Y |
|------|--------|------------|---|---|---|
| 日报 | **Daily Summary** | Execute → Slack | 不入镜 | 不入镜 | **活拍**（已通可只确认有卡） |
| 周报 | **Weekly Summary** | Execute 或口播「同门控」 | 不入镜 | 不入镜 | **闪** 画布（不必等周一） |
| Keepalive | **Health Keepalive** | Execute：PG + Shopify/Woo ping | 不入镜 | 不入镜 | **闪** execution |

---

## 2. 成片必须出现 vs 预演必跑

| | 预演（你自己走一遍） | 成片入镜 |
|--|----------------------|----------|
| 下单 + Order Tracker | 必跑 | F U Y **必须** |
| 退 >$50 + Returns Slack | 必跑 | F U Y **必须**（F 的 money shot） |
| 库存漂移 + Woo 回写 | 必跑（已通可缩短） | U Y **必须**；F 超时可砍 |
| Pricing Slack 卡 | 必跑到出卡 | U Y **必须**；F 可选 3s |
| Daily Summary | 必跑一次确认 | **仅 Y** |
| Crawl / Insights / Marketing / Keepalive / Weekly / Error Handler | Y 各闪一次即可 | **仅 Y** |
| 真发 Resend、故意打挂 Error Handler、无邮箱 anomaly | 不要为成片制造 | 不入镜 |

---

## 3. 铁律

- 本地 n8n **全停**；Woo webhook 只留线上。
- 下单必须带 **顾客邮箱**（paid 无邮箱会走 anomaly，不是主线）。
- 正常 paid **不发 Slack**；镜头 = Shopify 订单 + n8n Order Tracker 绿。
- 退款 **>$50** 才有 `↩️ Large refund processed`（店员已退，老板可点进订单）。
- 下单/退款可能带一张库存卡，记下即可，不算失败。
- 库存只改 `SNOWBOARD-LIQUID`；期望 **一张**真 SKU、`applied`，不要 `ext-*`。
- 定价预演默认 **Reject**。密钥不入镜。

---

## 4. 窗口

1. Shopify Orders  
2. Shopify 该 SKU 库存  
3. Woo 同一 SKU 库存  
4. Slack  
5. n8n Executions（Ingest / Order Tracker / Returns / Inventory Sync；Y 再开 Pricing、Daily、Insights…）  
6. Y：Jaeger、Langfuse、13 条 workflow 列表  

---

## 5. 预演走位（按这个点，覆盖全部该展示的）

预检：本地停；Ingest / Order Tracker / Returns / Inventory Sync Active；记下库存 Shopify `____` / Woo `____`；测试邮箱准备好。

### A. P1 下单 + 退货（F/U/Y 成片主线）

1. Shopify **Create order** → `SNOWBOARD-LIQUID` ×1 → 填 email → **Mark as paid**  
2. n8n：Ingest `dispatch.order` → **Order Tracker** `ok` / `paid`  
3. 频道 **没有** `⚠️ Order anomaly`  
4. 同单 **Refund** 整单（>$50）  
5. Slack `↩️ Large refund processed` · `manual_review`  
6. n8n **Returns Automation** 同一 `correlation_id`  

失败则停：没 dispatch order；`order_not_found`；退 ≤$50 却在等 Slack。

### B. P1/P3b 库存回写（U/Y 必入镜；F 可只预演）

7. 只改 Shopify 库存 ±5  
8. Slack **一张** `SNOWBOARD-LIQUID` · `applied`  
9. Woo 数量对齐  

失败则停：`ext-*`、两张幽灵卡、Woo 不动。

### C. P2 定价 wow（U/Y 入镜；F 可跳）

10. 执行 **Pricing Engine**（可选先跑 **Competitor Crawl**）  
11. Slack Approve/Reject 卡 → **Reject**  
12. Y：Langfuse 打开这次 generation  

### D. P2/P3 其余（仅 Y 闪，预演仍要点一次）

13. **Customer Insights** Execute → 成功即可  
14. **Marketing Orchestrator** Execute → 确认 `skipped` 或门控，**不要**对真人发信  
15. **Daily Summary** → Slack 日报（Y 活拍）  
16. **Weekly Summary** 打开画布闪一下（不必等到 Cron）  
17. **Health Keepalive** Execute → PG/渠道 ping ok  
18. **Error Handler** 打开画布 3s  
19. Jaeger 用 **退货卡** 上的 correlation_id 搜 ingest → returns  

### E. 回滚

- 演示单保持 refunded  
- 库存两边一致  
- 误 Approve 则改回价格  

---

## 6. 本轮成片（gig only）

同一条预演剪两刀。Y 以后再拍。

| 成片 | 入镜顺序 | 必须看到 | 不要拍 |
|------|----------|----------|--------|
| **F 75s** | Hook 订单 → Tracker 绿 → Refund → Returns Slack → CTA | 真单 + `Large refund processed` 卡 | 库存、定价、架构、OBS |
| **U 90s** | F + 改库存 → 一张 `applied` 卡 → Woo 对齐 + Pricing 卡 **Reject** + 3s 架构 | F + 回写闭环 + 人审定价 | 日报、Insights、邮件、Jaeger |

---

## 7. 预演记录

| 项 | 值 |
|----|-----|
| Shopify 订单号 | |
| Order Tracker correlation | |
| 退款金额（须 >50） | |
| 退货 Slack | 有 / 无 |
| Returns correlation | |
| 库存卡（一张真 SKU / applied） | |
| Pricing 卡 + Reject | |
| Daily Slack | |
| Insights / Marketing / Keepalive | 闪过 / 失败 |
| Jaeger 能搜到退货 id | |
| 回滚 | |
