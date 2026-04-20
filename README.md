# TradeDesk — Autonomous AI Trading Bot

Powered by Claude AI + Yahoo Finance + Supabase + GitHub Actions.
Runs completely autonomously during market hours — no human prompts needed.

---

## How it works

1. GitHub Actions wakes the bot automatically at 9:31 AM, 12:00 PM, and 2:30 PM ET
2. `trader.py` fetches live prices from Yahoo Finance
3. Claude AI analyzes the portfolio and market data
4. Claude returns trade decisions as JSON
5. Trades are executed and saved to Supabase
6. End-of-day snapshot is saved at 4:01 PM ET

---

## Setup (one time)

### Step 1 — Set up Supabase tables
1. Go to your Supabase dashboard → SQL Editor → New Query
2. Copy and run each SQL block from `setup_db.py`

### Step 2 — Get your Anthropic API key
1. Go to console.anthropic.com
2. Create an API key and copy it

### Step 3 — Add secrets to GitHub
1. Go to your GitHub repo → Settings → Secrets and variables → Actions
2. Add these three secrets:
   - `ANTHROPIC_API_KEY` — your Anthropic key
   - `SUPABASE_URL` — https://jzmhybaaaacauspstjlh.supabase.co
   - `SUPABASE_KEY` — your Supabase anon key

### Step 4 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial TradeDesk setup"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/tradedesk.git
git push -u origin main
```

### Step 5 — Enable GitHub Actions
1. Go to your repo → Actions tab
2. Click "Enable Actions"
3. The scheduler will now run automatically on trading days

---

## Running manually

```bash
pip install anthropic yfinance supabase pytz
python trader.py        # run a trading session
python trader.py eod    # run end-of-day snapshot
```

---

## Strategy

- Balanced growth with managed risk
- Max 20% of portfolio in any single stock
- Min 15% cash reserve always maintained
- Watchlist: SPY, AAPL, MSFT, NVDA, AMZN, GOOGL, TSLA, META
- Max 4 trades per session

---

## Files

| File | Purpose |
|------|---------|
| `trader.py` | Main bot — fetches prices, asks Claude, executes trades |
| `setup_db.py` | One-time Supabase table setup |
| `.github/workflows/trader.yml` | GitHub Actions schedule |
| `.env.example` | Environment variable template |
| `.gitignore` | Keeps secrets out of GitHub |
