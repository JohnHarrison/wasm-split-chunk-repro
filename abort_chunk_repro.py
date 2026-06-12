#!/usr/bin/env python3
"""
Deterministic reproduction of the wasm_split_helpers chunk-failure panic:
one aborted wasm-split chunk fetch permanently breaks a lazy route.

Usage (against any cargo-leptos app built with --split and lazy routes):

    pip install playwright && playwright install chromium
    python3 abort_chunk_repro.py http://127.0.0.1:3000 "a:has-text('Lazy')"

Arguments: the app's base URL, and a selector for a link that triggers a
client-side navigation to a lazy (wasm-split) route.

What it does:
  1. Loads the base URL and waits for hydration to settle.
  2. Installs a route handler that aborts exactly ONE request matching
     **/pkg/chunk_*.wasm — simulating a single transient network failure.
  3. Clicks the lazy-route link (client-side navigation).
  4. Prints the console: you'll see `TypeError: Failed to fetch` followed by
     `panicked at wasm_split_helpers-x.y.z/src/rt.rs: load callback should
     succeed` and `pageerror: unreachable`.
  5. Navigates away and back with the network healthy again: the route is
     still dead — async_once_cell cached the failed init for the session.
"""

import sys

from playwright.sync_api import sync_playwright

base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"
link_selector = sys.argv[2] if len(sys.argv) > 2 else "a:has-text('Lazy')"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.on("console", lambda m: m.type == "error" and print(f"[console.{m.type}] {m.text[:400]}"))
    page.on("pageerror", lambda e: print(f"[pageerror] {str(e)[:200]}"))

    page.goto(base_url, wait_until="networkidle")

    aborted = {"done": False}

    def abort_once(route):
        if not aborted["done"]:
            aborted["done"] = True
            print(f"[repro] aborting one chunk fetch: {route.request.url}")
            route.abort()
        else:
            route.fallback()

    page.route("**/pkg/chunk_*.wasm", abort_once)

    print("[repro] navigating to the lazy route (first attempt, one fetch will abort)…")
    page.click(link_selector)
    page.wait_for_timeout(3000)
    assert aborted["done"], "no chunk fetch happened — pick a link to a route that is actually lazy"

    print("[repro] navigating away and back (network healthy — should recover, doesn't)…")
    page.goto(base_url, wait_until="networkidle")
    page.click(link_selector)
    page.wait_for_timeout(3000)

    browser.close()
