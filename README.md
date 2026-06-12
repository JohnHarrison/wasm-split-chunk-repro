# Repro: one transient chunk-fetch failure permanently bricks a wasm-split lazy route

Affects `wasm_split_helpers` 0.2.1 (current) as used by leptos `--split`
lazy routes (leptos 0.8.x, cargo-leptos 0.3.x).

## Mechanism

- The generated JS loader (`makeFetch.web.js` / `split_wasm.js` in
  `wasm_split_cli`) starts a single `fetch(srcUrl)` and converts **any** error
  into a one-shot `callback(success = false)` — no retry.
- On the Rust side, `rt.rs::ensure_loaded` polls an
  `async_once_cell::Lazy<Option<()>>` and
  `.expect("load callback should succeed")`s the result.

Consequences of a single aborted/failed chunk fetch (flaky mobile network,
navigation abort, transient 5xx):

1. the WASM runtime **panics** (`load callback should succeed`,
   `pageerror: unreachable`), and
2. the failure is **cached forever** by the once-cell — every later
   `ensure_loaded` for that chunk re-polls the same failed cell, so the lazy
   route stays dead for the whole session even after the network recovers.
   Only a full page reload fixes it.

## Running

`abort_chunk_repro.py` makes the failure deterministic with Playwright route
interception — it aborts exactly one request matching `**/pkg/chunk_*.wasm`
during a client-side navigation to a lazy route, then proves the
cached-forever behavior by re-navigating with a healthy network.

```sh
pip install playwright && playwright install chromium
# against any --split leptos app with a lazy route, e.g. the leptos
# `lazy_routes` example:
python3 abort_chunk_repro.py http://127.0.0.1:3000 "a:has-text('C')"
```

Expected output: `TypeError: Failed to fetch`, the
`wasm_split_helpers .../rt.rs` panic on the first navigation, and the same
dead route on the second navigation despite no further aborts.

## Suggested fix

Retry transient fetch failures in the JS loader and/or make the once-cell
init retryable instead of caching `None`; at minimum surface a recoverable
error instead of panicking.

Found via leptos 0.8.19 `--split` lazy routes in production-like e2e testing
(intermittent on real networks; deterministic with the script above).
