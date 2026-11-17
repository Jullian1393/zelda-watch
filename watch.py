#!/usr/bin/env python3
"""Zelda 40th Anniversary Switch 2 restock watcher (cloud, push via ntfy).

Checks Nintendo, Target, Best Buy and GameStop every 30 seconds and sends a
phone push through ntfy when one looks buyable.
"""
import json, re, subprocess, sys, time, urllib.request, datetime

URL = ("https://www.nintendo.com/us/store/products/"
       "nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition-121642/")
import os
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", "0"))  # 0 = forever
INTERVAL = 30            # seconds between checks
COOLDOWN = 600           # don't re-alert for 10 minutes after an alert

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def log(msg):
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def in_stock(html):
    """True if the page data says the console can be bought."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    blob = m.group(1) if m else html
    sold_out = re.search(r'"(?:isSoldOut|soldOut)"\s*:\s*true', blob) or \
        re.search(r'"(?:availability|stockStatus)"\s*:\s*"(?:OUT_OF_STOCK|SOLD_OUT|NOT_AVAILABLE)', blob, re.I)
    buyable = re.search(r'"(?:isPurchasable|purchasable|isSalableInStore|inStock)"\s*:\s*true', blob) or \
        re.search(r'"(?:availability|stockStatus)"\s*:\s*"(?:IN_STOCK|AVAILABLE)', blob, re.I) or \
        re.search(r'<button(?![^>]*disabled)[^>]*>\s*Add to cart\s*<', html, re.I)
    return bool(buyable) and not sold_out


def simple_check(buy_patterns, out_patterns):
    def check(html):
        out = any(re.search(p, html, re.I) for p in out_patterns)
        buy = any(re.search(p, html, re.I) for p in buy_patterns)
        return buy and not out
    return check


# name, url, checker. Big stores sometimes block scripts; those show "check failed".
STORES = [
    ("Nintendo", URL, in_stock),
    ("Target", "https://www.target.com/p/-/A-1013322047",
     simple_check([r'"availability_status"\s*:\s*"IN_STOCK', r'<button(?![^>]*disabled)[^>]*>\s*Add to cart\s*<'],
                  [r'"availability_status"\s*:\s*"OUT_OF_STOCK', r'>\s*Out of stock\s*<', r'disabled[^>]*>\s*Add to cart'])),
    ("Best Buy", "https://www.bestbuy.com/product/switch-2-the-legend-of-zelda-40th-anniversary-edition/J7GSL57HTY",
     simple_check([r'data-button-state="ADD_TO_CART"', r'<button(?![^>]*disabled)[^>]*>\s*Add to Cart\s*<'],
                  [r'data-button-state="SOLD_OUT"', r'>\s*Sold Out\s*<', r'Coming Soon'])),
    ("GameStop", "https://www.gamestop.com/consoles-hardware/nintendo-switch-2/products/nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition/20037854.html",
     simple_check([r'<button(?![^>]*disabled)[^>]*>\s*Add to Cart\s*<', r'"availability"\s*:\s*"https?://schema.org/InStock"'],
                  [r'Currently Unavailable', r'Not Available', r'Sold Out', r'Coming Soon'])),
]


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


def alert_store(name, url):
    data = f"Zelda Switch 2 may be in stock at {name}. Tap to open.".encode()
    req = urllib.request.Request("https://ntfy.sh/" + NTFY_TOPIC, data=data, headers={
        "Title": f"RESTOCK: {name}", "Priority": "urgent", "Tags": "rotating_light",
        "Click": url, "Actions": f"view, Open {name}, {url}"})
    urllib.request.urlopen(req, timeout=20)
    log(f"ALERT sent for {name}")


def main():
    if "--test" in sys.argv:
        alert_store("TEST", URL)
        return
    last_alert = {}
    log("Watching: " + ", ".join(s[0] for s in STORES))
    start = time.time()
    while not RUN_SECONDS or time.time() - start < RUN_SECONDS:
        statuses = []
        for name, url, check in STORES:
            try:
                if check(fetch_url(url)):
                    statuses.append(f"{name}: IN STOCK")
                    if time.time() - last_alert.get(name, 0) > COOLDOWN:
                        alert_store(name, url)
                        last_alert[name] = time.time()
                else:
                    statuses.append(f"{name}: sold out")
            except Exception as e:
                statuses.append(f"{name}: check failed ({e})")
        log(" | ".join(statuses))
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
