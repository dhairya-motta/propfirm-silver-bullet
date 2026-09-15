import sys
import os
import time
import pandas as pd
import numpy as np

# Add the propfirm-silver-bullet path to sys.path to import its modules
sys.path.append(r'C:\Users\kingcuber\.gemini\antigravity-ide\scratch\propfirm-silver-bullet')
from data_loader import load_volatility_data, get_nfp_dates
from trade_extractor import extract_trades

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
        self.status = 'active'

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

def simulate_silver_bullet(df, trades, session_name, years):
    print(f"\n=============================================")
    print(f"Running Simulation for {session_name} ({years}-Year)")
    sim_start = time.time()
    
    if len(trades) == 0:
        print("0 trades found.")
        return

    first_date = trades[0]['date']
    account = PropAccount(first_date)
    
    events = []
    trade_outcomes = []
    current_date = None
    
    df_index = df.index.values

    # To group trades by session for 2-loss rule
    session_sl_count = {'AM': 0, 'PM': 0}

    for t in trades:
        t_date = t['date']
        
        if current_date != t_date:
            current_date = t_date
            account.next_day()
            session_sl_count = {'AM': 0, 'PM': 0}

        t_session = t['session']
        if session_sl_count[t_session] >= 2:
            continue
            
        entry = t['entry']
        is_long = t['is_long']
        sweep = t['sweep']
        
        # SB Limit Order Risk definition
        if is_long:
            sl = sweep - 1.0
            if sl >= entry: sl = entry - 0.25
            risk_pts = abs(entry - sl)
            tp = entry + risk_pts  # 1:1 RR
        else:
            sl = sweep + 1.0
            if sl <= entry: sl = entry + 0.25
            risk_pts = abs(entry - sl)
            tp = entry - risk_pts

        start_ts = t['time'].to_numpy()
        start_idx = np.searchsorted(df_index, start_ts)
        end_ts = pd.Timestamp(f"{t_date} 15:59:00").tz_localize('US/Eastern').to_numpy()
        end_idx = np.searchsorted(df_index, end_ts)

        if start_idx >= len(df) or start_idx >= end_idx: continue
        eval_window = df.iloc[start_idx+1:end_idx+1]
        
        res_pts = 0
        filled = False
        trade_hit_sl = False
        
        for idx, row in eval_window.iterrows():
            h, l = row['high'], row['low']
            if not filled:
                if is_long:
                    if l <= entry:
                        filled = True
                        if l <= sl: res_pts = sl - entry; trade_hit_sl = True; break
                        if h >= tp: res_pts = tp - entry; break
                else:
                    if h >= entry:
                        filled = True
                        if h >= sl: res_pts = entry - sl; trade_hit_sl = True; break
                        if l <= tp: res_pts = entry - tp; break
            else:
                if is_long:
                    if l <= sl: res_pts = sl - entry; trade_hit_sl = True; break
                    if h >= tp: res_pts = tp - entry; break
                else:
                    if h >= sl: res_pts = entry - sl; trade_hit_sl = True; break
                    if l <= tp: res_pts = entry - tp; break

        if not filled: continue
        
        if res_pts == 0:
            c = eval_window.iloc[-1]['close']
            res_pts = (c - entry) if is_long else (entry - c)
            if res_pts < 0: trade_hit_sl = True

        if trade_hit_sl:
            session_sl_count[t_session] += 1
            loss = START_BAL * RISK_PER_TRADE
            account.process_pnl(-loss, current_date)
            trade_outcomes.append(-1)
        else:
            actual_rr = abs(res_pts) / risk_pts
            profit = START_BAL * RISK_PER_TRADE * actual_rr
            account.process_pnl(profit, current_date)
            trade_outcomes.append(1)

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

def run_all():
    nq_data = r'C:\Users\kingcuber\.gemini\antigravity-ide\scratch\nsx_cleaned_2010_2025.csv'
    vol_data_path = r'C:\Users\kingcuber\.gemini\antigravity-ide\scratch\propfirm-silver-bullet\volatility_data.json'
    
    print("Loading data...")
    df = pd.read_csv(nq_data)
    df['time ET'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df.set_index('time ET', inplace=True)
    df.sort_index(inplace=True)
    df['date'] = df.index.date
    
    nfp_dates = get_nfp_dates(df)
    vol_data = load_volatility_data(vol_data_path)
    
    # Run for 5 and 10 years
    for years in [5, 10]:
        max_date = df.index.max()
        start_date = max_date - pd.DateOffset(years=years)
        df_period = df[df.index >= start_date]
        
        print(f"Extracting trades for {years}-Year period...")
        
        # AM + PM Combined [No Filter]
        trades_nofilter = extract_trades(df_period, vol_data, nfp_dates, use_filter=False, use_nfp=False, session='AM+PM')
        simulate_silver_bullet(df_period, trades_nofilter, "AM + PM Combined [NO FILTER]", years)
        
        # AM + PM Combined [ATR Filter]
        trades_atr = extract_trades(df_period, vol_data, nfp_dates, use_filter=True, use_nfp=False, session='AM+PM')
        simulate_silver_bullet(df_period, trades_atr, "AM + PM Combined [ATR FILTER]", years)

if __name__ == "__main__":
    run_all()
