# Phase 4 — XTQuant subscription-ack evidence

Run date: 2026-07-14 (Asia/Shanghai)

## Decision

**No.** Based on the installed XTQuant SDK and local first-party Beast/Thousand
implementations, an adapter cannot truthfully set
`subscription_acknowledged=true` for SmartCash today.

The available signals are a client-visible subscription sequence number, global
quote-server connection state, and later market-data callbacks. None is a
durable provider-side acknowledgement bound to a specific `symbol × period`
subscription. The SmartCash full-session capture gate remains blocked for
empirical claims.

## Evidence by signal

| Signal | What the local source actually provides | Why it is not the required provider ACK |
| --- | --- | --- |
| Client-side subscription return | `subscribe_quote` declares and returns an integer subscription sequence; the SDK documentation says a positive value means “subscription success” and `-1` failure. It supplies no provider identity, acknowledgement payload, acknowledgement timestamp, or durable receipt. | It is a synchronous SDK/MiniQmt result, not a persisted, attributable provider acknowledgement artifact. |
| `hktransaction` request | The generic `subscribe_quote` wraps a market-data callback, constructs metadata including `period`, and returns the underlying `client.subscribe_quote(...)` integer. | No distinct ACK callback or ACK record exists in this public path. |
| `l2thousand` request | `subscribe_l2thousand` likewise wraps a market-data callback and returns the same underlying integer result. | Same absence: no provider-ACK payload, timestamp, or durable record. |
| Market-data callback | SDK wrappers decode BSON and forward `datas`; local clients turn these into received/enqueued callback counts and raw events. | A callback proves only that data reached this process after the request; it cannot prove subscription coverage before the first event or source-side acceptance for a silent period. |
| Quote-server watch | `watch_quote_server_status` exposes only global `connected/disconnected` state. | It is neither per-symbol nor per-period, so it cannot acknowledge the two required subscriptions. |

## Precise local sources

- Installed SDK: [`xtdata.md`](/home/hliu/xtbackend/vendor/xtquant_251211_interim-release_cp36m-37m-38-39-310-311-312_linux-gnu_x86_64/xtquant/doc/xtdata.md:203) documents that `subscribe_quote` returns a subscription number and delivers market data through `callback`; its stated positive/negative result is at [line 239](/home/hliu/xtbackend/vendor/xtquant_251211_interim-release_cp36m-37m-38-39-310-311-312_linux-gnu_x86_64/xtquant/doc/xtdata.md:239).
- SDK implementation: [`xtdata.py`](/home/hliu/xtbackend/vendor/xtquant_251211_interim-release_cp36m-37m-38-39-310-311-312_linux-gnu_x86_64/xtquant/xtdata.py:1222) declares the generic return as an integer sequence and delegates to the underlying client at [line 1279](/home/hliu/xtbackend/vendor/xtquant_251211_interim-release_cp36m-37m-38-39-310-311-312_linux-gnu_x86_64/xtquant/xtdata.py:1279). The callback wrapper only decodes and forwards market-data payloads at [lines 1170–1181](/home/hliu/xtbackend/vendor/xtquant_251211_interim-release_cp36m-37m-38-39-310-311-312_linux-gnu_x86_64/xtquant/xtdata.py:1170).
- The SDK has a dedicated `l2thousand` entry point, but it too documents an integer subscription number and directly returns `client.subscribe_quote(...)`: [`xtdata.py:1346`](/home/hliu/xtbackend/vendor/xtquant_251211_interim-release_cp36m-37m-38-39-310-311-312_linux-gnu_x86_64/xtquant/xtdata.py:1346), [`xtdata.py:1379`](/home/hliu/xtbackend/vendor/xtquant_251211_interim-release_cp36m-37m-38-39-310-311-312_linux-gnu_x86_64/xtquant/xtdata.py:1379).
- Its only local connection-status watcher is global server state (`connected`/`disconnected`), not subscription acknowledgement: [`xtdata.py:3408`](/home/hliu/xtbackend/vendor/xtquant_251211_interim-release_cp36m-37m-38-39-310-311-312_linux-gnu_x86_64/xtquant/xtdata.py:3408).
- Beast’s native vendor guide sends `hktransaction` through `subscribe_quote(..., callback=...)` and starts the run loop; it does not show or persist an ACK: [`港股L2数据原生_v3.9.md:18`](/home/hliu/beast/港股L2数据原生_v3.9.md:18). It obtains `l2thousand` through `subscribe_l2thousand` with the same callback model: [`港股L2数据原生_v3.9.md:741`](/home/hliu/beast/港股L2数据原生_v3.9.md:741).
- Beast’s live service calls both methods but discards their return values; it only catches synchronous exceptions and forwards later callbacks: [`subscribe.py:531`](/home/hliu/beast/services/mammoth/realtime-service/src/subscribe.py:531), [`subscribe.py:612`](/home/hliu/beast/services/mammoth/realtime-service/src/subscribe.py:612).
- Thousand’s adapter retains SDK returns as in-memory `subscription_handles`, then marks the symbol subscribed; it creates no provider-ACK artifact: [`xtquant_client.py:145`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:145), [`xtquant_client.py:375`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:375). Its callback is explicitly a market-data bridge with local counters: [`xtquant_client.py:390`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:390).
- SmartCash itself correctly separates the two concepts: the prospective command states that XTQuant exposes subscription return, not provider acknowledgement: [`smartcash_live_capture.py:1`](/home/zrliu/thousand/backend/tools/smartcash_live_capture.py:1). Its recorder stores the return separately but deliberately rejects an attempt to claim provider acknowledgement without an adapter: [`live_capture.py:78`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:78), [`live_capture.py:91`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:91).
- The SmartCash gate requires `subscription_acknowledged`, an acknowledgement timestamp before expected open, complete heartbeats, and zero dropped callbacks: [`data_quality.py:80`](/home/zrliu/smartcash/src/smartcash/data_quality.py:80).

## Recommended next engineering action

Do **not** write an adapter that maps a positive subscription sequence, a
`connected` transition, or a first callback to
`subscription_acknowledged=true`. That would weaken the stated evidence
contract without adding provider evidence.

Instead, acquire a provider-controlled, persistable per-`symbol × period`
acknowledgement interface or record from XTQuant/MiniQmt (for example a
documented subscription-status event or support-provided audit feed). First
validate that it contains the requested symbol, `hktransaction` or
`l2thousand`, provider-issued time, success/failure, and a stable receipt or
event identifier. Then add a narrow adapter which fsyncs that raw record and
its hash before calling `record_provider_acknowledgement`.

Until such a source is available, continue recording the SDK return,
connection observations, callbacks, heartbeats, and drop counters as
diagnostic capture observations only; retain `subscription_acknowledged=false`
and run SmartCash exclusively in `--quality-only` mode.
