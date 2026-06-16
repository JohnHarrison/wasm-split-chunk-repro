#!/usr/bin/env python3
"""
Validate the lazy-route chunk-failure fix on leptos 0.9 + wasm_split_helpers 0.2.2.

Aborts ONE fetch of the ViewC *view* chunk (the lazy-route view that
`#[lazy_route]` now emits as `fallible`), then checks:

  nav 1 (one chunk fetch aborted): NO panic / NO `unreachable`; the
         <ErrorBoundary> fallback (#chunk-error) renders instead.
  nav 2 (network healthy):         the route loads normally (#page = "View C"),
         proving the failure was not cached.

Usage: python3 demo_repro_09.py http://127.0.0.1:3006
"""
import sys

from playwright.sync_api import sync_playwright

base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3006"
link = "a:has-text('C')"
view_chunk = "**/pkg/split___view_c_view_*.wasm"

panics = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.on("console", lambda m: m.type == "error" and print(f"[console.error] {m.text[:300]}"))

    def on_pageerror(e):
        s = str(e)
        print(f"[pageerror] {s[:200]}")
        if "unreachable" in s or "load callback should succeed" in s:
            panics.append(s)
    page.on("pageerror", on_pageerror)

    page.goto(base_url, wait_until="networkidle")

    aborted = {"done": False}

    def abort_once(route):
        if not aborted["done"]:
            aborted["done"] = True
            print(f"[repro] aborting one view-chunk fetch: {route.request.url}")
            route.abort()
        else:
            route.fallback()
    page.route(view_chunk, abort_once)

    print("\n=== NAV 1: lazy route with one aborted view-chunk fetch ===")
    page.click(link)
    page.wait_for_timeout(3000)
    assert aborted["done"], "view chunk never fetched — wrong selector/chunk"
    fallback_visible = page.locator("#chunk-error").count() > 0
    print(f"[check] ErrorBoundary fallback (#chunk-error) visible: {fallback_visible}")
    print(f"[check] panic/unreachable observed: {bool(panics)}")

    print("\n=== NAV 2: navigate away and back, network healthy ===")
    page.goto(base_url, wait_until="networkidle")
    page.click(link)
    page.wait_for_timeout(3000)
    recovered = "View C" in (page.locator("#page").inner_text() if page.locator("#page").count() else "")
    print(f"[check] route recovered on renavigation (#page = 'View C'): {recovered}")

    browser.close()

print("\n================ VERDICT ================")
ok = (not panics) and fallback_visible and recovered
print(f"no panic on nav 1 : {not panics}")
print(f"fallback on nav 1 : {fallback_visible}")
print(f"recovery on nav 2 : {recovered}")
print("RESULT:", "FIXED ✅" if ok else "NOT FIXED ❌")
sys.exit(0 if ok else 1)
