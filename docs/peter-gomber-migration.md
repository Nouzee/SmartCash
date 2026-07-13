# Peter Gomber volatility interruption 思路迁移边界

研究日期：2026-07-13

## 原始来源结论

[Peter Gomber 教授主页](https://www.efinance.wiwi.uni-frankfurt.de/en/team/staff/prof-dr-peter-gomber.html)确认其研究领域包括 market microstructure theory、电子交易系统、市场监管影响和 digital finance / fintech。

[SSRN 5055236](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5055236)所列 working paper *Don’t Stop Me Now! Identification and Prediction of Unnecessary Volatility Interruptions* 由 Benjamin Clapham、Peter Gomber、Florian Ewald、Niklas Trimpe 合著，最新版本日期为 2025-08-28。方法核验使用作者提交的[论文全文](https://portal.northernfinanceassociation.org/viewp.php?n=2240173992)。

论文研究已经实际触发的 Xetra volatility interruption，不是普通 `k×vol` 价格跳变。样本使用中断前后各两分钟、200ms 频率的前十档 LOB、成交、委托增删改和新闻。[论文 pp. 5–9](https://portal.northernfinanceassociation.org/viewp.php?n=2240173992#page=6)

论文先用 autoencoder + GMM 对事件前后路径聚类，再依据同向 midpoint 趋势持续、spread 变宽、L1 depth 下降、volatility 上升，以及趋势是否至少减速 50%，构造 unnecessary 标签。[论文 pp. 15–20](https://portal.northernfinanceassociation.org/viewp.php?n=2240173992#page=16)

事前预测只使用中断前数据。解释变量包括 relative spread、L1 depth、成交量、midpoint volatility、order-book message count、新闻、fast-market、历史中断、替代场所交易和距触发边界距离。论文没有 broker/participant identity、aggressor-signed flow、净买卖额或 concentration。[论文 pp. 25–36](https://portal.northernfinanceassociation.org/viewp.php?n=2240173992#page=26)

作者优先 precision；完整模型在阈值 0.775 时报告 precision 82.5%、recall 20.4%。论文使用随机 event split，而交易研究迁移应改成时间 walk-forward 和相邻事件 embargo。[论文 pp. 36–38](https://portal.northernfinanceassociation.org/viewp.php?n=2240173992#page=37)

## 本项目直接借鉴

- ex-post outcome 与 ex-ante feature 严格分离；
- 用趋势持续/减速/反转定义冲击结果；
- 同时观察 spread、depth、volatility、message activity；
- 完整性不足时保守回退；
- 将高 precision 作为可研究的非对称损失门控，而非追求全覆盖。

## 本项目自己的假设

- active broker / participant 净流代表潜在 informed flow；
- 历史 markout skill prior 能提高身份流质量；
- OFI、microprice、signed flow persistence 有助于事前确认；
- concentration 与 price response 的交互有信息；
- absorption candidate 可以用未来 markout 区分吸收成功和接盘失败；
- `max(k×past vol, return floor)` 可以作为港股研究 shock detector。

这些内容都不是论文公式，必须分别消融和验证。

## 香港制度差异

[HKEX VCM FAQ](https://www.hkex.com.hk/Global/Exchange/FAQ/Securities-Market/Trading/VCM?sc_lang=en)说明香港 VCM 以五分钟前最后成交价为参考，大/中/小型股价格带分别为 ±10%/±15%/±20%，触发后是五分钟 cooling-off，期间仍可在价格带内成交。这不同于 Xetra 的非计划集合竞价。

因此不能复制论文的时间窗、cluster 数、阈值或性能；本项目只迁移“判断价格冲击是否可持续”的研究逻辑。
