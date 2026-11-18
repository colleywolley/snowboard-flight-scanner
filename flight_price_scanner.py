#!/usr/bin/env python3
"""
Automated 6-Hour Flight Price Scanner for Pre-Christmas 2026 Snowboarding Trips.
Uses SerpApi's multi-airport support (departure_id="MKE,ORD,MDW", arrival_id="DEN,PDX,HDN,ASE")
so each date window only uses 1 API search credit (6 credits per run, preserving your 250 free searches).
"""

#!/usr/bin/env python3
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

LOW_PRICE_THRESHOLDS = {
    "DEN": 250,
    "PDX": 270,
    "HDN": 360,
    "ASE": 420,
}

ORIGINS = "MKE,ORD,MDW"
DESTINATIONS = "DEN,PDX,HDN,ASE"

WEEKENDS = [
    ("2026-12-02", "2026-12-06", "Early Dec (Wed-Sun)"),
    ("2026-12-03", "2026-12-07", "Early Dec (Thu-Mon)"),
    ("2026-12-09", "2026-12-13", "Mid Dec (Wed-Sun)"),
    ("2026-12-10", "2026-12-14", "Mid Dec (Thu-Mon)"),
    ("2026-12-16", "2026-12-20", "Pre-Xmas (Wed-Sun)"),
    ("2026-12-17", "2026-12-21", "Pre-Xmas (Thu-Mon)"),
]

STATE_FILE = Path(__file__).parent / "price_history.json"


def fetch_weekend_fares(api_key: str, dep: str, ret: str) -> dict[str, dict]:
    params = urllib.parse.urlencode({
        "engine": "google_flights",
        "departure_id": ORIGINS,
        "arrival_id": DESTINATIONS,
        "outbound_date": dep,
        "return_date": ret,
        "adults": 2,
        "currency": "USD",
        "hl": "en",
        "api_key": api_key,
    })
    url = f"https://serpapi.com/search.json?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "SnowboardFlightScanner/1.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    flights = (data.get("best_flights") or []) + (data.get("other_flights") or [])
    best_by_route: dict[str, dict] = {}

    for item in flights:
        total_price = item.get("price")
        legs = item.get("flights") or []
        if not total_price or not legs:
            continue

        orig = legs[0].get("departure_airport", {}).get("id", "UNK")
        dest = legs[-1].get("arrival_airport", {}).get("id", "UNK")
        airline = legs[0].get("airline", "Unknown")
        stops = max(0, len(legs) - 1)
        route_key = f"{orig}-{dest}"

        if route_key not in best_by_route or total_price < best_by_route[route_key]["price_total_2_adults"]:
            best_by_route[route_key] = {
                "orig": orig,
                "dest": dest,
                "price_total_2_adults": total_price,
                "price_per_person": round(total_price / 2),
                "airline": airline,
                "stops": stops,
            }

    return best_by_route


def send_webhook(webhook_url: str, message: str) -> None:
    if not webhook_url:
        print(message)
        return
    if "ntfy.sh/" in webhook_url:
        req = urllib.request.Request(
            webhook_url,
            data=message.encode("utf-8"),
            headers={"Title": "Snowboarding Flight Price Alert", "User-Agent": "SnowboardFlightScanner/1.0"},
            method="POST",
        )
    else:
        payload = json.dumps({"content": message, "text": message}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "SnowboardFlightScanner/1.0"},
            method="POST",
        )
    urllib.request.urlopen(req, timeout=10)


def main() -> None:
    api_key = os.environ.get("SERPAPI_KEY", "")
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
    if not api_key:
        print("Set SERPAPI_KEY environment variable to query live Google Flights data.")
        return

    history = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    alerts = []

    for dep, ret, label in WEEKENDS:
        best_by_route = fetch_weekend_fares(api_key, dep, ret)
        for route_key, result in best_by_route.items():
            orig = result["orig"]
            dest = result["dest"]
            key = f"{route_key}_{dep}_{ret}"
            pp = result["price_per_person"]
            prev = history.get(key, {}).get("price_per_person")
            threshold = LOW_PRICE_THRESHOLDS.get(dest, 300)
            stops_str = "Nonstop" if result["stops"] == 0 else f"{result['stops']} stop"

            if prev is not None and pp != prev:
                diff = pp - prev
                direction = f"DROPPED by ${abs(diff)}" if diff < 0 else f"rose by ${diff}"
                alerts.append(
                    f"📊 **{orig} → {dest}** ({label}: {dep} to {ret}) {direction}: "
                    f"now **${pp}/person** (${result['price_total_2_adults']} for 2) on {result['airline']} ({stops_str})"
                )
            elif pp <= threshold:
                alerts.append(
                    f"🔥 **LOW PRICE ALERT: {orig} → {dest}** ({label}: {dep} to {ret}) is **${pp}/person** "
                    f"(below ${threshold} target!) on {result['airline']} ({stops_str})"
                )

            history[key] = result

    STATE_FILE.write_text(json.dumps(history, indent=2))
    if alerts:
        send_webhook(webhook_url, "🏂 **Snowboarding Flight Price Update**\n" + "\n".join(alerts))
    else:
        print("Scan complete. No price changes or new low-price threshold triggers.")


if __name__ == "__main__":
    main()
