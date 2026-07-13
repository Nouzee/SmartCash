# 真实港股研究计划

## Phase 0 — 数据验收

1. Thousand 同时采集 `hktransaction` 与 `l2thousand`，保留 exchange event time、sequence/trade ID、active/passive broker。
2. 用独立 tape 核验 `dir` 方向，未通过前不报告 broker net flow。
3. 对 event loss、重复、乱序、盘口 crossed/locked、staleness、active broker coverage 出日报。
4. 记录 `complete/sessionStart/replayed`，不得把进程启动后的局部会话描述为当日全量。
5. broker queue 独立保存，但不进入 trade/L2 replay。

## Phase 1 — 因子与标签

- 以 200ms/1s/5s 冻结 FeatureSnapshot；
- 生成 10s/30s/60s/300s midpoint markout、MAE/MFE、spread capture；
- shock 生成 persistent/dampened/reversed outcome；
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
