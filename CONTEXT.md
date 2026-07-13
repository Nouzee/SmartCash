# SmartCash Microstructure Context

SmartCash 港股高频盘口研究的领域语言。这个上下文拥有原始市场事件的因果推进、微结构状态和策略产品；Lemnis 是可复用的高频基础库。

## Language

**Vault Dataset（Vault 数据集）**:
SmartCash 研究使用的权威历史/原始市场数据版本；必须可由 dataset ID、version 与内容哈希唯一定位。
_Avoid_: Thousand 默认数据源、本地临时 CSV、当前会话缓存

**Beast Transform（Beast 数据变换）**:
由 Beast 所属脚本把冻结的 Vault 数据转换成 SmartCash 规范事件 artifact 的可复现步骤；脚本 commit、配置哈希与输出哈希必须入 manifest。
_Avoid_: SmartCash 因子逻辑、前端 adapter、无版本清洗脚本

**Microstructure Event Clock（微结构事件时钟）**:
以交易所事件时间表达市场状态、以采集到达时间约束知识可见性的唯一因果时钟。它由 SmartCash 拥有，迟到事件不能回写已经完成的旧决策。
_Avoid_: Lemnis tick clock、分钟时钟、高频回测时钟

**Microstructure Step Snapshot（微结构步进快照）**:
SmartCash 在微结构事件时钟上冻结的、不可变且可审计的边界对象；它由决策状态和执行状态组成，两者共享同一时点与来源水位。
_Avoid_: Tick、Bar、Minute DataView、Feature Sidecar Row

**Decision State（决策状态）**:
微结构步进快照中用于产生或过滤交易信号的因果特征，包括主动资金流、盘口压力、冲击持续性、价格响应与数据质量。
_Avoid_: Execution Inputs、Fill State、未来标签

**Execution State（执行状态）**:
微结构步进快照中供 Lemnis 撮合使用的当时可见市场状态，包括多档价量、价差、最近成交和事件水位；它不包含未来路径，也不得用决策因子改变成交事实。
_Avoid_: Decision Features、Alpha State、重建盘口

**Source Watermark（来源水位）**:
一个快照已经因果消费到的逐笔与盘口来源位置，用于证明决策状态和执行状态对应同一市场知识边界。
_Avoid_: Processing Time、Future Horizon、文件行号

**Causal Availability（因果可见时间）**:
事件的 `captured_at` 所定义的系统最早已知时间；`event_ts` 描述市场发生时间，但不能让事件在被采集前进入快照或决策。
_Avoid_: Event Time、回填时间、文件排序时间

**Order Eligibility（订单生效时间）**:
订单在决策时间加配置延迟后，最早可以参与撮合的 `eligible_from`；它只能使用此后新到达的市场事件。
_Avoid_: Signal Time、Created At、同快照成交

**Taker-only Execution（仅主动成交）**:
只允许方向性订单跨越价差、逐档消耗订单生效后可见的对手盘；这是首版唯一可计入策略收益的成交方式。
_Avoid_: Market Making、Maker Strategy、触价即成交

**Passive Fill Unknown（被动成交未知）**:
没有逐笔委托增删与真实订单回报时，对未跨价限价单的唯一诚实状态；触价、成交打印或盘口减少都不能证明该订单成交。
_Avoid_: Touch Fill、Queue Fill、Maker Fill

**Decision Checkpoint（决策检查点）**:
策略获准读取当前微结构状态并产生新交易意图的固定时间边界；首版间隔为一秒，边界状态只可由因果上已经可见的事件向前携带。
_Avoid_: One-second Bar、桶结束聚合、Execution Step

**Market Event Step（市场事件步进）**:
每个规范化逐笔或盘口事件对唯一微结构状态机的一次因果推进；Lemnis 撮合可观察每次步进，但策略不会因此自动重新决策。
_Avoid_: Decision Checkpoint、Tick Bar、轮询刷新

**Candidate Shock（候选冲击）**:
价格、主动身份流或盘口流动性相对其因果历史显著异常而建立的待判断事件；它本身不是交易信号。
_Avoid_: Volatility Interruption、Trade Signal、单次价格跳动

**Candidate Lifecycle（候选生命周期）**:
候选冲击从发现、观察到确认或过期的单向状态机；首版最多观察五秒，至少两个含新成交和新盘口事件的连续一秒检查点通过门控才可确认。
_Avoid_: Future Label、可复活信号、重复快照确认

**Re-armed（重新待命）**:
标的在候选过期或交易片段结束后，触发异常连续两个含新事件的检查点回落到非异常区，因而获准发现下一次独立候选的状态。
_Avoid_: Cooldown Timer、持仓中加仓、旧冲击复活

**Shock Cluster（冲击簇）**:
同一标的在未重新待命前持续出现的同向异常集合；无论强度更新多少次，它只对应一个候选和最多一个交易片段。
_Avoid_: 多个独立信号、Pyramiding Opportunity、重复样本

**Sustainability Gate（持续性门控）**:
候选冲击之后，使用当时已经可见的方向流持续性、价格响应、流动性恢复和身份集中度判断是否允许产生方向性交易意图。
_Avoid_: Future Outcome、Shock Label、SmartMoneyScore Threshold

**Microstructure Confirmed（微结构确认）**:
只由盘口、价格和主动成交方向证明具有持续性的候选冲击；它是无身份基准，不得被命名为聪明钱确认。
_Avoid_: SmartMoney Confirmed、Identity Signal、最终主策略

**SmartMoney Confirmed（聪明钱确认）**:
已经通过微结构持续性门控，并在覆盖达标的 as-of seat/broker entity 身份证据中获得同向确认的候选冲击；它才具备主策略晋级资格。
_Avoid_: Candidate Shock、Raw SmartMoneyScore、Microstructure Confirmed

**Identity Unavailable（身份不可用）**:
身份映射或历史先验覆盖不足，无法作身份确认或冲突判断的状态；它表示缺少证据，不表示反向证据。
_Avoid_: Identity Conflict、Unknown Broker Is Bearish、零身份分数

**Seat（交易席位）**:
逐笔成交原始 `activeBrokerNo` 标识的执行席位，是 SmartCash 保留的最细身份事实；它不是 CCASS participant，也不自动等于独立公司。
_Avoid_: Participant、Broker Company、CCASS Holder

**Broker Entity（经纪商实体）**:
SmartCash 自有身份注册表中，一个或多个交易席位按 as-of 关系归属的经纪商公司实体。
_Avoid_: Seat、Participant ID、Broker Display Name

**External Identity Alias（外部身份别名）**:
来自其他系统、带来源和有效期的可选身份引用，例如 CCASS participant ID；它不能成为 SmartCash 的规范主键或隐式引入外部持仓语义。
_Avoid_: Canonical Broker ID、Participant、无来源映射

**Hierarchical Identity Evidence（层级身份信息）**:
同一批成交在 seat 和 broker entity 两个嵌套视图中的身份特征；最终确认必须防止将同一成交重复计分。
_Avoid_: Broker Score Plus Participant Score、独立双重确认

**Snapshot Contract（快照边界契约）**:
策略项目向高频基础设施暴露 `MicrostructureStepSnapshot` 的版本化公共模式；历史 Parquet sidecar 与实时消息是同一契约的两种传输形式。
_Avoid_: Internal Engine API、CCASS Payload、Minute DataView

**SmartCash**:
独立的港股方向性高频微结构研究与策略项目，拥有事件时钟、身份模型、因子语义、策略运行配置和快照契约，并可复用 Lemnis 公共基础设施。
_Avoid_: Smart Money、smart-money、CCASS 高频版、Lemnis 策略

**Deployable Long/Flat（可部署多头/空仓）**:
SmartCash 当前唯一可进入实盘候选的持仓状态；正向确认可以开多，负向确认只能减仓、平仓或禁止新多。
_Avoid_: Short Position、Borrow Assumption、对称实盘策略

**Experimental Short Signal（实验性空头信号）**:
负向 SmartMoneyConfirmed 的独立研究分支，可评估方向 markout 和明确标记为假设的主动成交回测，但在借券与卖空制度数据完备前不具备部署资格。
_Avoid_: Deployable Short、Executable Alpha、实盘组合收益

**Trade Episode（交易片段）**:
一次通过持续性门控后的方向性持仓生命周期，首版最长六十秒；它可以因反向微结构确认、身份冲突、质量失效或交易时段边界提前结束。
_Avoid_: Markout Horizon、隔夜持仓、事后最优退出

**Visible Capacity（可见容量）**:
订单生效后对手方前五档显示金额中，按冻结参与率允许 SmartCash 消耗的上限；它不代表隐藏流动性或未来补单。
_Avoid_: Daily Turnover Capacity、Full Fill Guarantee、Broker Queue

**Unfilled Capacity（容量不足未成交）**:
目标金额经过可见深度、现金/持仓和每标的 board lot 约束后不足一手的结果；它是未成交机会，不是亏损交易。
_Avoid_: Zero Return、Rejected Alpha、Partial Loss

**Protected IOC（价格保护即时成交剩余撤销单）**:
只在订单生效后的首次合格盘口中主动逐档成交，并以决策 midpoint 十个基点和最优对手价外两档 tick 的较严者限制最差价格；剩余数量立即取消。
_Avoid_: Market Order、Resting Limit Order、未来补单成交

**Unfilled Price Protection（价格保护未成交）**:
最优对手价已经超出 Protected IOC 允许范围，因而整笔没有成交的结果；它表示执行约束生效，不表示信号亏损。
_Avoid_: Slippage Loss、Rejected Signal、Passive Fill

**Observed Sweep Cost（已观测扫盘成本）**:
Protected IOC 按订单生效后可见 L2 逐档成交所得的 VWAP 与决策 midpoint 之差，已经包含跨价差和可见档位滑移。
_Avoid_: Fixed Slippage、Market Impact Stress、手续费

**Point-in-time Fee Schedule（时点费用表）**:
按成交日期生效的港股法定费用、结算费用与独立券商佣金配置；每个费用项目单独记账并保留来源。
_Avoid_: Current Fee Backfill、Single Cost Bps、Observed Sweep Cost

**Impact Stress（冲击压力情景）**:
对公开 L2 无法观察的自身市场冲击施加的独立 0/2/5bp 假设情景；它不是已观测成交价的一部分。
_Avoid_: Observed Slippage、Actual Fill Cost、重复扣费

**Pre-open Universe（开盘前标的池）**:
每个交易日开盘前，按此前二十个完整交易日中位成交额冻结的普通港股 Top 50，并要求当时已有 board lot、tick size、上市状态和交易日历。
_Avoid_: Current-day Liquidity Screen、盘后数据量选股、全产品混合池

**Empirical Admissibility（经验研究准入）**:
盘后根据独立 capture evidence 判断一个 symbol-day 是否足以支持经验结论的数据质量状态；失败样本保留原因和覆盖统计，但不产生因子业绩。
_Avoid_: Pre-open Universe、Alpha Filter、静默删除

**Seasonal Robust Baseline（时段稳健基线）**:
每只股票、每个五分钟日内时段使用此前二十个经验准入交易日的中位数与 MAD 冻结的异常参照；当天数据不能回写当天已发生候选的基线。
_Avoid_: Full-day Z-score、Current-day Refit、Cross-sectional Mean

**Abnormal Channel（异常通道）**:
price、signed flow、OFI、spread 或 depth 中相对时段稳健基线达到冻结阈值的一类证据；任一通道可以发现候选，但不能单独通过持续性门控。
_Avoid_: Trade Signal、Future Outcome、普通波动

**Price Retention Outcome（价格保留结果）**:
从候选发现时点衡量未来 midpoint 仍保留多少原始有向冲击的 ex-post 标签，分类为 persistent、dampened 或 reversed。
_Avoid_: Trade Return、Market Quality Composite、Realtime Feature

**Execution Markout（成交后标记收益）**:
从实际模拟成交价和成交时点开始计算的未来收益、MAE 与 MFE，用于评价可执行交易；它不能替代候选冲击结果。
_Avoid_: Shock Retention、Decision-mid Return、未成交信号收益

**Market-quality Outcome（市场质量结果）**:
候选后的 path reversal、spread recovery、depth recovery、signed-flow persistence 与 order-flow decay 等独立诊断维度。
_Avoid_: Price Retention Label、单一 Sustainable 布尔值、实时门控输入

**Locked Test Fold（锁定测试折）**:
按全市场完整交易日切分、在 train 与 validation/test 之间各隔一个交易日的二十日测试窗口；一经查看就不能用于修改同轮阈值或模型。
_Avoid_: Random Event Split、重新调参测试集、按股票拆日

**Matured Outcome（已成熟结果）**:
相应固定未来窗口已经完整结束且通过 endpoint 质量检查的标签；只有已成熟结果可以进入下一交易日的 identity skill prior 或训练集。
_Avoid_: Pending Label、Current Candidate、未来回填特征

**Shadow Promotion Gate（影子运行晋级门）**:
SmartCash 从离线研究进入非实盘 shadow 前必须同时通过的数据覆盖、样本量、锁定测试、统计置信度、身份增量、成本压力与集中度硬门。
_Avoid_: Best Fold、主观晋级、实验空头收益

**Bad Trade（负收益交易）**:
在主执行场景下实际模拟成交且六十秒净 markout 为负的交易片段；未成交、数据不可用和实验空头不进入该比例分母。
_Avoid_: Unfilled Signal、Rejected Candidate、Negative Shock Label

**Absorption Cohort（吸收候选组）**:
方向流较强但价格尚未同向响应的研究样本集合；在未来结果验证前，它不代表成功吸收，也不具备交易资格。
_Avoid_: Buy Signal、Confirmed Absorption、抄底信号

**Decision and Execution Pipeline（决策执行管线）**:
SmartCash 拥有的信号到意图、订单、风控、成交、账本与回放链路；它可以组合 Lemnis 公共组件，但 Lemnis 不拥有 SmartCash 领域，也不重建原始盘口。
_Avoid_: Microstructure Engine、盘口因子引擎
