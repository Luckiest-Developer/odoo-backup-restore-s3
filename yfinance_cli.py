#!/usr/bin/env python3
"""Yahoo Finance CLI wrapper — expose yfinance options via subcommands."""

import argparse
import json
import sys

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance is not installed. Run: pip install yfinance")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol.upper())


def _df_to_stdout(df, fmt: str) -> None:
    if df is None or df.empty:
        print("No data returned.")
        return
    if fmt == "json":
        print(df.to_json(orient="records", date_format="iso"))
    elif fmt == "csv":
        print(df.to_csv())
    else:
        print(df.to_string())


def _dict_to_stdout(d: dict, fmt: str) -> None:
    if not d:
        print("No data returned.")
        return
    if fmt == "json":
        print(json.dumps(d, indent=2, default=str))
    else:
        for k, v in d.items():
            print(f"{k}: {v}")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_info(args) -> None:
    """Print ticker metadata/fundamentals."""
    t = _ticker(args.symbol)
    data = t.info
    if args.field:
        val = data.get(args.field)
        print(val if val is not None else f"Field '{args.field}' not found.")
    else:
        _dict_to_stdout(data, args.format)


def cmd_history(args) -> None:
    """Fetch OHLCV history."""
    t = _ticker(args.symbol)
    df = t.history(
        period=args.period,
        interval=args.interval,
        start=args.start,
        end=args.end,
        auto_adjust=not args.no_adjust,
    )
    _df_to_stdout(df, args.format)


def cmd_options_expiries(args) -> None:
    """List available options expiration dates."""
    t = _ticker(args.symbol)
    expiries = t.options
    if not expiries:
        print("No options data available.")
        return
    for exp in expiries:
        print(exp)


def cmd_options_chain(args) -> None:
    """Fetch options chain for a given expiration date."""
    t = _ticker(args.symbol)
    expiries = t.options
    if not expiries:
        sys.exit("No options data available for this ticker.")

    date = args.date or expiries[0]
    if date not in expiries:
        sys.exit(f"Invalid expiry '{date}'. Available: {', '.join(expiries)}")

    chain = t.option_chain(date)

    sides = {
        "calls": chain.calls,
        "puts": chain.puts,
        "both": None,
    }

    side = args.side
    if side == "both":
        print("=== CALLS ===")
        _df_to_stdout(chain.calls, args.format)
        print("\n=== PUTS ===")
        _df_to_stdout(chain.puts, args.format)
    else:
        _df_to_stdout(sides[side], args.format)


def cmd_dividends(args) -> None:
    """Show dividend history."""
    t = _ticker(args.symbol)
    df = t.dividends.reset_index()
    _df_to_stdout(df, args.format)


def cmd_splits(args) -> None:
    """Show stock split history."""
    t = _ticker(args.symbol)
    df = t.splits.reset_index()
    _df_to_stdout(df, args.format)


def cmd_financials(args) -> None:
    """Show income statement, balance sheet, or cash flow."""
    t = _ticker(args.symbol)
    table_map = {
        "income": t.financials,
        "balance": t.balance_sheet,
        "cashflow": t.cashflow,
    }
    df = table_map[args.table]
    if args.quarterly:
        quarterly_map = {
            "income": t.quarterly_financials,
            "balance": t.quarterly_balance_sheet,
            "cashflow": t.quarterly_cashflow,
        }
        df = quarterly_map[args.table]
    _df_to_stdout(df, args.format)


def cmd_recommendations(args) -> None:
    """Show analyst recommendations."""
    t = _ticker(args.symbol)
    df = t.recommendations
    _df_to_stdout(df, args.format)


def cmd_earnings(args) -> None:
    """Show earnings data."""
    t = _ticker(args.symbol)
    df = t.earnings if not args.quarterly else t.quarterly_earnings
    _df_to_stdout(df, args.format)


def cmd_holders(args) -> None:
    """Show major or institutional holders."""
    t = _ticker(args.symbol)
    if args.kind == "major":
        df = t.major_holders
    else:
        df = t.institutional_holders
    _df_to_stdout(df, args.format)


def cmd_news(args) -> None:
    """Show recent news articles."""
    t = _ticker(args.symbol)
    articles = t.news
    if not articles:
        print("No news available.")
        return
    if args.format == "json":
        print(json.dumps(articles[: args.limit], indent=2, default=str))
    else:
        for a in articles[: args.limit]:
            print(f"[{a.get('providerPublishTime', '')}] {a.get('title', '')}")
            print(f"  {a.get('link', '')}\n")


def cmd_fast_info(args) -> None:
    """Show lightweight fast_info fields (price, market cap, etc.)."""
    t = _ticker(args.symbol)
    fi = t.fast_info
    fields = {
        "currency": fi.currency,
        "exchange": fi.exchange,
        "lastPrice": fi.last_price,
        "previousClose": fi.previous_close,
        "open": fi.open,
        "dayHigh": fi.day_high,
        "dayLow": fi.day_low,
        "fiftyTwoWeekHigh": fi.fifty_two_week_high,
        "fiftyTwoWeekLow": fi.fifty_two_week_low,
        "marketCap": fi.market_cap,
        "sharesOutstanding": fi.shares,
        "timezone": fi.timezone,
    }
    if args.field:
        val = fields.get(args.field)
        print(val if val is not None else f"Field '{args.field}' not found.")
    else:
        _dict_to_stdout(fields, args.format)


# ---------------------------------------------------------------------------
# CLI build
# ---------------------------------------------------------------------------

FORMAT_CHOICES = ["table", "csv", "json"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yf",
        description="Yahoo Finance CLI — query stocks, options, financials and more.",
    )
    p.add_argument(
        "-f", "--format",
        choices=FORMAT_CHOICES,
        default="table",
        help="Output format (default: table)",
    )

    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # ---- info ----
    sp = sub.add_parser("info", help="Ticker metadata and fundamentals")
    sp.add_argument("symbol", help="Ticker symbol, e.g. AAPL")
    sp.add_argument("--field", help="Return only a specific field, e.g. marketCap")
    sp.set_defaults(func=cmd_info)

    # ---- fast-info ----
    sp = sub.add_parser("fast-info", help="Lightweight real-time price info")
    sp.add_argument("symbol")
    sp.add_argument("--field", help="Specific field: lastPrice, marketCap, …")
    sp.set_defaults(func=cmd_fast_info)

    # ---- history ----
    sp = sub.add_parser("history", help="Historical OHLCV price data")
    sp.add_argument("symbol")
    sp.add_argument("--period", default="1mo",
                    help="Valid: 1d 5d 1mo 3mo 6mo 1y 2y 5y 10y ytd max (default: 1mo)")
    sp.add_argument("--interval", default="1d",
                    help="Valid: 1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo (default: 1d)")
    sp.add_argument("--start", help="Start date YYYY-MM-DD (overrides --period)")
    sp.add_argument("--end", help="End date YYYY-MM-DD")
    sp.add_argument("--no-adjust", action="store_true",
                    help="Disable auto-adjustment for splits/dividends")
    sp.set_defaults(func=cmd_history)

    # ---- options-expiries ----
    sp = sub.add_parser("options-expiries", help="List available options expiration dates")
    sp.add_argument("symbol")
    sp.set_defaults(func=cmd_options_expiries)

    # ---- options-chain ----
    sp = sub.add_parser("options-chain", help="Fetch options chain for an expiration date")
    sp.add_argument("symbol")
    sp.add_argument("--date", help="Expiration date (default: nearest available)")
    sp.add_argument("--side", choices=["calls", "puts", "both"], default="both",
                    help="Which side of the chain to show (default: both)")
    sp.set_defaults(func=cmd_options_chain)

    # ---- dividends ----
    sp = sub.add_parser("dividends", help="Dividend history")
    sp.add_argument("symbol")
    sp.set_defaults(func=cmd_dividends)

    # ---- splits ----
    sp = sub.add_parser("splits", help="Stock split history")
    sp.add_argument("symbol")
    sp.set_defaults(func=cmd_splits)

    # ---- financials ----
    sp = sub.add_parser("financials", help="Income statement, balance sheet, or cash flow")
    sp.add_argument("symbol")
    sp.add_argument("--table", choices=["income", "balance", "cashflow"], default="income",
                    help="Which financial table (default: income)")
    sp.add_argument("--quarterly", action="store_true", help="Quarterly instead of annual")
    sp.set_defaults(func=cmd_financials)

    # ---- recommendations ----
    sp = sub.add_parser("recommendations", help="Analyst recommendations")
    sp.add_argument("symbol")
    sp.set_defaults(func=cmd_recommendations)

    # ---- earnings ----
    sp = sub.add_parser("earnings", help="Earnings data")
    sp.add_argument("symbol")
    sp.add_argument("--quarterly", action="store_true")
    sp.set_defaults(func=cmd_earnings)

    # ---- holders ----
    sp = sub.add_parser("holders", help="Major or institutional holders")
    sp.add_argument("symbol")
    sp.add_argument("--kind", choices=["major", "institutional"], default="institutional")
    sp.set_defaults(func=cmd_holders)

    # ---- news ----
    sp = sub.add_parser("news", help="Recent news articles")
    sp.add_argument("symbol")
    sp.add_argument("--limit", type=int, default=10, help="Max articles to show (default: 10)")
    sp.set_defaults(func=cmd_news)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # propagate global --format into subcommand namespace
    if not hasattr(args, "format"):
        args.format = "table"

    args.func(args)


if __name__ == "__main__":
    main()
