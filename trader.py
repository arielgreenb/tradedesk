import pandas as pd
"""
TradeDesk Autonomous Trading Bot
Powered by Claude AI + Yahoo Finance + Supabase
Runs on a schedule — no human prompts needed during market hours
"""

import os
import json
import time
from datetime import datetime, date
import pytz

# ── Dependencies ──────────────────────────────────────────────────────────────
import anthropic
import yfinance as yf
from supabase import create_client, Client

# ── Config (loaded from environment variables) ────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SUPABASE_URL      = os.environ.get("SUPABASE_URL")
SUPABASE_KEY      = os.environ.get("SUPABASE_KEY")
STARTING_CASH     = 25000.0

# ── Clients ───────────────────────────────────────────────────────────────────
claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Watchlist ─────────────────────────────────────────────────────────────────
WATCHLIST = ["SPY", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META"]

ET = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────────────────────────────────────
# MARKET HOURS
# ─────────────────────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:          # Saturday / Sunday
        return False
    market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now <= market_close


def market_status_str() -> str:
    now = datetime.now(ET)
    return now.strftime("%A %I:%M %p ET") + (" — OPEN" if is_market_open() else " — CLOSED")


# ─────────────────────────────────────────────────────────────────────────────
# PRICE FETCHING  (Yahoo Finance — no account needed)
# ─────────────────────────────────────────────────────────────────────────────

def get_prices(tickers: list[str]) -> dict:
    """Fetch latest prices for all tickers."""
    prices = {}
    data = yf.download(tickers, period="2d", interval="1d", progress=False)
    for t in tickers:
        try:
            prices[t] = round(float(data["Close"][t].dropna().iloc[-1]), 2)
        except Exception:
            prices[t] = None
    return prices


def get_price_history(ticker: str, days: int = 30) -> list[dict]:
    """Fetch recent daily price history for context."""
    data = yf.download(ticker, period=f"{days}d", interval="1d", progress=False)
    history = []
    # Flatten multi-level columns if present (newer yfinance versions)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    for date_idx, row in data.iterrows():
        try:
            close  = round(float(row["Close"]),  2)
            volume = int(row["Volume"])
            history.append({"date": str(date_idx.date()), "close": close, "volume": volume})
        except Exception:
            continue
    return history[-10:]   # last 10 days is enough context


# ─────────────────────────────────────────────────────────────────────────────
# SUPABASE — PORTFOLIO STATE
# ─────────────────────────────────────────────────────────────────────────────

def load_portfolio() -> dict:
    """Load portfolio state from Supabase. Creates default if none exists."""
    try:
        result = supabase.table("portfolio").select("*").eq("id", 1).execute()
        if result.data:
            return result.data[0]
    except Exception:
        pass

    # First run — create default portfolio
    default = {
        "id":       1,
        "cash":     STARTING_CASH,
        "holdings": json.dumps({}),
        "updated_at": datetime.now(ET).isoformat()
    }
    supabase.table("portfolio").upsert(default).execute()
    return default


def save_portfolio(cash: float, holdings: dict):
    """Persist portfolio state to Supabase."""
    supabase.table("portfolio").upsert({
        "id":        1,
        "cash":      round(cash, 2),
        "holdings":  json.dumps(holdings),
        "updated_at": datetime.now(ET).isoformat()
    }).execute()


def log_trade(ticker: str, side: str, shares: int,
              price: float, total: float, reason: str):
    """Append a trade to the trade history table."""
    supabase.table("trades").insert({
        "ticker":     ticker,
        "side":       side,
        "shares":     shares,
        "price":      round(price, 2),
        "total":      round(total, 2),
        "reason":     reason,
        "executed_at": datetime.now(ET).isoformat()
    }).execute()


def log_daily_snapshot(portfolio_value: float, cash: float,
                        holdings: dict, prices: dict, pnl: float):
    """Save end-of-day performance snapshot."""
    supabase.table("daily_snapshots").insert({
        "date":            date.today().isoformat(),
        "portfolio_value": round(portfolio_value, 2),
        "cash":            round(cash, 2),
        "pnl":             round(pnl, 2),
        "pnl_pct":         round((pnl / STARTING_CASH) * 100, 4),
        "holdings":        json.dumps(holdings),
        "prices":          json.dumps(prices)
    }).execute()


# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE AI — TRADE DECISIONS
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are TradeDesk AI — an autonomous paper trading assistant managing a $25,000 portfolio.

STRATEGY:
- Balanced growth with managed risk
- No single stock exceeds 20% of total portfolio value
- Always maintain minimum 15% cash reserve
- Prefer quality blue chips + select growth stocks
- React to market conditions, not emotions

RULES:
- Never buy if it would drop cash below 15% of total portfolio value
- Never sell more shares than currently held
- Maximum 4 trades per session to avoid overtrading
- Always provide a clear, concise reason for each trade

OUTPUT FORMAT — respond ONLY with valid JSON, nothing else:
{
  "market_commentary": "2-3 sentence market summary",
  "trades": [
    {
      "ticker": "AAPL",
      "side": "buy",
      "shares": 5,
      "reason": "Strong support at 50-day MA, earnings beat expected"
    }
  ]
}

If no trades are warranted, return an empty trades array.
"""

def get_ai_decisions(portfolio: dict, prices: dict, price_histories: dict) -> dict:
    """Ask Claude to analyze the market and return trade decisions."""

    holdings = json.loads(portfolio["holdings"])
    cash     = portfolio["cash"]

    # Calculate current portfolio value
    invested = sum(
        holdings[t]["shares"] * prices.get(t, holdings[t]["avg_cost"])
        for t in holdings
    )
    total_value = cash + invested

    prompt = f"""
Current time: {market_status_str()}
Portfolio value: ${total_value:,.2f}
Cash available: ${cash:,.2f} ({(cash/total_value*100):.1f}% of portfolio)
Starting capital: ${STARTING_CASH:,.2f}
Total P&L: ${total_value - STARTING_CASH:+,.2f}

CURRENT HOLDINGS:
{json.dumps(holdings, indent=2) if holdings else "None — fully in cash"}

LIVE PRICES:
{json.dumps(prices, indent=2)}

RECENT PRICE HISTORY (last 10 days):
{json.dumps(price_histories, indent=2)}

Based on this data, what trades should I make right now?
Remember: maintain 15% cash minimum, no position > 20% of portfolio.
Respond only with the JSON format specified.
"""

    response = claude.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ─────────────────────────────────────────────────────────────────────────────
# TRADE EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def execute_trades(decisions: dict, portfolio: dict, prices: dict) -> tuple[float, dict, list]:
    """Execute trades from Claude's decisions. Returns updated cash, holdings, log."""
    cash     = portfolio["cash"]
    holdings = json.loads(portfolio["holdings"])
    invested = sum(
        holdings[t]["shares"] * prices.get(t, holdings[t]["avg_cost"])
        for t in holdings
    )
    total_value   = cash + invested
    min_cash      = total_value * 0.15
    executed_log  = []

    for trade in decisions.get("trades", []):
        ticker = trade["ticker"]
        side   = trade["side"]
        shares = int(trade["shares"])
        reason = trade.get("reason", "")
        price  = prices.get(ticker)

        if not price or shares <= 0:
            continue

        total_cost = price * shares

        if side == "buy":
            if cash - total_cost < min_cash:
                executed_log.append(f"SKIPPED buy {ticker} — would breach 15% cash reserve")
                continue
            cash -= total_cost
            if ticker in holdings:
                prev_total = holdings[ticker]["shares"] * holdings[ticker]["avg_cost"]
                new_shares = holdings[ticker]["shares"] + shares
                holdings[ticker] = {
                    "shares":   new_shares,
                    "avg_cost": round((prev_total + total_cost) / new_shares, 4)
                }
            else:
                holdings[ticker] = {"shares": shares, "avg_cost": price}
            log_trade(ticker, "buy", shares, price, total_cost, reason)
            executed_log.append(f"BUY  {shares}x {ticker} @ ${price} = ${total_cost:,.2f} | {reason}")

        elif side == "sell":
            if ticker not in holdings or holdings[ticker]["shares"] < shares:
                executed_log.append(f"SKIPPED sell {ticker} — insufficient shares")
                continue
            cash += total_cost
            holdings[ticker]["shares"] -= shares
            if holdings[ticker]["shares"] == 0:
                del holdings[ticker]
            log_trade(ticker, "sell", shares, price, total_cost, reason)
            executed_log.append(f"SELL {shares}x {ticker} @ ${price} = ${total_cost:,.2f} | {reason}")

    return cash, holdings, executed_log


# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_trading_session():
    print(f"\n{'='*60}")
    print(f"  TradeDesk AI — {market_status_str()}")
    print(f"{'='*60}\n")

    if not is_market_open():
        print("Market is closed. No trades executed.")
        print("Next open: weekdays 9:30 AM ET\n")
        return

    print("Market is OPEN — starting analysis...\n")

    # 1. Load portfolio
    portfolio = load_portfolio()
    holdings  = json.loads(portfolio["holdings"])
    print(f"Cash: ${portfolio['cash']:,.2f}")
    print(f"Holdings: {list(holdings.keys()) or 'None'}\n")

    # 2. Fetch prices
    print("Fetching live prices...")
    prices = get_prices(WATCHLIST)
    print(f"Prices: {prices}\n")

    # 3. Fetch price history for context
    print("Fetching price history...")
    histories = {}
    for ticker in WATCHLIST:
        histories[ticker] = get_price_history(ticker)
    print("History loaded.\n")

    # 4. Get Claude's decisions
    print("Consulting Claude AI for trade decisions...")
    decisions = get_ai_decisions(portfolio, prices, histories)
    print(f"\nMarket commentary: {decisions.get('market_commentary', '')}")
    print(f"Trades proposed: {len(decisions.get('trades', []))}\n")

    # 5. Execute trades
    new_cash, new_holdings, trade_log = execute_trades(decisions, portfolio, prices)

    # 6. Save state
    save_portfolio(new_cash, new_holdings)

    # 7. Print results
    invested = sum(
        new_holdings[t]["shares"] * prices.get(t, new_holdings[t]["avg_cost"])
        for t in new_holdings
    )
    total_value = new_cash + invested
    pnl = total_value - STARTING_CASH

    print("── Trade execution log ──────────────────────────────")
    if trade_log:
        for entry in trade_log:
            print(f"  {entry}")
    else:
        print("  No trades executed this session.")

    print(f"\n── Portfolio summary ────────────────────────────────")
    print(f"  Total value : ${total_value:,.2f}")
    print(f"  Cash        : ${new_cash:,.2f}")
    print(f"  Invested    : ${invested:,.2f}")
    print(f"  P&L         : ${pnl:+,.2f} ({(pnl/STARTING_CASH*100):+.2f}%)")
    print(f"{'='*60}\n")


def run_end_of_day():
    """End-of-day snapshot — call this at 4:00 PM ET."""
    portfolio = load_portfolio()
    holdings  = json.loads(portfolio["holdings"])
    prices    = get_prices(list(holdings.keys()) or WATCHLIST)
    invested  = sum(
        holdings[t]["shares"] * prices.get(t, holdings[t]["avg_cost"])
        for t in holdings
    )
    total_value = portfolio["cash"] + invested
    pnl = total_value - STARTING_CASH
    log_daily_snapshot(total_value, portfolio["cash"], holdings, prices, pnl)
    print(f"End-of-day snapshot saved. P&L today: ${pnl:+,.2f}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "eod":
        run_end_of_day()
    else:
        run_trading_session()
