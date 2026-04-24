#!/usr/bin/env python3
"""
KSA REIT Comprehensive Analyser
Metrics: price, performance, dividend yield, market cap,
         drawdown (dip ratio), and Price-to-NAV (undervalue signal).
"""

import sys
import warnings
import argparse
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
    import pandas as pd
    from tabulate import tabulate
except ImportError:
    sys.exit("Run: pip install yfinance pandas tabulate")


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

REITS = {
    "4330.SR": "Riyad REIT",
    "4331.SR": "AlJazira REIT",
    "4332.SR": "Jadwa REIT AlHaramain",
    "4333.SR": "Taleem REIT",
    "4334.SR": "Al Maather REIT",
    "4335.SR": "Musharaka REIT",
    "4336.SR": "Mulkia Gulf REIT",
    "4337.SR": "Al Azizia REIT",
    "4338.SR": "AlAhli REIT 1",
    "4339.SR": "Derayah REIT",
    "4340.SR": "Al Rajhi REIT",
    "4342.SR": "Jadwa REIT Saudi",
    "4344.SR": "SEDCO Capital REIT",
    "4345.SR": "Alinma Retail REIT",
    "4346.SR": "MEFIC REIT",
    "4347.SR": "Bonyan REIT",
    "4348.SR": "Alkhabeer REIT",
    "4349.SR": "Alinma Hospitality REIT",
    "4350.SR": "Alistithmar REIT",
    "4351.SR": "SICO Saudi REIT",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(val) -> str:
    if val is None or (isinstance(val, float) and (val != val)):
        return "N/A"
    return f"{val:+.2f}%"


def _sar(val, decimals=2) -> str:
    if val is None or (isinstance(val, float) and (val != val)):
        return "N/A"
    return f"{val:,.{decimals}f}"


def _mcap(val) -> str:
    """Format market cap in millions SAR."""
    if val is None or (isinstance(val, float) and (val != val)):
        return "N/A"
    return f"{val / 1_000_000:,.1f}M"


def _nav_signal(pb) -> str:
    """Convert P/B to a human-readable NAV signal."""
    if pb is None:
        return "N/A"
    if pb < 0.70:
        return f"Deep discount ({pb:.2f}x)"
    if pb < 0.90:
        return f"Discount      ({pb:.2f}x)"
    if pb <= 1.10:
        return f"Fair value    ({pb:.2f}x)"
    return f"Premium       ({pb:.2f}x)"


def _return_pct(hist: pd.DataFrame, days: int) -> float | None:
    """Compute price return over the last `days` calendar days."""
    if hist.empty:
        return None
    # Use iloc-based slicing to avoid any tz comparison issues
    cutoff = hist.index[-1] - pd.Timedelta(days=days)
    past = hist[hist.index <= cutoff]
    if past.empty:
        return None
    start_price = float(past["Close"].iloc[-1])
    end_price = float(hist["Close"].iloc[-1])
    if start_price == 0:
        return None
    return (end_price - start_price) / start_price * 100


def _ytd_return(hist: pd.DataFrame) -> float | None:
    last = hist.index[-1]
    # Build a tz-aware Timestamp matching the index timezone
    year_start = pd.Timestamp(last.year, 1, 1, tz=last.tzinfo)
    past = hist[hist.index < year_start]
    if past.empty:
        past_price = float(hist["Close"].iloc[0])
    else:
        past_price = float(past["Close"].iloc[-1])
    end_price = float(hist["Close"].iloc[-1])
    if past_price == 0:
        return None
    return (end_price - past_price) / past_price * 100


def _annual_dividend(ticker_obj: yf.Ticker) -> float | None:
    """Sum dividends paid in the last 12 months."""
    try:
        divs = ticker_obj.dividends
        if divs.empty:
            return None
        cutoff = divs.index[-1] - timedelta(days=365)
        recent = divs[divs.index > cutoff]
        return float(recent.sum()) if not recent.empty else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Data fetcher
# ---------------------------------------------------------------------------

def fetch_reit(symbol: str, name: str) -> dict:
    row = {"Ticker": symbol.replace(".SR", ""), "Name": name}
    try:
        t = yf.Ticker(symbol)

        # --- price history (1 year + a bit) ---
        hist = t.history(period="13mo", auto_adjust=True)

        if hist.empty:
            row["Status"] = "No data"
            return row

        price = float(hist["Close"].iloc[-1])
        high52 = float(hist["High"].max())
        low52  = float(hist["Low"].min())

        # Dip ratio: how far below the 52-week high (negative = dipped)
        dip_ratio = (price - high52) / high52 * 100

        # Performance
        ret_1m  = _return_pct(hist, 30)
        ret_3m  = _return_pct(hist, 91)
        ret_6m  = _return_pct(hist, 182)
        ret_1y  = _return_pct(hist, 365)
        ret_ytd = _ytd_return(hist)

        # Dividends
        annual_div = _annual_dividend(t)
        div_yield  = (annual_div / price * 100) if annual_div and price else None

        # Fundamentals from info
        info = {}
        try:
            info = t.info
        except Exception:
            pass

        market_cap  = info.get("marketCap")
        price_book  = info.get("priceToBook")     # P/B ≈ P/NAV for REITs
        book_value  = info.get("bookValue")        # NAV per unit

        # Discount to NAV
        nav_discount = None
        if price_book and price_book > 0:
            nav_discount = (1 - price_book) * 100  # positive = trading below NAV

        row.update({
            "Price (SAR)":      price,
            "Mkt Cap":          market_cap,
            "1M %":             ret_1m,
            "3M %":             ret_3m,
            "6M %":             ret_6m,
            "1Y %":             ret_1y,
            "YTD %":            ret_ytd,
            "52W High":         high52,
            "52W Low":          low52,
            "Dip from High %":  dip_ratio,
            "Div/Unit (SAR)":   annual_div,
            "Div Yield %":      div_yield,
            "Book/NAV (SAR)":   book_value,
            "P/NAV (x)":        price_book,
            "Disc/Prem %":      nav_discount,
        })

    except Exception as e:
        row["Status"] = str(e)

    return row


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_table(rows: list[dict], fmt: str) -> None:
    if fmt == "json":
        import json
        print(json.dumps(rows, indent=2, default=str))
        return

    if fmt == "csv":
        df = pd.DataFrame(rows)
        print(df.to_csv(index=False))
        return

    # Pretty table
    display_rows = []
    for r in rows:
        if "Status" in r:
            display_rows.append([
                r["Ticker"], r["Name"], r.get("Status", "Error"),
                *["—"] * 14
            ])
            continue

        disc = r.get("Disc/Prem %")
        disc_str = "N/A"
        if disc is not None:
            disc_str = f"{disc:+.1f}%"

        pnav = r.get("P/NAV (x)")
        pnav_str = f"{pnav:.3f}x" if pnav else "N/A"

        display_rows.append([
            r["Ticker"],
            r["Name"][:22],
            _sar(r.get("Price (SAR)")),
            _mcap(r.get("Mkt Cap")),
            _pct(r.get("1M %")),
            _pct(r.get("3M %")),
            _pct(r.get("6M %")),
            _pct(r.get("1Y %")),
            _pct(r.get("YTD %")),
            _pct(r.get("Dip from High %")),
            _sar(r.get("Div/Unit (SAR)"), 3),
            f"{r['Div Yield %']:.2f}%" if r.get("Div Yield %") else "N/A",
            _sar(r.get("Book/NAV (SAR)")),
            pnav_str,
            disc_str,
        ])

    headers = [
        "Ticker", "Name", "Price\n(SAR)", "Mkt Cap",
        "1M", "3M", "6M", "1Y", "YTD",
        "Dip from\n52W High",
        "Div/Unit\n(SAR)", "Div\nYield",
        "Book/NAV\n(SAR)", "P/NAV", "Disc(+)\nPrem(-)",
    ]

    print(tabulate(display_rows, headers=headers, tablefmt="rounded_outline",
                   stralign="right", numalign="right"))

    # Legend
    print()
    print("  P/NAV  : Price-to-Net Asset Value  (< 1.0 = trading below NAV = undervalued)")
    print("  Disc(+): Positive = discount to NAV (undervalued), Negative = premium")
    print("  Dip    : % below 52-week high  (0% = at all-time high, −30% = deep dip)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ksa_reits",
        description="KSA REIT analyser — performance, dividends, valuation",
    )
    p.add_argument(
        "-f", "--format", choices=["table", "csv", "json"], default="table",
        help="Output format (default: table)",
    )
    p.add_argument(
        "--ticker", metavar="TICKER",
        help="Analyse a single ticker only, e.g. 4340",
    )
    p.add_argument(
        "--sort", metavar="COL",
        choices=["price", "mcap", "1y", "ytd", "yield", "pnav", "dip"],
        default=None,
        help="Sort by: price | mcap | 1y | ytd | yield | pnav | dip",
    )
    p.add_argument(
        "--undervalued", action="store_true",
        help="Show only REITs trading below NAV (P/NAV < 1.0)",
    )
    return p


SORT_KEY_MAP = {
    "price": "Price (SAR)",
    "mcap":  "Mkt Cap",
    "1y":    "1Y %",
    "ytd":   "YTD %",
    "yield": "Div Yield %",
    "pnav":  "P/NAV (x)",
    "dip":   "Dip from High %",
}


def main() -> None:
    args = build_parser().parse_args()

    universe = REITS
    if args.ticker:
        sym = args.ticker.upper()
        if not sym.endswith(".SR"):
            sym += ".SR"
        if sym not in REITS:
            sys.exit(f"Unknown ticker '{sym}'. Available: {', '.join(REITS)}")
        universe = {sym: REITS[sym]}

    print(f"Fetching data for {len(universe)} KSA REITs …\n", flush=True)

    rows = []
    for symbol, name in universe.items():
        print(f"  {symbol:<12} {name}", flush=True)
        rows.append(fetch_reit(symbol, name))

    print()

    # Filter
    if args.undervalued:
        rows = [r for r in rows if r.get("P/NAV (x)") is not None and r["P/NAV (x)"] < 1.0]
        print(f"Showing {len(rows)} REITs trading below NAV\n")

    # Sort
    if args.sort:
        key = SORT_KEY_MAP[args.sort]
        rows.sort(key=lambda r: (r.get(key) is None, r.get(key) or 0))

    print_table(rows, args.format)


if __name__ == "__main__":
    main()
