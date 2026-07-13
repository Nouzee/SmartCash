# Smart Money Microstructure

一个独立的港股高频“聪明钱”研究项目。核心不是 CCASS 或 Hitchhike 日频信号，而是：

```text
hktransaction + l2thousand + broker/participant as-of mapping
                         ↓
事件时间规范化与因果状态机
                         ↓
主动资金流 + 盘口压力 + 价格响应 + 流动性恢复
                         ↓
SmartMoneyScore / FlowPriceState
                         ↓
10s / 30s / 60s / 300s markout 与 shock outcome
```

项目是 research prototype，不修改 Thousand、Lemnis、Hephaestus 或生产网页。

## Peter Gomber 思路如何迁移

Gomber 等人的 *Don’t Stop Me Now!* 研究已经触发的 Xetra volatility interruption，先用事件后价格趋势和市场质量构造 ex-post 标签，再只用事件前盘口、交易和上下文预测哪些中断可能不必要。

本项目迁移的是这套研究纪律：

- 不把单次价格跳动自动解释成信息；
- 同时检查价格趋势、spread、depth、volatility 和消息活跃度；
- 将 `persistent / dampened / reversed` 作为未来 outcome；
- 实时分数只使用 `t ≤ as_of`；
- 数据不完整或置信度不足时保守不放行。

没有迁移 Xetra 的两分钟窗口、12 clusters、50% 阈值或论文模型性能。broker identity、主动净流、skill prior、absorption 都是本项目的新假设。详见 [Peter Gomber 迁移说明](docs/peter-gomber-migration.md)。

## 数据事实边界

- `hktransaction` 是唯一成交方向与成交金额来源。
- 方向流使用 `activeBrokerNo`；被动 `brokerNo` 仅留作审计，缺失 active broker 时不会回退。
- raw `dir` 必须显式选择解释契约。厂商文档口径是 `1=主动卖、2=主动买`；Thousand 当前 legacy exporter 与其相反，真实研究前必须用独立 tape 核验。
- `l2thousand` 是盘口来源。
- `broker_queue/hkbrokerqueueex` 会被 replay CLI 明确拒绝，不能伪装成成交或 L2 order book。
- snapshot-based depth increase 只叫 `refill_proxy`；没有 hkorder 增删消息时，不声称识别了真实补单或撤单。
- broker 与 participant 分层聚合；full name、display name、effective dates 都保留。
- skill score 必须是用已经成熟的历史 markout、按 as-of 日期估计的先验，不能用当前或未来 outcome。
- 实时会话迟于开盘启动时 `complete=false`；只有显式 historical replay 可以 `replayed=true`。

## 实时因子

### 盘口压力

```text
book_imbalance_L = (Σ bid_size_L - Σ ask_size_L)
                   / (Σ bid_size_L + Σ ask_size_L)

microprice = (ask1 × bid_size1 + bid1 × ask_size1)
             / (bid_size1 + ask_size1)

microprice_edge_bps = (microprice / midpoint - 1) × 10,000
```

输出 L1/L2/L5 imbalance、L1/L5 depth、spread、microprice edge。

### Order Flow Imbalance

L1 OFI 使用相邻 full snapshots 的最优价/量变化，遵循 price improvement、same-price size change 和 price deterioration 的符号规则，再除以前后平均 L1 depth。它是盘口事件流，不是 broker queue 统计。

### 流动性与恢复

- `realized_mid_volatility_60s`：截至 `as_of` 的 midpoint returns 波动；
- `book_update_count_10s`：过去十秒 L2 snapshot 数；
- `depth_recovery_ratio_60s`：当前 L1 depth 在过去 60 秒局部 min/max 的位置；
- `spread_recovery_ratio_60s`：价差从过去 60 秒局部高点收窄的比例；
- `bid/ask_refill_proxy`：仅当最优价不变时的正向 size increment；
- `liquidity_stress`：相对窗口起点的 spread 恶化与 depth 枯竭。

### 主动身份流

每个快照输出 10/30/60/300 秒窗口：

```text
signed_flow_ratio = (active buy turnover - active sell turnover)
                    / directional turnover

skill_weighted_flow = Σ(skill_broker × signed turnover_broker)
                      / directional turnover

top_broker_net_concentration = max(|broker net|) / directional turnover
```

neutral turnover 不进入方向分母，单独报告 `neutral_share`；未映射成交降低 mapping coverage。

### Flow–Price 状态

对称处理买卖方向：

- `confirmed`：60 秒主动流较强，midpoint 至少同向移动 5bp；
- `absorption_candidate`：主动流较强但价格基本走平，只进入研究 cohort；
- `conflict`：价格与主动流反向至少 5bp；
- `neutral`：主动方向不足。

只有 `confirmed`、高 confidence、低 liquidity stress 的信号才可能 `trade_eligible=true`。absorption 不预设为好事，必须看未来 markout。

### SmartMoneyScore v0

透明的冻结规则：

```text
0.25 × L1 imbalance
+ 0.20 × tanh(microprice_edge_bps / 2)
+ 0.20 × clipped normalized OFI
+ 0.20 × signed_flow_ratio_60s
+ 0.15 × skill_weighted_flow_60s
```

这是可消融 baseline，不是训练完成的最优权重。真实权重只能在 walk-forward train/validation 上拟合。

## Shock sustainability

项目自定义 shock（不是论文的 Xetra interruption）：

```text
abs(return_t) > max(k × past_volatility, minimum_return_floor)
```

`ShockDetector` 只读取 detection time 之前的数据。`ShockLabeler` 等未来窗口结束后，按 post-shock 方向和相对 shock 幅度标记：

- `persistent`：同向且未减速超过阈值；
- `dampened`：仍同向但明显减速；
- `reversed`：反向。

spread widening 和 depth depletion 是 outcome 的市场质量维度。未来路径不会回写实时特征。

## 项目结构

```text
src/smart_money/
  contracts.py   # 事件、特征、会话契约
  xtquant.py     # hktransaction / l2thousand 规范化
  identity.py    # broker / participant as-of mapping 与 skill prior
  engine.py      # 因果事件状态机与 SmartMoneyScore
  shocks.py      # ex-ante shock detector / ex-post outcome labeler
  replay.py      # event-time replay 与未来 markout
  cli.py         # 真实 JSONL replay
  demo.py        # synthetic sanity replay
tests/           # 公共接口行为测试
docs/            # 研究说明与接入计划
```

## 运行 synthetic demo

```bash
cd /home/zrliu/smart-money
PYTHONPATH=src /opt/conda/envs/research/bin/python -m smart_money.demo \
  --output-dir artifacts/demo \
  --duration-seconds 720 \
  --seed 7
```

输出：

- `feature_snapshots.csv`：严格实时字段，`uses_future_data=false`；
- `markout_labels.csv`：10/30/60/300 秒未来标签；
- `backtest_summary.csv`：按 horizon 与 flow-price state 分组；
- `shock_events.csv` / `shock_outcomes.csv`；
- `manifest.json`：明确 `synthetic_demo`、禁止 empirical claim。

## 运行真实事件 replay

JSONL 每行：

```json
{"kind":"hktransaction","symbol":"00700.HK","payload":{"time":1767576601000,"price":400.0,"volume":1000,"dir":2,"activeBrokerNo":101,"brokerNo":9999}}
{"kind":"l2thousand","symbol":"00700.HK","payload":{"time":1767576601000,"bidPrice":[399.8],"bidVolume":[10000],"askPrice":[400.0],"askVolume":[8000]}}
```

执行：

```bash
PYTHONPATH=src /opt/conda/envs/research/bin/python -m smart_money.cli \
  --events-jsonl /path/to/events.jsonl \
  --identity-csv /path/to/identity_asof.csv \
  --output-dir artifacts/real-replay \
  --direction-convention xtquant_vendor_doc_dir_1_sell_2_buy \
  --expected-open 2026-01-05T09:30:00+08:00 \
  --session-start 2026-01-05T09:30:00+08:00 \
  --replayed
```

一次 replay 只接受一个交易日。`--direction-convention` 是必填项，避免静默方向错误。

## 测试

```bash
cd /home/zrliu/smart-money
/opt/conda/envs/research/bin/python -m pytest -q
```

## 与现有项目的关系

- **Thousand**：数据采集与持久化。需要补齐 `l2thousand` 历史落盘，并修复/核验 side contract。
- **Lemnis**：当前明确不支持 tick/order-book 微结构撮合；后续可消费冻结后的 1s/5s feature sidecar，用它的调度、订单、账本和 replay 做组合级验证。
- **Hephaestus**：用于 Research Ledger、假设注册、成本/markout 审计、DecisionEngine 和 dossier；不采用其现有 queue simulator 作为成交真值。

## 当前限制

- full-snapshot 原型，不重建逐订单 price-time priority；
- 没有 hkorder 时不能测真实 add/cancel/refill；
- 没有自己的真实成交，不能验证 queue position 或 fill probability；
- synthetic 结果只验证管线，不证明 alpha；
- 还没有在线学习 broker skill，当前只消费显式历史 prior；
- 未加入费用、延迟、冲击和实际撮合，不能把 markout 当净策略收益。
