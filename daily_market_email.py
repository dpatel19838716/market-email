#!/usr/bin/env python3
"""
Daily market update emailer: US tech stocks, gold, and US dollar.

Setup:
    pip install yfinance

Environment variables (set these, don't hardcode passwords):
    SMTP_USER   your sending address, e.g. you@gmail.com
    SMTP_PASS   an app password (Gmail: Google Account > Security > App passwords)
    EMAIL_TO    where to send the update (can equal SMTP_USER)
    SMTP_HOST   optional, default smtp.gmail.com
    SMTP_PORT   optional, default 465 (SSL)

Run:  python daily_market_email.py
Use --dry-run to print the HTML to a file instead of emailing.
"""
import os
import sys
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import yfinance as yf

# ---- Edit these lists to customise ----
INDICES = {"^IXIC": "Nasdaq Composite", "^NDX": "Nasdaq 100", "^GSPC": "S&P 500", "XLK": "Tech Sector ETF (XLK)"}
TECH_STOCKS = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "META": "Meta", "TSLA": "Tesla", "AVGO": "Broadcom",
    "AMD": "AMD", "ORCL": "Oracle",
}
GOLD = {"GC=F": "Gold futures (US$/oz)", "GLD": "SPDR Gold ETF (GLD)"}
CURRENCY = {
    "DX-Y.NYB": "US Dollar Index (DXY)", "AUDUSD=X": "AUD/USD", "EURUSD=X": "EUR/USD",
    "USDJPY=X": "USD/JPY", "^TNX": "US 10-yr yield (%)",
}


def quote(symbol):
    """Return (last, prev_close, change, pct, as_of_date) or None."""
    try:
        h = yf.Ticker(symbol).history(period="7d")["Close"].dropna()
        if len(h) < 2:
            return None
        last, prev = float(h.iloc[-1]), float(h.iloc[-2])
        return last, prev, last - prev, (last - prev) / prev * 100, h.index[-1].strftime("%d %b")
    except Exception as e:
        print(f"Warning: could not fetch {symbol}: {e}", file=sys.stderr)
        return None


def build_rows(group):
    rows = []
    for sym, name in group.items():
        q = quote(sym)
        rows.append((sym, name, q))
    return rows


def table_html(title, rows):
    out = [f"<h3 style='margin:24px 0 6px'>{title}</h3>",
           "<table style='border-collapse:collapse;width:100%;font-size:14px'>",
           "<tr style='background:#f0f0f0;text-align:left'><th style='padding:6px'>Name</th>"
           "<th style='padding:6px;text-align:right'>Last</th>"
           "<th style='padding:6px;text-align:right'>Change</th>"
           "<th style='padding:6px;text-align:right'>%</th></tr>"]
    for sym, name, q in rows:
        if q is None:
            out.append(f"<tr><td style='padding:6px'>{name} ({sym})</td><td colspan='3' "
                       "style='padding:6px;text-align:right;color:#888'>unavailable</td></tr>")
            continue
        last, _, chg, pct, _ = q
        colour = "#0a7d32" if chg >= 0 else "#c0222b"
        out.append(
            f"<tr style='border-bottom:1px solid #e5e5e5'>"
            f"<td style='padding:6px'>{name} <span style='color:#888'>({sym})</span></td>"
            f"<td style='padding:6px;text-align:right'>{last:,.2f}</td>"
            f"<td style='padding:6px;text-align:right;color:{colour}'>{chg:+,.2f}</td>"
            f"<td style='padding:6px;text-align:right;color:{colour}'>{pct:+.2f}%</td></tr>")
    out.append("</table>")
    return "\n".join(out)


def movers_html(stock_rows):
    valid = [(n, s, q) for s, n, q in stock_rows if q]
    if not valid:
        return ""
    valid.sort(key=lambda x: x[2][3], reverse=True)
    best, worst = valid[0], valid[-1]
    return (f"<p style='margin:12px 0'><b>Top mover:</b> {best[0]} ({best[2][3]:+.2f}%) &nbsp;|&nbsp; "
            f"<b>Weakest:</b> {worst[0]} ({worst[2][3]:+.2f}%)</p>")


def headlines_html(limit=6):
    try:
        news = yf.Ticker("^GSPC").news or []
        items = []
        for n in news[:limit]:
            c = n.get("content", n)
            title = c.get("title")
            link = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
            if title:
                items.append(f"<li><a href='{link}'>{title}</a></li>" if link else f"<li>{title}</li>")
        if items:
            return "<h3 style='margin:24px 0 6px'>Headlines</h3><ul>" + "".join(items) + "</ul>"
    except Exception as e:
        print(f"Warning: headlines unavailable: {e}", file=sys.stderr)
    return ""


def gold_aud_line(gold_rows):
    """Approximate gold price in AUD from gold futures and AUD/USD."""
    try:
        g = quote("GC=F")
        a = quote("AUDUSD=X")
        if g and a:
            return (f"<p style='margin:12px 0'><b>Gold in AUD (approx.):</b> A${g[0] / a[0]:,.2f}/oz</p>")
    except Exception:
        pass
    return ""


def build_email():
    idx, stocks = build_rows(INDICES), build_rows(TECH_STOCKS)
    gold, fx = build_rows(GOLD), build_rows(CURRENCY)
    as_of = next((q[4] for _, _, q in idx if q), "latest close")
    now = datetime.now().strftime("%A %d %B %Y")

    html = f"""<html><body style='font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:auto;color:#222'>
<h2 style='margin-bottom:2px'>Daily Market Update</h2>
<div style='color:#777;font-size:13px'>{now} &middot; US data as of close {as_of}</div>
{table_html("US Indices", idx)}
{table_html("Big Tech Stocks", stocks)}
{movers_html(stocks)}
{table_html("Gold", gold)}
{gold_aud_line(gold)}
{table_html("US Dollar &amp; Rates", fx)}
{headlines_html()}
<p style='color:#999;font-size:11px;margin-top:30px'>Data via Yahoo Finance (may be delayed).
For information only, not financial advice.</p>
</body></html>"""
    return f"Market Update: {now}", html


def send(subject, html):
    user, pw, to = os.environ["SMTP_USER"], os.environ["SMTP_PASS"], os.environ["EMAIL_TO"]
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText("Please view this email in an HTML-capable client.", "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL(host, port) as s:
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())


if __name__ == "__main__":
    subject, html = build_email()
    if "--dry-run" in sys.argv:
        with open("preview.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Saved preview.html")
    else:
        send(subject, html)
        print("Email sent.")
