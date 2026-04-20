"""
TradeDesk — Supabase Database Setup
Run this once to create all required tables
"""

import os
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def setup_tables():
    """Create all tables via Supabase SQL editor — paste each block below."""
    print("""
Run these SQL statements in your Supabase SQL Editor:
(Dashboard → SQL Editor → New Query → paste → Run)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 1. Portfolio state (single row, always id=1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE IF NOT EXISTS portfolio (
  id          INT PRIMARY KEY DEFAULT 1,
  cash        FLOAT NOT NULL DEFAULT 25000,
  holdings    TEXT  NOT NULL DEFAULT '{}',
  updated_at  TEXT
);

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 2. Trade history log
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE IF NOT EXISTS trades (
  id          BIGSERIAL PRIMARY KEY,
  ticker      TEXT  NOT NULL,
  side        TEXT  NOT NULL,
  shares      INT   NOT NULL,
  price       FLOAT NOT NULL,
  total       FLOAT NOT NULL,
  reason      TEXT,
  executed_at TEXT
);

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 3. Daily performance snapshots
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE IF NOT EXISTS daily_snapshots (
  id              BIGSERIAL PRIMARY KEY,
  date            TEXT  NOT NULL,
  portfolio_value FLOAT NOT NULL,
  cash            FLOAT NOT NULL,
  pnl             FLOAT NOT NULL,
  pnl_pct         FLOAT NOT NULL,
  holdings        TEXT,
  prices          TEXT
);
""")

if __name__ == "__main__":
    setup_tables()
