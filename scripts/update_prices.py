#!/usr/bin/env python3
"""
update_prices.py

This script is intended to run in a GitHub Actions workflow.  It reads a
``watchlist.json`` file from the root of the repository, fetches the latest
prices for each asset in the watchlist using public Yahoo Finance endpoints,
updates the watchlist with the current price and timestamp, and, if
configured, sends email alerts when prices cross user‑defined thresholds.

Environment variables used:

* ``SMTP_EMAIL`` and ``SMTP_PASSWORD`` – credentials for connecting to the
  user's Google (Gmail) account via SMTP.  These should be stored as
  repository secrets.  See the README for instructions.
* ``ALERT_EMAIL`` – email address that receives price alerts.  Defaults to
  ``SMTP_EMAIL`` if not provided.

The script also maintains an ``alerts_log.json`` file to avoid sending
duplicate alerts.  Each alert is recorded with a timestamp to ensure that
notifications are only sent when prices recross the thresholds.

This script requires only the standard library and therefore works out of
the box in GitHub Actions without any additional dependencies.
"""

import base64
import datetime as _dt
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Any, List


def fetch_price(symbol: str) -> float:
    """Fetch the current market price for a given asset symbol.

    Yahoo Finance uses ticker symbols to represent both stocks and
    cryptocurrencies.  Crypto tickers generally use the ``-USD`` suffix
    (e.g. ``BTC-USD``).  This function makes a GET request to the
    ``query1.finance.yahoo.com`` quote endpoint and parses the JSON
    response to extract the ``regularMarketPrice``.

    Parameters
    ----------
    symbol:
        The ticker symbol of the asset (e.g. ``AAPL`` or ``BTC-USD``).

    Returns
    -------
    float
        The last traded price of the asset.

    Raises
    ------
    RuntimeError
        If the price cannot be retrieved (e.g. due to network errors or
        missing fields).
    """
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={urllib.parse.quote(symbol)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Error fetching price for {symbol}: {exc}") from exc

    try:
        result = data["quoteResponse"]["result"][0]
        price = result["regularMarketPrice"]
        if price is None:
            raise ValueError("No price returned")
        return float(price)
    except Exception as exc:
        raise RuntimeError(f"Malformed response for {symbol}: {data}") from exc


def send_email(subject: str, body: str, sender: str, password: str, recipient: str) -> None:
    """Send an email using Gmail's SMTP server.

    Parameters
    ----------
    subject:
        The subject line of the email.
    body:
        The plain‑text body of the email.
    sender:
        The Gmail address used to send the email.
    password:
        The password or app password associated with ``sender``.
    recipient:
        The email address to which the alert will be sent.

    Notes
    -----
    Gmail requires that an app password be created if two‑factor
    authentication is enabled.  See the README for more details.
    """
    context = ssl.create_default_context()
    message = f"Subject: {subject}\n\n{body}"
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, message)


def load_json_file(path: str) -> Any:
    """Load a JSON file and return its contents, or a default value if it
    does not exist or cannot be parsed."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json_file(path: str, data: Any) -> None:
    """Write data to a JSON file with pretty formatting."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, path)


def fetch_historical(symbol: str, interval: str, range_param: str) -> List[Dict[str, Any]]:
    """Fetch historical OHLC data for a symbol from Yahoo Finance.

    Parameters
    ----------
    symbol:
        The ticker symbol (e.g. ``AAPL`` or ``BTC-USD``).
    interval:
        The data interval, e.g. ``1d`` or ``4h``.  Accepts values supported by
        the Yahoo Finance chart API.
    range_param:
        The time range to request, e.g. ``1mo`` or ``3mo``.  Should be long
        enough to populate at least ~50 data points for charting.

    Returns
    -------
    list of dict
        A list of candlestick points with keys ``t`` (Unix timestamp
        milliseconds), ``o``, ``h``, ``l``, ``c``.

    Notes
    -----
    The function catches exceptions and returns an empty list upon failure
    rather than propagating exceptions to the caller.  This avoids breaking
    the entire update cycle if a single symbol fails to fetch.
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
        f"?range={range_param}&interval={interval}&indicators=quote&includeTimestamps=true"
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        chart = data.get("chart", {})
        error = chart.get("error")
        if error:
            return []
        result = chart.get("result", [])[0]
        timestamps = result.get("timestamp", [])
        ohlc = result.get("indicators", {}).get("quote", [{}])[0]
        opens = ohlc.get("open", [])
        highs = ohlc.get("high", [])
        lows = ohlc.get("low", [])
        closes = ohlc.get("close", [])
        points = []
        for ts, o, h, l, c in zip(timestamps, opens, highs, lows, closes):
            if None in (o, h, l, c):
                continue
            points.append({
                "t": int(ts) * 1000,
                "o": float(o),
                "h": float(h),
                "l": float(l),
                "c": float(c)
            })
        return points
    except Exception as exc:
        # Return empty list on failure to avoid interrupting the update process
        print(f"Failed to fetch historical data for {symbol} ({interval}): {exc}", file=sys.stderr)
        return []


def update_watchlist_and_alerts(watchlist: Dict[str, Any], alerts_log: Dict[str, Any]) -> None:
    """Update prices in the watchlist and check for threshold crossings.

    This function mutates the ``watchlist`` and ``alerts_log`` dictionaries in
    place.  After updating all assets, the caller should persist these
    structures back to disk.

    Parameters
    ----------
    watchlist:
        The watchlist dictionary loaded from ``watchlist.json``.  It should
        contain a top‑level key ``assets`` whose value is a list of asset
        entries.
    alerts_log:
        The alerts log dictionary loaded from ``alerts_log.json``.  Its
        structure is {symbol: {"above": timestamp, "below": timestamp}}.
    """
    now_iso = _dt.datetime.utcnow().isoformat() + "Z"
    assets: List[Dict[str, Any]] = watchlist.get("assets", [])
    alerts: Dict[str, Dict[str, str]] = alerts_log.setdefault("alerts", {})

    smtp_email = os.environ.get("SMTP_EMAIL")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    alert_email = os.environ.get("ALERT_EMAIL", smtp_email)
    send_enabled = bool(smtp_email and smtp_password and alert_email)

    for asset in assets:
        symbol = asset.get("symbol")
        if not symbol:
            continue
        try:
            price = fetch_price(symbol)
        except Exception as exc:
            print(exc, file=sys.stderr)
            continue
        asset["last_price"] = price
        asset["last_updated"] = now_iso

        # Generate historical candlestick data for supported intervals.  This
        # allows the front‑end to display charts without having to make live
        # requests from the browser (which may be blocked by CORS).  Only
        # refresh the data once per run to minimize network usage.
        hist_data = {
            "4h": fetch_historical(symbol, "4h", "1mo"),
            "1d": fetch_historical(symbol, "1d", "3mo"),
            "1wk": fetch_historical(symbol, "1wk", "1y"),
        }
        # Write historical data into a separate file under the repo root.  Use
        # a deterministic filename based on the symbol.
        hist_filename = f"historical_{symbol.replace('/', '_')}.json"
        hist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), hist_filename)
        try:
            save_json_file(hist_path, hist_data)
        except Exception as exc:
            print(f"Failed to save historical data for {symbol}: {exc}", file=sys.stderr)

        # Threshold checks
        if not send_enabled:
            continue
        symbol_alerts = alerts.setdefault(symbol, {})
        above_threshold = asset.get("alert_above")
        below_threshold = asset.get("alert_below")
        # Per‑asset email overrides the global alert email if defined.  This
        # allows users to configure different destinations per activo.
        asset_email = asset.get("email")
        recipient_email = asset_email or alert_email

        # Price crosses above threshold
        if above_threshold is not None and price >= above_threshold:
            last_sent = symbol_alerts.get("above")
            # Send only if never sent before or last alert was more than a day ago
            send = False
            if last_sent is None:
                send = True
            else:
                try:
                    last_dt = _dt.datetime.fromisoformat(last_sent.rstrip("Z"))
                    if (_dt.datetime.utcnow() - last_dt).total_seconds() > 86400:
                        send = True
                except Exception:
                    send = True
            if send:
                subject = f"Alerta: {symbol} >= {above_threshold}"
                body = (f"El activo {symbol} ha alcanzado un precio de {price:.2f},\n"
                        f"superando el nivel de alerta establecido ({above_threshold}).\n\n"
                        f"Hora UTC: {now_iso}\n")
                try:
                    send_email(subject, body, smtp_email, smtp_password, recipient_email)
                    symbol_alerts["above"] = now_iso
                    print(f"Sent above alert for {symbol} at {price}")
                except Exception as exc:
                    print(f"Failed to send alert for {symbol}: {exc}", file=sys.stderr)

        # Price crosses below threshold
        if below_threshold is not None and price <= below_threshold:
            last_sent = symbol_alerts.get("below")
            send = False
            if last_sent is None:
                send = True
            else:
                try:
                    last_dt = _dt.datetime.fromisoformat(last_sent.rstrip("Z"))
                    if (_dt.datetime.utcnow() - last_dt).total_seconds() > 86400:
                        send = True
                except Exception:
                    send = True
            if send:
                subject = f"Alerta: {symbol} <= {below_threshold}"
                body = (f"El activo {symbol} ha alcanzado un precio de {price:.2f},\n"
                        f"por debajo del nivel de alerta establecido ({below_threshold}).\n\n"
                        f"Hora UTC: {now_iso}\n")
                try:
                    send_email(subject, body, smtp_email, smtp_password, recipient_email)
                    symbol_alerts["below"] = now_iso
                    print(f"Sent below alert for {symbol} at {price}")
                except Exception as exc:
                    print(f"Failed to send alert for {symbol}: {exc}", file=sys.stderr)


def main() -> None:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    watchlist_path = os.path.join(repo_root, "watchlist.json")
    alerts_log_path = os.path.join(repo_root, "alerts_log.json")

    watchlist = load_json_file(watchlist_path) or {"assets": []}
    alerts_log = load_json_file(alerts_log_path) or {"alerts": {}}

    update_watchlist_and_alerts(watchlist, alerts_log)

    # Save updates back to disk
    save_json_file(watchlist_path, watchlist)
    save_json_file(alerts_log_path, alerts_log)


if __name__ == "__main__":
    main()
