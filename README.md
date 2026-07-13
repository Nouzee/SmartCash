# SmartCash Microstructure

SmartCash 是一个独立的港股方向性高频“聪明钱”研究项目。核心不是 CCASS 或 Hitchhike 日频信号，而是：

```text
Vault dataset → Beast canonical hktransaction/l2thousand transform
             + independent seat/broker-entity as-of mapping
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
- 历史/研究数据从冻结的 Vault dataset 读取，由 Beast 脚本生成 SmartCash 规范事件；manifest 必须绑定 Vault dataset/version/hash、Beast commit/config hash 与 artifact hash。
- 方向流使用 `activeBrokerNo`；被动 `brokerNo` 仅留作审计，缺失 active broker 时不会回退。
- raw `dir` 必须显式选择解释契约。厂商文档口径是 `1=主动卖、2=主动买`；Thousand 当前 legacy exporter 与其相反，真实研究前必须用独立 tape 核验。
- `l2thousand` 是盘口来源。
- `broker_queue/hkbrokerqueueex` 会被 replay CLI 明确拒绝，不能伪装成成交或 L2 order book。
- snapshot-based depth increase 只叫 `refill_proxy`；没有 hkorder 增删消息时，不声称识别了真实补单或撤单。
- seat 与 broker entity 是嵌套身份视图，不重复计分；full name、display name、provenance、effective dates 都保留。
- SmartCash 不继承 CCASS participant 口径；可复用的 CCASS ID 只作为带来源的外部别名，CCASS holdings/T+2 不进入高频因子。
- skill score 必须是用已经成熟的历史 markout、按 as-of 日期估计的先验，不能用当前或未来 outcome。
- `replayed=true` 只描述数据模式，不自动证明完整。CLI 只有在显式声明 coverage、开盘首帧及时、L2 最大间隔不超阈值，且逐笔 sequence 连续、无重复 ID、无文件乱序时才接受 coverage；特征分别报告 `complete_60s`、`complete_300s`，全量 `complete=true` 要求 300 秒热身。

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

top_seat_net_concentration = max(|seat net|) / directional turnover
top_broker_entity_net_concentration = max(|broker-entity net|) / directional turnover
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

`ShockDetector` 只读取 detection time 之前的数据。`ShockLabeler` 等未来窗口结束后，按 post-shock 方向、相对 shock 幅度、路径反转、signed-flow persistence 和 order-flow decay 标记：

- `persistent`：同向且未减速超过阈值；
- `dampened`：仍同向但明显减速；
- `reversed`：反向。

spread widening 和 depth depletion 是 outcome 的市场质量维度。超过目标时点 2 秒才出现的 endpoint 会被拒绝，未来路径不会回写实时特征。

## 项目结构

```text
src/smartcash/
  contracts.py   # 事件、特征、会话契约
  candidates.py  # 候选冲击、确认、过期、去重与 re-arm
  xtquant.py     # hktransaction / l2thousand 规范化
  identity.py    # 独立 seat / broker-entity as-of mapping 与 skill prior
  engine.py      # 因果事件状态机与 SmartMoneyScore
  execution.py   # taker-only Protected IOC 与逐标的交易规则
  shocks.py      # ex-ante shock detector / ex-post outcome labeler
  replay.py      # event-time replay 与未来 markout
  walk_forward.py # 60/1/20/1/20 date-aligned folds
  integrations/  # Lemnis 公共订单桥与 Parquet snapshot sidecar
                 # Vault → Beast artifact 血缘契约
  reporting.py   # 显式 dataset mode 的 CSV/诊断输出
  data_quality.py # Phase 0 逐标的 tape/L2/身份覆盖验收
  cli.py         # 真实 JSONL replay
  demo.py        # synthetic sanity replay
tests/           # 公共接口行为测试
docs/            # 研究说明与接入计划
```

## 运行 synthetic demo

```bash
cd /home/zrliu/smartcash
PYTHONPATH=src /opt/conda/envs/research/bin/python -m smartcash.demo \
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
{"kind":"hktransaction","symbol":"00700.HK","captured_at":"2026-01-05T09:30:01.010+08:00","payload":{"time":1767576601000,"price":400.0,"volume":1000,"dir":2,"activeBrokerNo":101,"brokerNo":9999,"tradeID":"00700-1","seq":1}}
{"kind":"l2thousand","symbol":"00700.HK","captured_at":"2026-01-05T09:30:01.012+08:00","payload":{"time":1767576601000,"bidPrice":[399.8],"bidVolume":[10000],"askPrice":[400.0],"askVolume":[8000]}}
```

逐笔完整性不能由“文件里 sequence 连续”推断。采集器还要独立写出不可由 replay 补造的 capture evidence JSON：顶层固定 `source=xtquant.hktransaction`、`trade_date`，并以 `events_sha256` 绑定原始 JSONL；每个 expected symbol 记录真实 subscription ACK、`subscribed_at`、从开盘到收盘不超过 60 秒间隔的 monitor heartbeat，以及非负 JSON 整数 `dropped_callback_count`。午休不计 heartbeat gap。缺文件、哈希不匹配、缺股票、首尾不覆盖、乱序、gap 超限或丢包非零都会令该股票失败。

执行：

```bash
PYTHONPATH=src /opt/conda/envs/research/bin/python -m smartcash.cli \
  --events-jsonl /path/to/events.jsonl \
  --vault-beast-manifest /path/to/vault_beast_manifest.json \
  --identity-csv /path/to/identity_asof.csv \
  --output-dir artifacts/real-replay \
  --dataset-mode historical_replay \
  --direction-convention xtquant_vendor_doc_dir_1_sell_2_buy \
  --expected-open 2026-01-05T09:30:00+08:00 \
  --expected-end 2026-01-05T16:00:00+08:00 \
  --expected-symbol 00700.HK \
  --session-start 2026-01-05T09:30:00+08:00 \
  --trade-capture-evidence-file /path/to/trade_capture_evidence.json \
  --side-verification-file /path/to/side-verification.json \
  --coverage-complete
```

一次 replay 只接受一个交易日，事件类型只接受明确的 `hktransaction` / `l2thousand`，不接受通用 tick/L2 别名后再重标来源。`--expected-symbol` 必须按预期 universe 逐只重复传入；完全没有事件的股票也会产生失败的质量行。`--dataset-mode` 与 `--direction-convention` 都是必填项。

Phase 0 对逐笔和 L2 分别检查 exchange event time、`captured_at` 覆盖、负延迟、回调乱序和过期到达；逐笔另查 sequence、重复 trade ID 与独立整日 capture envelope，L2 另查 crossed/locked、首尾和连续 gap。L2 最大 gap 与 callback 延迟阈值只能收紧，分别不能放宽到 5 秒和 1,000 毫秒以上。交易时段按冻结的 2025–2026 HKEX 开市日、休市日与半日市表校验，且时间戳必须为香港 `+08:00`；普通日为 09:30–12:00、13:00–16:00，半日市为 09:30–12:00。12:00–13:00 午休不计 gap。

历史因子 replay 必须同时满足四道硬门：与事件 JSONL 哈希一致的 Vault/Beast lineage manifest、独立逐笔 capture evidence、独立方向核验 JSON（匹配的 `direction_convention`、`verified=true`、带时区 `verified_at` 和非空 `evidence`），以及 `--coverage-complete` 声明下所有预期股票均通过验收。任一道不通过都不会生成 feature 或未来 label；此时只能用 `--quality-only` 生成 Phase 0 质量报告。

`--output-dir` 必须不存在或为空；每次运行使用独立目录。CLI 不会让本次失败/quality-only 的质量报告与上一次成功运行留下的 feature、label 或 shock 文件混在一起。

Phase 0 当前验收与真实数据阻塞见 [2026-07-13 数据验收报告](reports/phase-00-data-acceptance-2026-07-13.md)。

尚未完成独立方向核验时，运行同一命令但去掉 `--side-verification-file`，加入 `--quality-only`。该模式只落盘 manifest 与 `data_quality_report.csv`，不会生成 signed-flow 因子或未来标签。

## 测试

```bash
cd /home/zrliu/smartcash
/opt/conda/envs/research/bin/python -m pytest -q
```

## 与现有项目的关系

- **Vault**：SmartCash 历史/研究数据的权威版本源；实际 mount/API 由运行环境配置。
- **Beast**：负责从 Vault 生成保留 `event_ts/captured_at` 的规范事件 artifact；处理脚本留在 Beast 所属仓库，SmartCash 只校验 manifest 和消费结果。
- **Thousand**：可承担实时采集或运维展示，但不是 SmartCash 默认历史研究数据 API，也不拥有因子语义。
- **Lemnis**：SmartCash 已能输出哈希绑定的 1s/5s dual-plane Parquet sidecar，并把 Protected IOC intent 转成 Lemnis 公共订单 batch；L2 逐档成交仍由 SmartCash 负责，Lemnis 用于订单生命周期、风险、账本和 replay。当前本机 Lemnis 缺少其声明的 `polars` 依赖，公共对象物化尚未完成环境验收。
- **Hephaestus**：用于 Research Ledger、假设注册、成本/markout 审计、DecisionEngine 和 dossier；不采用其现有 queue simulator 作为成交真值。

## 当前限制

- full-snapshot 原型，不重建逐订单 price-time priority；
- 没有 hkorder 时不能测真实 add/cancel/refill；
- 没有自己的真实成交，不能验证 queue position 或 fill probability；
- synthetic 结果只验证管线，不证明 alpha；
- 还没有在线学习 broker skill，当前只消费显式历史 prior；
- 已有首个 eligible 新盘口上的 10bp/2-tick、前五档、2% visible-capacity Protected IOC 原型，但尚未加入 point-in-time 港股费用、可配置延迟批量场景、未观测冲击压力与组合账本，不能把 markout 当净策略收益。
