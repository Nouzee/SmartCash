# 真实港股研究计划

## Phase 0 — 数据验收

1. Thousand 同时采集 `hktransaction` 与 `l2thousand`，保留 exchange event time、sequence/trade ID、active/passive broker。
2. 用独立 tape 核验 `dir` 方向，未通过前不报告 broker net flow。
3. 对逐笔/L2 的 event time 与 callback arrival 分别检查缺失、负延迟、乱序和 staleness；另查 sequence gap、重复 trade ID、盘口 crossed/locked、active broker coverage。载入后排序不能抹掉原始质量证据。
4. 调用方显式声明 expected universe；零事件股票也必须有失败行。逐笔完整性另由采集器的 subscription ACK、开收盘 heartbeat envelope 与 dropped callback 计数证明，不能由局部 sequence 连续推断。
5. 完整日按冻结的 2025–2026 HKEX 开市/休市/半日市日历、香港 `+08:00` 时区和不超过 5 秒的活跃时段 L2 gap 验收，调用方只能收紧阈值。
6. 记录 `complete_60s/complete_300s/sessionStart/replayed/coverage_complete/max_book_gap_seconds`，不得把 replay 标志或进程启动后的局部会话描述为当日全量。
7. 只有 capture envelope、coverage 与独立 side verification 都通过的 session 才能生成因子和未来标签；其他输入只能生成质量报告。
8. broker queue 独立保存，但不进入 trade/L2 replay。

## Phase 1 — 因子与标签

- 以 200ms/1s/5s 冻结 FeatureSnapshot；
- 生成 10s/30s/60s/300s midpoint markout、MAE/MFE、spread capture；
- shock 生成 persistent/dampened/reversed outcome，并记录 path reversal、signed-flow persistence、order-flow decay；
- absorption candidate 单独评估，不预设正标签；
- broker skill 只用已成熟历史 markout，按日滚动更新并加 shrinkage。

## Phase 2 — Walk-forward

- 按交易日 expanding train/validation/test；
- 同标的相邻 shock/信号做 embargo；
- 比较 book-only、flow-only、identity-only、flow+price、full score；
- 报告 IC/rank IC、hit rate、markout、MAE、signal count、coverage 和 regime stability；
- 以高 precision threshold 为主，同时量化漏掉的盈利机会。

## Phase 3 — 执行验证

- 加费用、延迟、spread crossing 和 participation；
- 有 hkorder 后再研究 add/cancel/refill；
- 有自己的真实订单回报后再估 queue/fill probability；
- 冻结 1s/5s feature sidecar 接入 Lemnis 的下一步执行、账本与 replay；
- 用 Hephaestus 风格 DecisionEngine 决定 PROMOTE/KILL/RETEST/MONITOR。

## 晋级条件

- side contract 和 active broker coverage 通过；
- test-only 多标的、多月结果稳定；
- full score 相对 book-only/flow-only 有增量；
- conflict filter 显著降低负 markout 数量和比例；
- realistic cost 后仍为正；
- shadow replay 与离线 replay 对同一事件产生逐字段一致的 FeatureSnapshot。
