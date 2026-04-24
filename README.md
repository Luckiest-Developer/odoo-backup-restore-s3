# Yahoo Finance CLI

A lightweight command-line wrapper around [yfinance](https://github.com/ranaroussi/yfinance).

## Install

```bash
pip install -r requirements.txt
chmod +x yfinance_cli.py
```

## Usage

```
python yfinance_cli.py [-f {table,csv,json}] COMMAND SYMBOL [options]
```

### Commands

| Command | Description |
|---|---|
| `info` | Full ticker metadata & fundamentals |
| `fast-info` | Lightweight real-time price info |
| `history` | Historical OHLCV price data |
| `options-expiries` | List available options expiration dates |
| `options-chain` | Full options chain (calls + puts) |
| `dividends` | Dividend payment history |
| `splits` | Stock split history |
| `financials` | Income statement / balance sheet / cash flow |
| `recommendations` | Analyst buy/sell recommendations |
| `earnings` | Earnings history |
| `holders` | Major or institutional holders |
| `news` | Recent news articles |

### Examples

```bash
# Current price and market cap
python yfinance_cli.py fast-info AAPL

# Specific field only
python yfinance_cli.py fast-info AAPL --field lastPrice

# 3-month daily history as CSV
python yfinance_cli.py -f csv history TSLA --period 3mo

# 1-minute intraday bars
python yfinance_cli.py history NVDA --period 1d --interval 1m

# Custom date range
python yfinance_cli.py history MSFT --start 2024-01-01 --end 2024-06-30

# List options expiry dates
python yfinance_cli.py options-expiries SPY

# Full options chain for nearest expiry (JSON)
python yfinance_cli.py -f json options-chain SPY

# Only calls for a specific expiry
python yfinance_cli.py options-chain SPY --date 2025-01-17 --side calls

# Annual income statement
python yfinance_cli.py financials AAPL --table income

# Quarterly balance sheet
python yfinance_cli.py financials AAPL --table balance --quarterly

# Recent news headlines
python yfinance_cli.py news AMZN --limit 5
```

### Output formats

Pass `-f` / `--format` before the subcommand:

```bash
python yfinance_cli.py -f json  history AAPL --period 1mo
python yfinance_cli.py -f csv   history AAPL --period 1mo
python yfinance_cli.py -f table history AAPL --period 1mo   # default
```
