#!/usr/bin/env python3
"""
KSA REIT table builder
======================
Columns are defined in a YAML file. Each column is either:
  field : a direct key from the data bag (no calculation)
  expr  : a Python expression evaluated against the data bag

Run:
  python ksa_reits.py                        # default columns
  python ksa_reits.py --columns my.yaml      # custom columns
  python ksa_reits.py --list-fields          # show all available fields
  python ksa_reits.py --undervalued          # P/NAV < 1 only
  python ksa_reits.py --sort yield           # sort by named column alias
"""

import sys, argparse, warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")

# ── third-party ──────────────────────────────────────────────────────────────
try:
    import yfinance as yf
    import pandas as pd
    import yaml
    from tabulate import tabulate
except ImportError as e:
    sys.exit(f"Missing dependency — run: pip install yfinance pandas tabulate pyyaml\n{e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  UNIVERSE
# ═══════════════════════════════════════════════════════════════════════════════

REITS: dict[str, str] = {
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


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  DATA BAG — one flat dict per ticker
#     ∙ All keys here are usable as `field` in YAML columns
#     ∙ All keys are also available as variables inside `expr` expressions
# ═══════════════════════════════════════════════════════════════════════════════

def _pct_change(hist: pd.DataFrame, days: int) -> float | None:
    if hist.empty:
        return None
    cutoff = hist.index[-1] - pd.Timedelta(days=days)
    past = hist[hist.index <= cutoff]
    if past.empty:
        return None
    s = float(past["Close"].iloc[-1])
    e = float(hist["Close"].iloc[-1])
    return (e - s) / s * 100 if s else None


def _ytd(hist: pd.DataFrame) -> float | None:
    if hist.empty:
        return None
    last = hist.index[-1]
    year_start = pd.Timestamp(last.year, 1, 1, tz=last.tzinfo)
    past = hist[hist.index < year_start]
    s = float(past["Close"].iloc[-1]) if not past.empty else float(hist["Close"].iloc[0])
    e = float(hist["Close"].iloc[-1])
    return (e - s) / s * 100 if s else None


def _annual_div(t: yf.Ticker) -> float | None:
    try:
        d = t.dividends
        if d.empty:
            return None
        cutoff = d.index[-1] - pd.Timedelta(days=365)
        recent = d[d.index > cutoff]
        return float(recent.sum()) if not recent.empty else None
    except Exception:
        return None


def build_data_bag(symbol: str, name: str) -> dict:
    """
    Returns a flat dict with every data point available for expression use.
    Keys are grouped into:
      identity  : ticker, symbol, name
      price     : price, prev_close, open, day_high, day_low, high_52w, low_52w
      market    : market_cap, shares
      perf      : ret_1m, ret_3m, ret_6m, ret_1y, ret_ytd
      dividend  : annual_div
      valuation : price_book, book_value, nav_discount
      raw_info  : every key from yf.Ticker.info (prefixed as-is)
    """
    bag: dict = {
        "ticker": symbol.replace(".SR", ""),
        "symbol": symbol,
        "name":   name,
        "_ok":    False,
        "_error": None,
    }

    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="13mo", auto_adjust=True)

        if hist.empty:
            bag["_error"] = "no data"
            return bag

        price   = float(hist["Close"].iloc[-1])
        high_52 = float(hist["High"].max())
        low_52  = float(hist["Low"].min())
        ann_div = _annual_div(t)

        # ── price ───────────────────────────────────────────────────────────
        bag["price"]      = price
        bag["high_52w"]   = high_52
        bag["low_52w"]    = low_52
        bag["prev_close"] = float(hist["Close"].iloc[-2]) if len(hist) > 1 else None
        bag["open"]       = float(hist["Open"].iloc[-1])
        bag["day_high"]   = float(hist["High"].iloc[-1])
        bag["day_low"]    = float(hist["Low"].iloc[-1])
        bag["volume"]     = float(hist["Volume"].iloc[-1])

        # ── performance ─────────────────────────────────────────────────────
        bag["ret_1m"]  = _pct_change(hist, 30)
        bag["ret_3m"]  = _pct_change(hist, 91)
        bag["ret_6m"]  = _pct_change(hist, 182)
        bag["ret_1y"]  = _pct_change(hist, 365)
        bag["ret_ytd"] = _ytd(hist)

        # ── dividend ────────────────────────────────────────────────────────
        bag["annual_div"] = ann_div
        bag["div_yield"]  = (ann_div / price * 100) if ann_div and price else None

        # ── raw yfinance info (all fields) ──────────────────────────────────
        info: dict = {}
        try:
            info = t.info or {}
        except Exception:
            pass

        # flatten info into bag (so exprs can use e.g. `marketCap` directly)
        for k, v in info.items():
            if k not in bag:          # don't overwrite computed keys
                bag[k] = v

        # ── convenience aliases for common info fields ───────────────────────
        bag["market_cap"]  = info.get("marketCap")
        bag["shares"]      = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
        bag["price_book"]  = info.get("priceToBook")
        bag["book_value"]  = info.get("bookValue")
        bag["nav_discount"] = ((1 - bag["price_book"]) * 100) if bag["price_book"] else None
        bag["dip_from_high"] = ((price - high_52) / high_52 * 100) if high_52 else None
        bag["range_position"] = (
            (price - low_52) / (high_52 - low_52) * 100
            if (high_52 and low_52 and high_52 != low_52) else None
        )
        bag["trailing_pe"] = info.get("trailingPE")
        bag["forward_pe"]  = info.get("forwardPE")
        bag["beta"]        = info.get("beta")
        bag["currency"]    = info.get("currency", "SAR")

        bag["_ok"] = True

    except Exception as e:
        bag["_error"] = str(e)

    return bag


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  FORMATTERS
# ═══════════════════════════════════════════════════════════════════════════════

_NA = "N/A"

def _fmt(value, spec: str | None) -> str:
    """Apply a format spec to a value. spec can be a Python format string or a
    named formatter: pct | pct_plain | sar | mcap | x | int | raw"""
    if value is None or (isinstance(value, float) and value != value):
        return _NA

    if spec is None:
        return str(value) if not isinstance(value, float) else f"{value:.4g}"

    named = {
        "pct":       lambda v: f"{v:+.2f}%",
        "pct_plain": lambda v: f"{v:.2f}%",
        "sar":       lambda v: f"{v:,.2f}",
        "mcap":      lambda v: (
            f"{v/1e9:,.2f}B" if abs(v) >= 1e9 else f"{v/1e6:,.1f}M"
        ),
        "x":         lambda v: f"{v:.3f}x",
        "int":       lambda v: f"{v:,.0f}",
        "raw":       lambda v: str(v),
    }
    if spec in named:
        try:
            return named[spec](value)
        except Exception:
            return _NA

    # treat as Python format string e.g. "{:.2f}%" or "%.2f"
    try:
        if "{" in spec:
            return spec.format(value)
        return spec % value
    except Exception:
        return _NA


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  COLUMN ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class _SafeNamespace(dict):
    """Dict that returns None for missing keys so exprs never raise NameError."""
    def __missing__(self, key):
        return None


def resolve_column(col_def: dict, bag: dict) -> str:
    """
    col_def keys:
      header : str            column header (supports \n for line breaks)
      field  : str            direct key lookup in bag
      expr   : str            Python expression; bag variables are in scope
      fmt    : str | None     formatter (see _fmt)
      width  : int | None     truncate string to this width
    """
    fmt   = col_def.get("fmt")
    width = col_def.get("width")

    raw = None
    try:
        if "field" in col_def:
            raw = bag.get(col_def["field"])
        elif "expr" in col_def:
            ns = _SafeNamespace(bag)
            raw = eval(col_def["expr"], {"__builtins__": {}}, ns)   # noqa: S307
        # coerce non-numeric strings from yfinance info fields to None
        if isinstance(raw, str) and fmt not in (None, "raw"):
            raw = None
    except Exception:
        return _NA

    cell = _fmt(raw, fmt)

    if width and isinstance(cell, str) and len(cell) > width:
        cell = cell[: width - 1] + "…"

    return cell


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  DEFAULT COLUMN SPEC (used when no --columns file is given)
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_COLUMNS: list[dict] = [
    {"header": "Ticker",         "field": "ticker",        "align": "left"},
    {"header": "Name",           "field": "name",          "align": "left", "width": 22},
    {"header": "Price\n(SAR)",   "field": "price",         "fmt": "{:.2f}"},
    {"header": "Mkt Cap",        "field": "market_cap",    "fmt": "mcap"},
    {"header": "1M",             "field": "ret_1m",        "fmt": "pct"},
    {"header": "3M",             "field": "ret_3m",        "fmt": "pct"},
    {"header": "6M",             "field": "ret_6m",        "fmt": "pct"},
    {"header": "1Y",             "field": "ret_1y",        "fmt": "pct"},
    {"header": "YTD",            "field": "ret_ytd",       "fmt": "pct"},
    {"header": "Dip from\n52W High",
                                 "field": "dip_from_high", "fmt": "pct"},
    {"header": "52W\nPosition",
     "expr": "range_position",   "fmt": "{:.0f}%",
     "header": "52W Pos\n(lo→hi)"},
    {"header": "Div/Unit\n(SAR)","field": "annual_div",    "fmt": "{:.3f}"},
    {"header": "Div\nYield",     "field": "div_yield",     "fmt": "pct_plain"},
    {"header": "Book/NAV\n(SAR)","field": "book_value",    "fmt": "{:.2f}"},
    {"header": "P/NAV",          "field": "price_book",    "fmt": "x"},
    {"header": "Disc(+)\nPrem(-)",
                                 "field": "nav_discount",  "fmt": "{:+.1f}%"},
]

# ─── Example custom column files (written to disk for reference) ──────────────
EXAMPLE_DIVIDEND_YAML = """\
# dividend_table.yaml — yield-focused columns
# Run: python ksa_reits.py --columns dividend_table.yaml --sort yield
columns:
  - header: "Ticker"
    field: ticker
    align: left

  - header: "Name"
    field: name
    align: left
    width: 22

  - header: "Price"
    field: price
    fmt: "{:.2f}"

  - header: "Div/Unit"
    field: annual_div
    fmt: "{:.3f}"

  - header: "Yield %"
    field: div_yield
    fmt: pct_plain

  - header: "Yield on\n52W Low"
    expr: "annual_div / low_52w * 100 if (annual_div and low_52w) else None"
    fmt: pct_plain

  - header: "Payout\nCover (x)"
    expr: "trailingPE / (price / annual_div) if (trailingPE and annual_div and price) else None"
    fmt: "{:.2f}x"

  - header: "Mkt Cap"
    field: market_cap
    fmt: mcap
"""

EXAMPLE_VALUATION_YAML = """\
# valuation_table.yaml — NAV / undervalue focus
# Run: python ksa_reits.py --columns valuation_table.yaml --sort pnav
columns:
  - header: "Ticker"
    field: ticker
    align: left

  - header: "Name"
    field: name
    align: left
    width: 22

  - header: "Price\n(SAR)"
    field: price
    fmt: "{:.2f}"

  - header: "Book/NAV\n(SAR)"
    field: book_value
    fmt: "{:.2f}"

  - header: "P/NAV"
    field: price_book
    fmt: x

  - header: "Discount\nto NAV %"
    field: nav_discount
    fmt: "{:+.1f}%"

  - header: "Upside to\nNAV (SAR)"
    expr: "book_value - price if (book_value and price) else None"
    fmt: "{:+.2f}"

  - header: "52W High"
    field: high_52w
    fmt: "{:.2f}"

  - header: "Dip %"
    field: dip_from_high
    fmt: pct

  - header: "1Y Perf"
    field: ret_1y
    fmt: pct
"""

EXAMPLE_PERFORMANCE_YAML = """\
# performance_table.yaml — returns across timeframes
# Run: python ksa_reits.py --columns performance_table.yaml --sort 1y
columns:
  - header: "Ticker"
    field: ticker
    align: left

  - header: "Name"
    field: name
    align: left
    width: 22

  - header: "Price"
    field: price
    fmt: "{:.2f}"

  - header: "YTD"
    field: ret_ytd
    fmt: pct

  - header: "1M"
    field: ret_1m
    fmt: pct

  - header: "3M"
    field: ret_3m
    fmt: pct

  - header: "6M"
    field: ret_6m
    fmt: pct

  - header: "1Y"
    field: ret_1y
    fmt: pct

  - header: "Momentum\n(1M-3M avg)"
    expr: "(ret_1m + ret_3m) / 2 if (ret_1m is not None and ret_3m is not None) else None"
    fmt: pct

  - header: "Volatility\nProxy"
    expr: "abs(day_high - day_low) / price * 100 if price else None"
    fmt: "{:.2f}%"
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 6.  RENDER
# ═══════════════════════════════════════════════════════════════════════════════

def render_table(bags: list[dict], col_defs: list[dict], fmt: str) -> None:
    headers = [c["header"] for c in col_defs]

    rows = []
    for bag in bags:
        if not bag["_ok"]:
            err = bag.get("_error", "unknown error")
            row = [bag["ticker"], bag["name"], f"[{err}]"] + ["—"] * max(0, len(col_defs) - 3)
            rows.append(row)
            continue
        rows.append([resolve_column(c, bag) for c in col_defs])

    if fmt == "json":
        import json
        result = []
        for bag in bags:
            result.append({c["header"].replace("\n", " "): resolve_column(c, bag)
                           for c in col_defs})
        print(json.dumps(result, indent=2))
        return

    if fmt == "csv":
        flat_headers = [h.replace("\n", " ") for h in headers]
        print(",".join(flat_headers))
        for row in rows:
            print(",".join(row))
        return

    # detect per-column alignment
    col_align = []
    for c in col_defs:
        col_align.append(c.get("align", "right"))

    print(tabulate(rows, headers=headers, tablefmt="rounded_outline",
                   colalign=col_align))


# ═══════════════════════════════════════════════════════════════════════════════
# 7.  CLI
# ═══════════════════════════════════════════════════════════════════════════════

SORT_ALIASES = {
    "price": "price",
    "mcap":  "market_cap",
    "1m":    "ret_1m",
    "3m":    "ret_3m",
    "6m":    "ret_6m",
    "1y":    "ret_1y",
    "ytd":   "ret_ytd",
    "yield": "div_yield",
    "pnav":  "price_book",
    "dip":   "dip_from_high",
    "nav":   "nav_discount",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ksa_reits",
        description="KSA REIT dynamic table builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Column YAML format:
  columns:
    - header: "My Col"
      field: price          # direct data bag key
      fmt: "{:.2f}"

    - header: "Yield on Low"
      expr: "annual_div / low_52w * 100 if annual_div else None"
      fmt: pct_plain

Named formatters: pct | pct_plain | sar | mcap | x | int | raw
Sort aliases    : price mcap 1m 3m 6m 1y ytd yield pnav dip nav
""",
    )
    p.add_argument("-f", "--format", choices=["table", "csv", "json"],
                   default="table")
    p.add_argument("--columns", metavar="FILE",
                   help="YAML file with column definitions (default: built-in)")
    p.add_argument("--ticker", metavar="TICKER",
                   help="Single ticker, e.g. 4340")
    p.add_argument("--sort", metavar="ALIAS", choices=list(SORT_ALIASES),
                   help=f"Sort ascending by: {', '.join(SORT_ALIASES)}")
    p.add_argument("--desc", action="store_true",
                   help="Reverse sort (descending)")
    p.add_argument("--undervalued", action="store_true",
                   help="Only show REITs with P/NAV < 1.0 (trading below NAV)")
    p.add_argument("--list-fields", action="store_true",
                   help="Fetch one ticker and list all available data bag fields")
    p.add_argument("--write-examples", action="store_true",
                   help="Write example YAML column files to disk and exit")
    return p


def load_col_defs(path: str | None) -> list[dict]:
    if path is None:
        return DEFAULT_COLUMNS
    text = Path(path).read_text()
    data = yaml.safe_load(text)
    return data.get("columns", data)  # support both with/without top-level key


def main() -> None:
    args = build_parser().parse_args()

    # ── write example files ──────────────────────────────────────────────────
    if args.write_examples:
        for fname, content in [
            ("dividend_table.yaml",    EXAMPLE_DIVIDEND_YAML),
            ("valuation_table.yaml",   EXAMPLE_VALUATION_YAML),
            ("performance_table.yaml", EXAMPLE_PERFORMANCE_YAML),
        ]:
            Path(fname).write_text(content)
            print(f"  wrote {fname}")
        print("\nUsage:")
        print("  python ksa_reits.py --columns dividend_table.yaml --sort yield")
        print("  python ksa_reits.py --columns valuation_table.yaml --undervalued")
        print("  python ksa_reits.py --columns performance_table.yaml --sort 1y --desc")
        return

    # ── select universe ──────────────────────────────────────────────────────
    universe = REITS
    if args.ticker:
        sym = args.ticker.upper()
        if not sym.endswith(".SR"):
            sym += ".SR"
        if sym not in REITS:
            sys.exit(f"Unknown ticker '{sym}'")
        universe = {sym: REITS[sym]}

    # ── list-fields mode ─────────────────────────────────────────────────────
    if args.list_fields:
        sym, name = next(iter(universe.items()))
        print(f"Fetching {sym} …\n")
        bag = build_data_bag(sym, name)
        print(f"{'FIELD':<35} {'VALUE'}")
        print("─" * 70)
        for k, v in sorted(bag.items()):
            if k.startswith("_"):
                continue
            disp = str(v)
            if len(disp) > 60:
                disp = disp[:57] + "…"
            print(f"  {k:<33} {disp}")
        print(f"\n  Total fields: {sum(1 for k in bag if not k.startswith('_'))}")
        return

    # ── fetch all ────────────────────────────────────────────────────────────
    print(f"Fetching data for {len(universe)} KSA REITs …\n", flush=True)
    bags: list[dict] = []
    for sym, name in universe.items():
        print(f"  {sym:<12} {name}", flush=True)
        bags.append(build_data_bag(sym, name))

    print()

    # ── filter ───────────────────────────────────────────────────────────────
    if args.undervalued:
        bags = [b for b in bags if b.get("price_book") and b["price_book"] < 1.0]
        print(f"→ {len(bags)} REITs trading below NAV\n")

    # ── sort ─────────────────────────────────────────────────────────────────
    if args.sort:
        key = SORT_ALIASES[args.sort]
        bags.sort(key=lambda b: (b.get(key) is None, b.get(key) or 0),
                  reverse=args.desc)

    # ── column definitions ───────────────────────────────────────────────────
    col_defs = load_col_defs(args.columns)

    # ── render ───────────────────────────────────────────────────────────────
    render_table(bags, col_defs, args.format)

    if args.format == "table":
        print()
        print("  Named formatters : pct | pct_plain | sar | mcap | x | int | raw")
        print("  field            : direct data bag key  (--list-fields to see all)")
        print("  expr             : any Python expression with bag variables in scope")
        print()
        print("  python ksa_reits.py --write-examples   # generate sample YAML files")
        print("  python ksa_reits.py --list-fields       # see all available fields")


if __name__ == "__main__":
    main()
