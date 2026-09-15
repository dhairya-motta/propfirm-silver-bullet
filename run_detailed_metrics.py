import pandas as pd
import numpy as np
import time
import os

RISK_PER_TRADE = 0.01
EVAL_COST = 455.0

START_BAL = 100000.0
STATIC_MAX_LOSS = 92000.0 # 8% static
DAILY_DRAWDOWN_PCT = 0.04 # 4% daily
PAYOUT_TARGET_PCT = 0.02 # 2% target for continuous payouts
PHASE_1_TARGET = 108000.0 # 8%
PHASE_2_TARGET = 105000.0 # 5%

class PropAccountTracker:
    def __init__(self, start_date):
        self.eval_start_date = start_date
        self.eval_pass_date = None
        self.first_1pct_payout_date = None
        self.first_4pct_payout_date = None
        self.payouts_1pct_count = 0
        self.payouts_4pct_count = 0
        self.total_payouts_usd = 0.0
        self.refund_earned = 0.0
        self.status = 'active' # active, blown, passed

class PropAccount:
    def __init__(self, date):
        self.tracker_history = []
        self.current_tracker = PropAccountTracker(date)
        self.total_fees = 0.0
        self.reset_account(date)
        
    def reset_account(self, date):
        self.phase = 1
        self.equity = START_BAL
        self.start_of_day_equity = START_BAL
        self.daily_loss_limit = START_BAL * DAILY_DRAWDOWN_PCT
        self.daily_loss = 0.0
        self.total_fees += EVAL_COST
        
        if self.current_tracker.eval_start_date != date:
            self.tracker_history.append(self.current_tracker)
            self.current_tracker = PropAccountTracker(date)
        
    def next_day(self):
        self.start_of_day_equity = self.equity
        self.daily_loss_limit = self.start_of_day_equity * DAILY_DRAWDOWN_PCT
        self.daily_loss = 0.0

    def process_pnl(self, pnl, current_date):
        self.equity += pnl
        if pnl < 0:
            self.daily_loss += abs(pnl)
            
        if self.equity <= STATIC_MAX_LOSS or self.daily_loss >= self.daily_loss_limit:
            self.current_tracker.status = 'blown'
            self.reset_account(current_date)
            return 'blown'
            
        if self.phase == 1 and self.equity >= PHASE_1_TARGET:
            self.phase = 2
            self.equity = START_BAL
            self.start_of_day_equity = START_BAL
            self.daily_loss = 0.0
            return 'passed_phase1'
            
        elif self.phase == 2 and self.equity >= PHASE_2_TARGET:
            self.phase = 'FUNDED'
            self.equity = START_BAL
            self.start_of_day_equity = START_BAL
            self.daily_loss = 0.0
            self.current_tracker.eval_pass_date = current_date
            return 'passed_phase2'
            
        elif self.phase == 'FUNDED':
            if self.current_tracker.payouts_1pct_count == 0 and self.equity >= START_BAL + 1000.0:
                payout_amt = 1000.0
                self.current_tracker.payouts_1pct_count += 1
                self.current_tracker.total_payouts_usd += payout_amt
                self.current_tracker.first_1pct_payout_date = current_date
                if self.current_tracker.refund_earned == 0:
                    self.current_tracker.refund_earned = EVAL_COST
                self.equity -= payout_amt
                self.start_of_day_equity -= payout_amt
                return 'payout_1r'
                
            elif self.equity >= START_BAL * (1 + PAYOUT_TARGET_PCT):
                payout_amt = min(self.equity - START_BAL, 2000.0)
                self.current_tracker.payouts_4pct_count += 1
                self.current_tracker.total_payouts_usd += payout_amt
                if self.current_tracker.first_4pct_payout_date is None:
                    self.current_tracker.first_4pct_payout_date = current_date
                if self.current_tracker.refund_earned == 0:
                    self.current_tracker.refund_earned = EVAL_COST
                self.equity -= payout_amt
                self.start_of_day_equity -= payout_amt
                self.daily_loss = 0.0
                return 'payout'
                
        return 'active'

def run_simulation(data_path, years_to_run, range_start_str, range_end_str, entry_start_str, entry_end_str, session_name):
    print(f"\n=============================================")
    print(f"Loading NQ dataset for {years_to_run}-Year Backtest...")
    print(f"Variant: {session_name} | Flat 50 Points")
    start_load = time.time()
    
    df = pd.read_csv(data_path)
    df['time ET'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df.set_index('time ET', inplace=True)
    df.sort_index(inplace=True)
    
    max_date = df.index.max()
    start_date = max_date - pd.DateOffset(years=years_to_run)
    df = df[df.index >= start_date]

    print(f"Loaded {len(df)} rows in {time.time() - start_load:.2f} seconds.")

    first_date = df.index.min().date()
    account = PropAccount(first_date)
    events = []
    trade_outcomes = []
    current_date = None
    
    r_start = pd.Timestamp(range_start_str).time()
    r_end = pd.Timestamp(range_end_str).time()
    e_start = pd.Timestamp(entry_start_str).time()
    e_end = pd.Timestamp(entry_end_str).time()

    # Session variables
    in_trade = False
    trade_entry = 0.0
    trade_sl = 0.0
    trade_tp = 0.0
    bias = None
    extreme_price = None
    fib_0 = None
    fib_1 = None
    limit_order_active = False
    limit_order_price = 0.0
    limit_order_tp = 0.0
    limit_order_sl = 0.0
    range_high = None
    range_low = None
    stop_trading_session = False
    session_sl_count = 0

    sim_start = time.time()

    for row in df.itertuples():
        current_time = row.Index
        time_only = current_time.time()
        day_of_week = current_time.weekday()
        date_only = current_time.date()
        
        if current_date != date_only:
            current_date = date_only
            account.next_day()
            
            in_trade = False
            bias = None
            range_high = None
            range_low = None
            limit_order_active = False
            stop_trading_session = False
            session_sl_count = 0

        r_high = row.high
        r_low = row.low
        r_close = row.close
        
        if day_of_week == 4 and time_only >= pd.Timestamp('15:50').time() and in_trade:
            r_return = (r_close - trade_entry) / (trade_entry - trade_sl) if bias == 'LONG' else (trade_entry - r_close) / (trade_sl - trade_entry)
            pnl = START_BAL * RISK_PER_TRADE * r_return
            res = account.process_pnl(pnl, current_date)
            events.append({'date': date_only, 'type': 'FRIDAY_EXIT', 'pnl': pnl})
            trade_outcomes.append(1 if pnl > 0 else -1)
            in_trade = False
            stop_trading_session = True

        if in_trade:
            if bias == 'LONG':
                if r_low <= trade_sl:
                    session_sl_count += 1
                    loss = START_BAL * RISK_PER_TRADE
                    res = account.process_pnl(-loss, current_date)
                    events.append({'date': date_only, 'type': 'LONG_SL', 'pnl': -loss})
                    trade_outcomes.append(-1)
                    in_trade = False
                    extreme_price = min(extreme_price, r_low)
                    fib_0 = extreme_price
                elif r_high >= trade_tp:
                    actual_rr = (trade_tp - trade_entry) / (trade_entry - trade_sl)
                    profit = START_BAL * RISK_PER_TRADE * actual_rr
                    res = account.process_pnl(profit, current_date)
                    events.append({'date': date_only, 'type': 'LONG_TP', 'pnl': profit})
                    trade_outcomes.append(1)
                    in_trade = False
                    bias = None
                    stop_trading_session = True
            elif bias == 'SHORT':
                if r_high >= trade_sl:
                    session_sl_count += 1
                    loss = START_BAL * RISK_PER_TRADE
                    res = account.process_pnl(-loss, current_date)
                    events.append({'date': date_only, 'type': 'SHORT_SL', 'pnl': -loss})
                    trade_outcomes.append(-1)
                    in_trade = False
                    extreme_price = max(extreme_price, r_high)
                    fib_0 = extreme_price
                elif r_low <= trade_tp:
                    actual_rr = (trade_entry - trade_tp) / (trade_sl - trade_entry)
                    profit = START_BAL * RISK_PER_TRADE * actual_rr
                    res = account.process_pnl(profit, current_date)
                    events.append({'date': date_only, 'type': 'SHORT_TP', 'pnl': profit})
                    trade_outcomes.append(1)
                    in_trade = False
                    bias = None
                    stop_trading_session = True
            if in_trade:
                continue

        if stop_trading_session or session_sl_count >= 2:
            continue
            
        if time_only >= r_start and time_only <= r_end:
            if range_high is None:
                range_high, range_low = r_high, r_low
            else:
                range_high = max(range_high, r_high)
                range_low = min(range_low, r_low)
            continue

        if range_high is None or range_low is None:
            continue

        if bias is None:
            if r_low < range_low:
                bias = 'LONG'
                extreme_price = r_low
                fib_1 = range_high
                fib_0 = extreme_price
            elif r_high > range_high:
                bias = 'SHORT'
                extreme_price = r_high
                fib_1 = range_low
                fib_0 = extreme_price
            if bias is None:
                continue

        if bias == 'LONG' and r_high >= fib_1:
            stop_trading_session = True
            limit_order_active = False
            continue
        elif bias == 'SHORT' and r_low <= fib_1:
            stop_trading_session = True
            limit_order_active = False
            continue

        if bias == 'LONG':
            extreme_price = min(extreme_price, r_low)
            fib_0 = extreme_price
        elif bias == 'SHORT':
            extreme_price = max(extreme_price, r_high)
            fib_0 = extreme_price

        if limit_order_active:
            if bias == 'LONG':
                if r_high >= limit_order_tp:
                    limit_order_active = False
                    continue
                if r_low <= limit_order_price:
                    trade_entry, trade_sl, trade_tp = limit_order_price, limit_order_sl, limit_order_tp
                    if r_low <= trade_sl:
                        session_sl_count += 1
                        loss = START_BAL * RISK_PER_TRADE
                        res = account.process_pnl(-loss, current_date)
                        events.append({'date': date_only, 'type': 'LONG_SL', 'pnl': -loss})
                        trade_outcomes.append(-1)
                        limit_order_active = False
                        extreme_price = min(extreme_price, r_low)
                        fib_0 = extreme_price
                    else:
                        in_trade = True
                        limit_order_active = False
            elif bias == 'SHORT':
                if r_low <= limit_order_tp:
                    limit_order_active = False
                    continue
                if r_high >= limit_order_price:
                    trade_entry, trade_sl, trade_tp = limit_order_price, limit_order_sl, limit_order_tp
                    if r_high >= trade_sl:
                        session_sl_count += 1
                        loss = START_BAL * RISK_PER_TRADE
                        res = account.process_pnl(-loss, current_date)
                        events.append({'date': date_only, 'type': 'SHORT_SL', 'pnl': -loss})
                        trade_outcomes.append(-1)
                        limit_order_active = False
                        extreme_price = max(extreme_price, r_high)
                        fib_0 = extreme_price
                    else:
                        in_trade = True
                        limit_order_active = False
            continue

        if time_only >= e_start and time_only <= e_end:
            fib_range = fib_1 - fib_0
            c = r_close
            
            f236 = fib_0 + fib_range * 0.236
            f400 = fib_0 + fib_range * 0.400
            f330 = fib_0 + fib_range * 0.330
            
            if bias == 'LONG':
                if c > f236:
                    trade_sl = fib_0
                    if c <= f400:
                        in_trade = True
                        trade_entry = c
                        if trade_entry == trade_sl: trade_sl -= 1
                        trade_tp = trade_entry + 50
                    else:
                        limit_order_active = True
                        limit_order_price = f330
                        limit_order_sl = trade_sl
                        if limit_order_price == limit_order_sl: limit_order_sl -= 1
                        limit_order_tp = limit_order_price + 50
                        
            elif bias == 'SHORT':
                if c < f236:
                    trade_sl = fib_0
                    if c >= f400:
                        in_trade = True
                        trade_entry = c
                        if trade_entry == trade_sl: trade_sl += 1
                        trade_tp = trade_entry - 50
                    else:
                        limit_order_active = True
                        limit_order_price = f330
                        limit_order_sl = trade_sl
                        if limit_order_price == limit_order_sl: limit_order_sl += 1
                        limit_order_tp = limit_order_price - 50

    account.tracker_history.append(account.current_tracker)

    # --- Metrics Calculation ---
    trackers = account.tracker_history
    passed_trackers = [t for t in trackers if t.eval_pass_date is not None]
    trackers_with_1r = [t for t in passed_trackers if t.payouts_1pct_count > 0]
    trackers_with_4pct = [t for t in passed_trackers if t.payouts_4pct_count > 0]
    
    avg_days_to_pass = np.mean([(t.eval_pass_date - t.eval_start_date).days for t in passed_trackers]) if passed_trackers else 0
    avg_days_to_1r = np.mean([(t.first_1pct_payout_date - t.eval_pass_date).days for t in trackers_with_1r]) if trackers_with_1r else 0
    avg_days_to_4pct = np.mean([(t.first_4pct_payout_date - t.eval_pass_date).days for t in trackers_with_4pct]) if trackers_with_4pct else 0
    
    avg_1r_per_passed = np.mean([t.payouts_1pct_count for t in passed_trackers]) if passed_trackers else 0
    avg_4pct_per_passed = np.mean([t.payouts_4pct_count for t in passed_trackers]) if passed_trackers else 0

    pct_reach_payout = (len(trackers_with_1r) / len(passed_trackers) * 100) if passed_trackers else 0
    pct_reach_4pct_payout = (len(trackers_with_4pct) / len(passed_trackers) * 100) if passed_trackers else 0
    
    total_net = sum(t.total_payouts_usd for t in trackers)
    total_refunds = sum(t.refund_earned for t in trackers)
    net_burn = account.total_fees - total_refunds
    net_profit = total_net - net_burn
    roi = (total_net / net_burn * 100) if net_burn > 0 else 0

    # Streaks
    streaks = []
    current_streak = 0
    for outcome in trade_outcomes:
        if outcome == 1:
            current_streak = current_streak + 1 if current_streak > 0 else 1
        elif outcome == -1:
            current_streak = current_streak - 1 if current_streak < 0 else -1
        streaks.append(current_streak)
        
    win_streaks = [s for s in streaks if s > 0]
    loss_streaks = [abs(s) for s in streaks if s < 0]
    
    avg_win_streak = np.mean(win_streaks) if win_streaks else 0
    avg_loss_streak = np.mean(loss_streaks) if loss_streaks else 0

    print(f"Simulation completed in {time.time() - sim_start:.2f} seconds.")
    print("--- Detailed Summary ---")
    print(f"Total Trades Taken: {len(trade_outcomes)}")
    print(f"Total Evaluations Started: {len(trackers)}")
    print(f"Evaluations Passed: {len(passed_trackers)}")
    print(f"Total Fees Paid: ${account.total_fees:,.2f}")
    print(f"Total Refunds Earned: ${total_refunds:,.2f}")
    print(f"Net Fee Burn: ${net_burn:,.2f}")
    print(f"Total Payouts Received: ${total_net:,.2f}")
    print(f"Net Profit (Payouts - Net Burn): ${net_profit:,.2f}")
    print(f"Return on Spend (ROI): {roi:.1f}%")
    print("--- Lifecycle Metrics ---")
    print(f"Avg Win Streak: {avg_win_streak:.2f} trades")
    print(f"Avg Losing Streak: {avg_loss_streak:.2f} trades")
    print(f"Avg Days to Pass Eval (P1+P2): {avg_days_to_pass:.1f} days")
    print(f"Avg Days to First 1% Payout (from funded): {avg_days_to_1r:.1f} days")
    print(f"Avg Days to First 4% Payout (from funded): {avg_days_to_4pct:.1f} days")
    print(f"Avg 1% Payouts per passed account: {avg_1r_per_passed:.2f}")
    print(f"Avg 4% Payouts per passed account: {avg_4pct_per_passed:.2f}")
    print(f"% Passed Accounts that reached 1% payout: {pct_reach_payout:.1f}%")
    print(f"% Passed Accounts that reached 4% payout: {pct_reach_4pct_payout:.1f}%")
    print("=============================================\n")


if __name__ == "__main__":
    nq_data = r'C:\Users\kingcuber\.gemini\antigravity-ide\scratch\nsx_cleaned_2010_2025.csv'
    
    # 5-Year
    run_simulation(nq_data, 5, '08:12', '09:22', '09:30', '11:00', "NY Session (5-Year)")
    run_simulation(nq_data, 5, '01:10', '02:22', '02:30', '05:00', "London Variant B (5-Year)")
    
    # 10-Year
    run_simulation(nq_data, 10, '08:12', '09:22', '09:30', '11:00', "NY Session (10-Year)")
    run_simulation(nq_data, 10, '01:10', '02:22', '02:30', '05:00', "London Variant B (10-Year)")
