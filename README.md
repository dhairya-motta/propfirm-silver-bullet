# Silver Bullet Strategy (AM + PM Sessions)

This repository contains the simulation engine, logic, and comprehensive multi-year backtest data for the **Silver Bullet Strategy** on NQ (Nasdaq 100) futures.

## The Strategy

The Silver Bullet Strategy looks for structural liquidity sweeps during specific 1-hour windows (10:00-11:00 AM EST and 2:00-3:00 PM EST). 

- **Instrument:** NQ
- **Risk:** 1% per trade
- **Take Profit / Stop Loss:** 1:1 Risk/Reward Ratio targeting the opposing liquidity pool.
- **Filters:** We backtested an **[ATR Filter]** which keeps the strategy out of low-volatility, choppy market conditions versus an unfiltered **[NO FILTER]** approach that blindly takes every setup.

## Prop Firm Payout Mechanics (The "2% Rinse")

Instead of waiting for large capital buffers to accumulate (e.g., waiting for +4% equity to withdraw), this strategy utilizes a **2% Continuous Rinsing** mechanic. 

Once an account passes its evaluations (Phase 1 & Phase 2) and gets funded:
1. The first payout targets a 1% profit to immediately recoup the Evaluation Fee.
2. Every subsequent payout triggers as soon as the account equity reaches +2% ($2,000 buffer on a 100k account).
3. The account is aggressively milked for small, continuous cash flow before drawdowns can erode profits.

---

## 10-Year Backtest Results (2015 - 2025)

The following metrics represent a 10-year simulation of trading this strategy exclusively on standard $100k Prop Firm evaluations, accounting for all evaluation fees, account blow-ups, and actual physical dollars extracted.

### AM + PM Combined [NO FILTER] (10-Year)
- **Total Trades Taken:** 3,918
- **Total Evaluations Started:** 41
- **Evaluations Passed:** 8
- **Total Fees Paid:** $18,655.00
- **Total Refunds Earned:** $3,185.00
- **Net Fee Burn:** $15,470.00
- **Total Payouts Received:** $63,000.00
- **Net Profit (Payouts - Net Burn):** **$47,530.00**
- **Return on Spend (ROI):** **407.2%**

**Account Lifecycle:**
- Avg Win Streak: 1.99 trades
- Avg Losing Streak: 2.03 trades
- Avg Days to Pass Eval (P1+P2): 89.4 days
- Avg Days to First 2% Payout (from funded): 30.4 days
- Avg 2% Payouts per passed account: 3.50

### AM + PM Combined [ATR FILTER] (10-Year)
- **Total Trades Taken:** 2,327
- **Total Evaluations Started:** 21
- **Evaluations Passed:** 4
- **Total Fees Paid:** $9,555.00
- **Total Refunds Earned:** $1,820.00
- **Net Fee Burn:** $7,735.00
- **Total Payouts Received:** $52,000.00
- **Net Profit (Payouts - Net Burn):** **$44,265.00**
- **Return on Spend (ROI):** **672.3%**

**Account Lifecycle:**
- Avg Win Streak: 1.96 trades
- Avg Losing Streak: 1.95 trades
- Avg Days to Pass Eval (P1+P2): 150.2 days
- Avg Days to First 2% Payout (from funded): 108.0 days
- Avg 2% Payouts per passed account: 6.00

---

## 5-Year Backtest Results (2020 - 2025)

The most recent 5 years of price action (which includes higher NQ volatility post-pandemic) showed a very different characteristic, where passing evaluations happened faster but the total yield was lower compared to the 10-year block.

### AM + PM Combined [NO FILTER] (5-Year)
- **Net Profit:** $35,630.00
- **Return on Spend (ROI):** 659.3%
- **Avg 2% Payouts per passed account:** 4.75

### AM + PM Combined [ATR FILTER] (5-Year)
- **Net Profit:** $25,630.00
- **Return on Spend (ROI):** 502.4%
- **Avg 2% Payouts per passed account:** 7.50

## Conclusion
The **Silver Bullet Strategy** is highly effective at grinding out profits over the long term. While it does not produce the massive $200k+ yields of the Fibo 50-pt strategy, its tight 1:1 risk/reward ensures that drawdowns are shallow and manageable. 

Using the **ATR Filter** reduces the number of evaluations passed (since you take fewer trades, passing takes 150 days on average), but drastically increases the survival rate of funded accounts. When an account gets funded using the ATR filter, it averages **6 distinct payouts** before blowing up, making it a highly resilient cash-flow engine.
