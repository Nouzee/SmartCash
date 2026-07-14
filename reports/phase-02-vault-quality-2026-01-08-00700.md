# Phase 2 — First Vault quality-only replay

Run date: 2026-07-14 (Asia/Shanghai)

Market session: 2026-01-08

Symbol: `00700.HK`

## Outcome

The data exists and the Vault-to-SmartCash path runs end to end, but this
session is not admissible for factor estimation, alpha claims or performance
backtests. SmartCash correctly produced zero features and zero future labels.

Status: `BLOCKED_FOR_EMPIRICAL_CLAIMS`.

## Source and lineage

- Source: `/vault/core/data/Octopus-Live/PROD/20260108/realtime`
- Selected contracts: `tick_archiver/tick_raw` and
  `l2thousand_enhancer/l2thousand`
- Explicitly excluded: 12,917 `large_trade_monitor` broker-queue files
- Selected source files: 22,992
- Selected source snapshot SHA-256:
  `afe1632e9b569ae5161708fb8ee63eb940506256ee33d0a8ca4c43b242e2e07b`
- Export SHA-256:
  `ddba4b5dea996f08bdef9db53e94b9b43a94392ea796d882952c91e53c88e84b`
- Arrival proxy: filesystem `mtime_ns`, labelled
  `captured_at_source=vault_file_mtime_ns`

The source writer saves files using wall-clock time, but the archive contains
no independent callback receipt record. File mtime is therefore a quality
diagnostic proxy, not proof of callback completeness or latency.

## Quality results

| Check | Result |
| --- | ---: |
| Raw trade rows | 10,717 |
| Raw L2 rows | 12,275 |
| Accepted L2 rows | 12,271 |
| Crossed/locked L2 rejected | 4 |
| Trade sequence present | yes |
| Trade sequence discontinuities | 10,715 |
| Duplicate trade IDs | 0 |
| Stale trades above 1,000 ms | 3,191 |
| Stale books above 1,000 ms | 1,445 |
| Maximum trade save-time latency proxy | 576,656.908 ms |
| Maximum book save-time latency proxy | 576,058.908 ms |
| Maximum active-session L2 gap | 593.451 s |
| Neutral turnover share | 10.6507% |
| Active-seat disclosure, turnover-weighted | 0.0267% |
| Broker-entity mapping coverage | 0% |

Session-duration endpoints cover the requested day, but that alone does not
prove complete tape or L2 capture. The near-total sequence discontinuity also
shows that Vault `Seq` cannot be assumed to be a contiguous per-symbol tape
counter.

## Failed hard gates

- no independent `xtquant.hktransaction` subscription ACK, capture heartbeats,
  or dropped-callback counter;
- no independent verification of `Dir=1/2` semantics;
- tape continuity failed;
- trade and L2 save-time staleness failed;
- the 593.451-second book gap exceeds the 5-second hard maximum;
- active-seat disclosure is too sparse and no as-of broker identity mapping is
  supplied to this replay;
- no final Vault/Beast lineage manifest can be issued without admissible
  capture evidence.

## Next step

Search Vault and `/home/hliu/beast` capture infrastructure for the missing ACK,
heartbeat/drop-counter and direction-verification artifacts. If they do not
exist, the next valid dataset must be captured prospectively with those records
rather than inferring completeness from archive filenames or mtimes.

A static candidate mapping exists at
`/vault/core/data/Mammoth-v1/silver/base/broker_info/broker_id_to_participant_id.csv`.
It maps the only disclosed active seat in this sample, `5336`, to participant
`B01110`, J.P. Morgan Broking (Hong Kong) Ltd. It lacks SmartCash as-of validity
metadata and was not supplied to this run, so the reported mapping coverage
correctly remains zero. Even after validation, the sample's 0.0267%
turnover-weighted seat disclosure is far too sparse for identity-flow claims.
