import pandas as pd
import numpy as np
import time

DATA_PATH = r'C:\Users\kingcuber\Desktop\algoRange\Dataset_NQ_1min_2022_2025.csv'

RISK_PER_TRADE = 0.01  # 1% Risk per trade
MAX_SL_PER_SESSION = 2
EVAL_COST = 499.0

# Prop Firm Constants ($100k Account)
START_BAL = 100000.0
STATIC_MAX_LOSS = 88000.0   # 12% static drawdown floor
DAILY_DRAWDOWN_PCT = 0.04   # 4% daily drawdown from start-of-day equity
PAYOUT_TARGET_PCT = 0.05    # 5% target for funded payouts
PHASE_1_TARGET = 110000.0
PHASE_2_TARGET = 106000.0

class PropAccount:
    def __init__(self):
        # Lifecycle Metrics
        self.evals_blown = 0
        self.evals_passed = 0
        self.payouts_count = 0
        self.total_payouts_usd = 0.0
        self.total_fees = 0.0
        self.has_taken_1r_payout = False
        
        self.reset_account()
        
    def reset_account(self):
        self.phase = 1
        self.equity = START_BAL
        self.start_of_day_equity = START_BAL
        self.daily_loss_limit = START_BAL * DAILY_DRAWDOWN_PCT
        self.daily_loss = 0.0
        self.total_fees += EVAL_COST
        self.has_taken_1r_payout = False
        
    def next_day(self):
        self.start_of_day_equity = self.equity
        self.daily_loss_limit = self.start_of_day_equity * DAILY_DRAWDOWN_PCT
        self.daily_loss = 0.0

    def process_pnl(self, pnl, current_date):
        self.equity += pnl
        if pnl < 0:
            self.daily_loss += abs(pnl)
            
        # Check DD
        if self.equity <= STATIC_MAX_LOSS or self.daily_loss >= self.daily_loss_limit:
            self.evals_blown += 1
            self.reset_account()
            return 'blown'
            
        # Check targets
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
            self.evals_passed += 1
            return 'passed_phase2'
            
        elif self.phase == 'FUNDED':
            if not self.has_taken_1r_payout and self.equity >= START_BAL + 1000.0:
                payout_amt = 1000.0
                self.payouts_count += 1
                self.total_payouts_usd += payout_amt
                self.equity -= payout_amt
                self.start_of_day_equity -= payout_amt
                self.has_taken_1r_payout = True
                return 'payout_1r'
                
            elif self.equity >= START_BAL * (1 + PAYOUT_TARGET_PCT):
                payout_amt = self.equity - START_BAL
                self.payouts_count += 1
                self.total_payouts_usd += payout_amt
                self.equity = START_BAL
                self.start_of_day_equity = START_BAL
                self.daily_loss = 0.0
                return 'payout'
                
        return 'active'

print("Loading NQ dataset for 6-Month Fibonacci Prop Firm Backtest...")
start_load = time.time()
df = pd.read_csv(DATA_PATH)
df['time ET'] = pd.to_datetime(df['timestamp ET'])
df.set_index('time ET', inplace=True)
df.sort_index(inplace=True)

# Filter for last 6 months
max_date = df.index.max()
start_date = max_date - pd.DateOffset(months=6)
df = df[df.index >= start_date]

print(f"Filtered to last 6 months: {start_date.date()} to {max_date.date()}")
print(f"Loaded {len(df)} rows in {time.time() - start_load:.2f} seconds.")

account = PropAccount()
events = []
current_date = None

in_trade = False
trade_entry = 0.0
trade_sl = 0.0
trade_tp = 0.0
bias = None
extreme_price = None
fib_0 = None
fib_1 = None
sl_count = 0
limit_order_active = False
limit_order_price = 0.0
limit_order_tp = 0.0
limit_order_sl = 0.0
range_high = None
range_low = None
stop_trading_session = False
entry_time = None

print("\n--- Running Simulation on NQ (NY Session Only) ---")
sim_start = time.time()

for row in df.itertuples():
    current_time = row.Index
    time_only = current_time.time()
    day_of_week = current_time.weekday()
    date_only = current_time.date()
    
    if current_date != date_only:
        current_date = date_only
        account.next_day()

    r_high = row.high
    r_low = row.low
    r_close = row.close

    # Force close any open trade on Friday at 15:50
    if day_of_week == 4 and time_only >= pd.Timestamp('15:50').time() and in_trade:
        if bias == 'LONG':
            r_return = (r_close - trade_entry) / (trade_entry - trade_sl)
        else:
            r_return = (trade_entry - r_close) / (trade_sl - trade_entry)
        
        pnl = START_BAL * RISK_PER_TRADE * r_return
        res = account.process_pnl(pnl, current_date)
        events.append({'date': date_only, 'time': current_time, 'type': f'{bias}_FRIDAY_EXIT', 'pnl': pnl, 'phase': account.phase, 'equity': account.equity, 'status': res})
        
        in_trade = False
        stop_trading_session = True

    # Check active trade
    if in_trade:
        if bias == 'LONG':
            if r_low <= trade_sl:
                sl_count += 1
                loss = START_BAL * RISK_PER_TRADE
                res = account.process_pnl(-loss, current_date)
                events.append({'date': date_only, 'time': current_time, 'type': 'LONG_SL', 'pnl': -loss, 'phase': account.phase, 'equity': account.equity, 'status': res})
                in_trade = False
                extreme_price = min(extreme_price, r_low)
                fib_0 = extreme_price
            elif r_high >= trade_tp:
                actual_rr = (trade_tp - trade_entry) / (trade_entry - trade_sl)
                profit = START_BAL * RISK_PER_TRADE * actual_rr
                res = account.process_pnl(profit, current_date)
                events.append({'date': date_only, 'time': current_time, 'type': 'LONG_TP', 'pnl': profit, 'phase': account.phase, 'equity': account.equity, 'status': res})
                in_trade = False
                bias = None
                stop_trading_session = True
        elif bias == 'SHORT':
            if r_high >= trade_sl:
                sl_count += 1
                loss = START_BAL * RISK_PER_TRADE
                res = account.process_pnl(-loss, current_date)
                events.append({'date': date_only, 'time': current_time, 'type': 'SHORT_SL', 'pnl': -loss, 'phase': account.phase, 'equity': account.equity, 'status': res})
                in_trade = False
                extreme_price = max(extreme_price, r_high)
                fib_0 = extreme_price
            elif r_low <= trade_tp:
                actual_rr = (trade_entry - trade_tp) / (trade_sl - trade_entry)
                profit = START_BAL * RISK_PER_TRADE * actual_rr
                res = account.process_pnl(profit, current_date)
                events.append({'date': date_only, 'time': current_time, 'type': 'SHORT_TP', 'pnl': profit, 'phase': account.phase, 'equity': account.equity, 'status': res})
                in_trade = False
                bias = None
                stop_trading_session = True
        
        if in_trade:
            continue

    # Session Reset Logic (NY Only)
    if time_only == pd.Timestamp('08:12').time() and not in_trade:
        sl_count = 0
        bias = None
        range_high = None
        range_low = None
        limit_order_active = False
        stop_trading_session = False

    if stop_trading_session or in_trade:
        continue

    if sl_count >= MAX_SL_PER_SESSION:
        continue

    # NY Session Time Bounds
    range_start = pd.Timestamp('08:12').time()
    range_end = pd.Timestamp('09:22').time()
    entry_start = pd.Timestamp('09:30').time()
    entry_end = pd.Timestamp('11:00').time()

    # Form Range
    if time_only >= range_start and time_only <= range_end:
        if range_high is None:
            range_high = r_high
            range_low = r_low
        else:
            range_high = max(range_high, r_high)
            range_low = min(range_low, r_low)
        continue

    if range_high is None or range_low is None:
        continue

    # Bias identification
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

    # Evaluate TP hit before entry
    if bias == 'LONG' and r_high >= fib_1:
        stop_trading_session = True
        limit_order_active = False
        continue
    elif bias == 'SHORT' and r_low <= fib_1:
        stop_trading_session = True
        limit_order_active = False
        continue

    # Update extremes
    if bias == 'LONG':
        if r_low < extreme_price:
            extreme_price = r_low
            fib_0 = extreme_price
    elif bias == 'SHORT':
        if r_high > extreme_price:
            extreme_price = r_high
            fib_0 = extreme_price

    # Process Limit Order if active
    if limit_order_active:
        if bias == 'LONG':
            if r_high >= limit_order_tp:
                limit_order_active = False
                continue
            if r_low <= limit_order_price:
                trade_entry = limit_order_price
                trade_sl = limit_order_sl
                trade_tp = limit_order_tp
                if r_low <= trade_sl:
                    sl_count += 1
                    loss = START_BAL * RISK_PER_TRADE
                    res = account.process_pnl(-loss, current_date)
                    events.append({'date': date_only, 'time': current_time, 'type': 'LONG_SL', 'pnl': -loss, 'phase': account.phase, 'equity': account.equity, 'status': res})
                    limit_order_active = False
                    extreme_price = min(extreme_price, r_low)
                    fib_0 = extreme_price
                else:
                    in_trade = True
                    entry_time = current_time
                    limit_order_active = False
                
        elif bias == 'SHORT':
            if r_low <= limit_order_tp:
                limit_order_active = False
                continue
            if r_high >= limit_order_price:
                trade_entry = limit_order_price
                trade_sl = limit_order_sl
                trade_tp = limit_order_tp
                if r_high >= trade_sl:
                    sl_count += 1
                    loss = START_BAL * RISK_PER_TRADE
                    res = account.process_pnl(-loss, current_date)
                    events.append({'date': date_only, 'time': current_time, 'type': 'SHORT_SL', 'pnl': -loss, 'phase': account.phase, 'equity': account.equity, 'status': res})
                    limit_order_active = False
                    extreme_price = max(extreme_price, r_high)
                    fib_0 = extreme_price
                else:
                    in_trade = True
                    entry_time = current_time
                    limit_order_active = False
        continue

    # Entry Window logic
    if time_only >= entry_start and time_only <= entry_end:
        fib_range = fib_1 - fib_0
        c = r_close
        
        if bias == 'LONG':
            f236 = fib_0 + fib_range * 0.236
            f400 = fib_0 + fib_range * 0.400
            f330 = fib_0 + fib_range * 0.330
            
            if c > f236:
                if c <= f400:
                    in_trade = True
                    trade_entry = c
                    trade_sl = fib_0
                    if trade_entry == trade_sl: trade_sl -= 1
                    trade_tp = trade_entry + 50
                    entry_time = current_time
                else:
                    limit_order_active = True
                    limit_order_price = f330
                    limit_order_sl = fib_0
                    if limit_order_price == limit_order_sl: limit_order_sl -= 1
                    limit_order_tp = limit_order_price + 50
                    
        elif bias == 'SHORT':
            f236 = fib_0 + fib_range * 0.236
            f400 = fib_0 + fib_range * 0.400
            f330 = fib_0 + fib_range * 0.330
            
            if c < f236:
                if c >= f400:
                    in_trade = True
                    trade_entry = c
                    trade_sl = fib_0
                    if trade_entry == trade_sl: trade_sl += 1
                    trade_tp = trade_entry - 50
                    entry_time = current_time
                else:
                    limit_order_active = True
                    limit_order_price = f330
                    limit_order_sl = fib_0
                    if limit_order_price == limit_order_sl: limit_order_sl += 1
                    limit_order_tp = limit_order_price - 50

print(f"Simulation completed in {time.time() - sim_start:.2f} seconds.")
print("\n--- Summary ---")

df_events = pd.DataFrame(events)
if not df_events.empty:
    print(f"Total Trades Taken: {len(df_events)}")
    print(f"Evaluations Blown: {account.evals_blown}")
    print(f"Evaluations Passed (Fully Funded): {account.evals_passed}")
    print(f"Total Evaluation Fees Paid: ${account.total_fees:,.2f}")
    print(f"Total Payouts Received: {account.payouts_count} (${account.total_payouts_usd:,.2f})")
    print(f"Net Profit: ${account.total_payouts_usd - account.total_fees:,.2f}")
    
    # Save a detailed log of events to see exactly what happened
    df_events.to_csv(r"C:\Users\kingcuber\.gemini\antigravity-ide\brain\8370803b-9474-4100-8b6b-158135823a70\scratch\fibo_prop_events.csv", index=False)
else:
    print("No trades taken.")
