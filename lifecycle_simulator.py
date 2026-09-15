import pandas as pd
import numpy as np

# ─────────────────────────────────────────────
# PROP FIRM RULES (from screenshot)
# ─────────────────────────────────────────────
START_BAL         = 50000.0                # $50k Account
EVAL_TARGET       = 3000.0                 # $3k profit target
EVAL_FEE          = 49.0                   # Assume $49 on sale
ACTIVATION_FEE    = 139.0
MAX_DD            = 2000.0                 # $2k trailing DD
EOD_DD_LIMIT      = 2000.0
DAILY_LOSS_LIMIT  = 1000.0                 # $1k Daily Loss Limit
CONSISTENCY_MAX   = 0.50                   # No single trade > 50% of total profit
RISK_AMT          = 250.0                  # Risk $250 per trade
PENALTY_PTS       = 0.75                   # slippage + commission per side
MAX_CONTRACTS_EVAL   = 5.0                   
MAX_CONTRACTS_FUNDED = 4.0
NUM_ACCOUNTS      = 20
PAYOUT_BUFFER     = 0.0                    # No buffer (withdraw everything)
PAYOUT_AMT        = 1500.0                 # Target $1,500 per payout
FUNDED_TARGET     = START_BAL + PAYOUT_AMT + PAYOUT_BUFFER

TARGET_R          = 1.0                    # Fixed 1R target
MAX_PAYOUTS       = 6                      # Retire account after 6 payouts


class PropAccount:
    """State machine for a single prop firm account."""

    def __init__(self, acct_id):
        self.id = acct_id
        self.reset_eval()

        # Lifetime counters
        self.total_fees          = EVAL_FEE   # first eval fee on creation
        self.total_payouts_usd   = 0.0
        self.total_payouts_count = 0
        self.evals_taken         = 1
        self.evals_passed        = 0
        self.evals_blown         = 0
        self.accounts_retired    = 0
        self.payouts_1st         = 0
        self.payouts_2nd         = 0
        self.events              = []

        # Timing lists
        self.eval_pass_days_list  = []
        self.payout1_days_list    = []
        self.payout2_days_list    = []

        # Win/loss streak tracking (across entire lifetime)
        self.cur_win_streak  = 0
        self.cur_lose_streak = 0
        self.win_streaks     = []
        self.lose_streaks    = []

        # Consistency rule block tracking
        self.consistency_violations = 0

    def reset_eval(self):
        """Start a brand new evaluation."""
        self.state          = 'EVAL'
        self.equity         = START_BAL
        self.eod_peak       = START_BAL
        self.dd_threshold   = START_BAL - MAX_DD
        self.daily_loss     = 0.0
        self.days_in_state  = 0
        self.funded_pcount  = 0            # payouts in THIS funded session
        self.funded_pnls    = []           # trade PnLs in THIS funded session (for consistency rule)
        self.funded_total_profit = 0.0

    def reset_funded(self):
        """Transition from eval-passed into a fresh funded account."""
        self.state          = 'FUNDED'
        self.equity         = START_BAL
        self.eod_peak       = START_BAL
        self.dd_threshold   = START_BAL - MAX_DD
        self.daily_loss     = 0.0
        self.days_in_state  = 0
        self.funded_pcount  = 0
        self.funded_pnls    = []
        self.funded_total_profit = 0.0

    def eod_update(self):
        """Call once per day boundary."""
        self.days_in_state += 1
        self.daily_loss = 0.0   # reset daily loss limit
        # Trail the drawdown
        if self.equity > self.eod_peak:
            self.eod_peak = self.equity
            new_floor = self.eod_peak - MAX_DD
            if self.state == 'FUNDED':
                new_floor = min(new_floor, START_BAL)   # lock at start bal
            if new_floor > self.dd_threshold:
                self.dd_threshold = new_floor

    def blow_account(self, event_date):
        self.events.append({'date': event_date, 'type': 'blown'})
        self.evals_blown += 1
        self.total_fees  += EVAL_FEE    # buy new eval immediately
        self.evals_taken += 1
        self.reset_eval()
        # Streak: count the loss
        if self.cur_win_streak > 0:
            self.win_streaks.append(self.cur_win_streak)
            self.cur_win_streak = 0
        self.cur_lose_streak += 1

    def retire_account(self, event_date):
        self.events.append({'date': event_date, 'type': 'retired'})
        self.accounts_retired += 1
        self.total_fees  += EVAL_FEE    # buy new eval immediately
        self.evals_taken += 1
        self.reset_eval()
        self.cur_win_streak = 0
        self.cur_lose_streak = 0

    def process_trade(self, event_date, trade_pnl_pts, contracts, net_pts):
        """
        Apply a completed trade.
        Returns: 'ok', 'blown', 'payout'
        """
        net_pnl = net_pts * 20.0 * contracts

        # ── Streak tracking ──
        if net_pnl > 0:
            if self.cur_lose_streak > 0:
                self.lose_streaks.append(self.cur_lose_streak)
                self.cur_lose_streak = 0
            self.cur_win_streak += 1
        else:
            if self.cur_win_streak > 0:
                self.win_streaks.append(self.cur_win_streak)
                self.cur_win_streak = 0
            self.cur_lose_streak += 1

        self.equity += net_pnl

        # Track daily loss
        if net_pnl < 0:
            self.daily_loss += abs(net_pnl)

        # Track funded session PnL for consistency rule
        if self.state == 'FUNDED':
            self.funded_pnls.append(net_pnl)
            self.funded_total_profit += max(net_pnl, 0)  # only count wins

        # ── Check DD breach ──
        if self.equity <= self.dd_threshold:
            self.blow_account(event_date)
            return 'blown'

        # ── Check state targets ──
        if self.state == 'EVAL':
            if self.equity >= START_BAL + EVAL_TARGET:
                self.events.append({'date': event_date, 'type': 'passed'})
                self.evals_passed += 1
                self.total_fees   += ACTIVATION_FEE
                self.eval_pass_days_list.append(self.days_in_state)
                self.reset_funded()
                return 'passed'

        elif self.state == 'FUNDED':
            if self.equity >= FUNDED_TARGET:
                # Check consistency rule before paying out
                if len(self.funded_pnls) > 0 and self.funded_total_profit > 0:
                    max_single = max(self.funded_pnls)
                    if max_single > CONSISTENCY_MAX * self.funded_total_profit:
                        # Payout BLOCKED — keep trading until ratio improves
                        self.consistency_violations += 1
                        return 'consistency_blocked'

                # PAYOUT!
                self.funded_pcount        += 1
                self.total_payouts_count  += 1
                self.total_payouts_usd    += PAYOUT_AMT

                if self.funded_pcount == 1:
                    self.payouts_1st += 1
                    self.payout1_days_list.append(self.days_in_state)
                elif self.funded_pcount == 2:
                    self.payouts_2nd += 1
                    self.payout2_days_list.append(self.days_in_state)

                self.equity -= PAYOUT_AMT

                if self.funded_pcount >= MAX_PAYOUTS:
                    self.retire_account(event_date)
                    return 'retired'
                else:
                    self.events.append({'date': event_date, 'type': 'payout'})
                    self.eod_peak = self.equity       # reset peak after withdrawal
                    self.dd_threshold = self.eod_peak - MAX_DD
                    self.daily_loss      = 0.0
                    self.days_in_state   = 0
                    self.funded_pnls     = []
                    self.funded_total_profit = 0.0
                    return 'payout'

        return 'ok'


import json

def run_simulation():
    print("Loading NSX dataset...")
    df = pd.read_csv(r"C:\Users\kingcuber\.gemini\antigravity-ide\scratch\nsx_cleaned_2010_2024.csv")
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df.set_index('timestamp', inplace=True)
    df = df.between_time('09:30', '16:00')
    df['date'] = df.index.date
    days = df['date'].unique()
    
    # Load volatility data
    with open(r"C:\Users\kingcuber\.gemini\antigravity-ide\brain\8370803b-9474-4100-8b6b-158135823a70\scratch\volatility_data.json", 'r') as f:
        vol_data = json.load(f)
        
    print(f"Loaded {len(days)} days of NSX data. Extracting signals with ATR > 100 filter...")

    # ── Signal extraction (ICT Silver Bullet, 1R) ──
    trades = []
    for d in days:
        date_str = str(d)
        
        # Volatility Filter: Skip days where ATR <= 100
        if date_str not in vol_data:
            continue
        if vol_data[date_str].get('atr') is None or vol_data[date_str]['atr'] <= 100:
            continue
            
        day_df = df[df['date'] == d]
        liq_start = pd.Timestamp(f"{d} 09:30:00").tz_localize('US/Eastern')
        liq_end   = pd.Timestamp(f"{d} 09:59:00").tz_localize('US/Eastern')
        if liq_end not in day_df.index: continue
        liq_data = day_df.loc[liq_start:liq_end]
        if len(liq_data) == 0: continue
        liq_high, liq_low = liq_data['high'].max(), liq_data['low'].min()

        sb_start = pd.Timestamp(f"{d} 10:00:00").tz_localize('US/Eastern')
        sb_end   = pd.Timestamp(f"{d} 11:00:00").tz_localize('US/Eastern')
        sb_window = day_df.loc[sb_start:sb_end]
        if len(sb_window) < 3: continue

        state = 'WAITING'; sweep_extreme = 0
        c1_h = c1_l = c2_h = c2_l = None

        for ts, row in sb_window.iterrows():
            h, l, c = row['high'], row['low'], row['close']
            c3_h, c3_l = h, l
            if state == 'WAITING':
                if l < liq_low:   state = 'SWEEPING_LOW';  sweep_extreme = l
                elif h > liq_high: state = 'SWEEPING_HIGH'; sweep_extreme = h
            elif state == 'SWEEPING_LOW':
                if l < sweep_extreme: sweep_extreme = l
                if c1_h is not None and c1_h < c3_l and c > c1_h:
                    trades.append({'time': ts, 'is_long': True,  'entry': c3_l, 'sl': sweep_extreme - 1.0, 'day': d})
                    break
            elif state == 'SWEEPING_HIGH':
                if h > sweep_extreme: sweep_extreme = h
                if c1_l is not None and c1_l > c3_h and c < c1_l:
                    trades.append({'time': ts, 'is_long': False, 'entry': c3_h, 'sl': sweep_extreme + 1.0, 'day': d})
                    break
            c1_h, c1_l = c2_h, c2_l
            c2_h, c2_l = c3_h, c3_l

    am_trades = trades[:]   # AM Silver Bullet trades (already extracted)
    print(f"Found {len(am_trades)} AM trades.")

    # ── PM Signal Extraction (Sweep 1:30-1:59, FVG Entry 2:00-3:00) ──
    pm_trades = []
    for d in days:
        day_df = df[df['date'] == d]
        liq_start = pd.Timestamp(f"{d} 13:30:00").tz_localize('US/Eastern')
        liq_end   = pd.Timestamp(f"{d} 13:59:00").tz_localize('US/Eastern')
        if liq_start not in day_df.index or liq_end not in day_df.index: continue
        liq_data = day_df.loc[liq_start:liq_end]
        if len(liq_data) == 0: continue
        liq_high, liq_low = liq_data['high'].max(), liq_data['low'].min()

        sb_start = pd.Timestamp(f"{d} 14:00:00").tz_localize('US/Eastern')
        sb_end   = pd.Timestamp(f"{d} 15:00:00").tz_localize('US/Eastern')
        sb_window = day_df.loc[sb_start:sb_end]
        if len(sb_window) < 3: continue

        state = 'WAITING'; sweep_extreme = 0
        c1_h = c1_l = c2_h = c2_l = None
        for ts, row in sb_window.iterrows():
            h, l, c = row['high'], row['low'], row['close']
            c3_h, c3_l = h, l
            if state == 'WAITING':
                if l < liq_low:    state = 'SWEEPING_LOW';  sweep_extreme = l
                elif h > liq_high: state = 'SWEEPING_HIGH'; sweep_extreme = h
            elif state == 'SWEEPING_LOW':
                if l < sweep_extreme: sweep_extreme = l
                if c1_h is not None and c1_h < c3_l and c > c1_h:
                    pm_trades.append({'time': ts, 'is_long': True,  'entry': c3_l, 'sl': sweep_extreme - 1.0, 'day': d, 'session': 'PM'})
                    break
            elif state == 'SWEEPING_HIGH':
                if h > sweep_extreme: sweep_extreme = h
                if c1_l is not None and c1_l > c3_h and c < c1_l:
                    pm_trades.append({'time': ts, 'is_long': False, 'entry': c3_h, 'sl': sweep_extreme + 1.0, 'day': d, 'session': 'PM'})
                    break
            c1_h, c1_l = c2_h, c2_l
            c2_h, c2_l = c3_h, c3_l

    print(f"Found {len(pm_trades)} PM trades.")

    # Tag AM trades with session
    for t in am_trades: t['session'] = 'AM'

    # Combined: sort all trades chronologically
    combined_trades = sorted(am_trades + pm_trades, key=lambda x: x['time'])
    print(f"Combined: {len(combined_trades)} total trades.")

    # Pre-load arrays for fast trade resolution
    df_index  = df.index.values
    df_highs  = df['high'].values
    df_lows   = df['low'].values
    df_closes = df['close'].values
    df_dates  = df['date'].values

    def is_nfp_day(date_str):
        dt = pd.to_datetime(date_str)
        return dt.dayofweek == 4 and 1 <= dt.day <= 7

    am_pm_combined = am_trades + pm_trades
    am_pm_no_nfp = [t for t in am_pm_combined if not is_nfp_day(t['day'])]

    print(f"AM+PM Combined (With NFP): {len(am_pm_combined)} trades.")
    print(f"AM+PM Combined (No NFP): {len(am_pm_no_nfp)} trades.")

    scenarios = [
        ('AM+PM (With NFP)', am_pm_combined),
        ('AM+PM (No NFP)', am_pm_no_nfp),
    ]
    scenario_results = {}

    for scenario_name, trade_list in scenarios:
        print(f"\nRunning {scenario_name} ({len(trade_list)} trades, {NUM_ACCOUNTS} accounts)...")
        accounts = [PropAccount(i) for i in range(NUM_ACCOUNTS)]
        net_profit = - (NUM_ACCOUNTS * EVAL_FEE)
        daily_empire_equity = {}

        trades_list = trade_list
        trades_list.sort(key=lambda x: x['time'])
        current_day = None
        
        for t in trades_list:
            # EOD boundary
            if current_day is not None and t['day'] != current_day:
                for acc in accounts:
                    acc.eod_update()
            current_day = t['day']

            is_long   = t['is_long']
            entry     = t['entry']
            sl        = t['sl']
            risk_pts  = abs(entry - sl)
            if risk_pts < 0.25: continue

            tp = (entry + risk_pts * TARGET_R) if is_long else (entry - risk_pts * TARGET_R)

            start_idx = int(np.searchsorted(df_index, t['time'].to_numpy()))
            max_scan  = min(start_idx + 1500, len(df_index))
            fh_arr = df_highs[start_idx:max_scan]
            fl_arr = df_lows[start_idx:max_scan]
            fd_arr = df_dates[start_idx:max_scan]
            fc_arr = df_closes[start_idx:max_scan]

            # Resolve trade outcome (True execution engine)
            res_pts   = 0
            trade_day = current_day
            filled    = False

            for i in range(len(fh_arr)):
                h, l = fh_arr[i], fl_arr[i]
                if fd_arr[i] != trade_day:
                    trade_day = fd_arr[i]
                    break  # Cancel pending order or close EOD
                
                if not filled:
                    # Check if limit order gets filled
                    if is_long:
                        if l <= entry:
                            filled = True
                            # Check if the SAME candle also hit stop loss
                            if l <= sl:
                                res_pts = sl - entry
                                break
                            # If it hits TP in the exact same candle, assume loss to be conservative
                            if h >= tp:
                                res_pts = sl - entry
                                break
                    else: # SHORT
                        if h >= entry:
                            filled = True
                            if h >= sl:
                                res_pts = entry - sl
                                break
                            if l <= tp:
                                res_pts = entry - sl # Conservative loss if both hit in 1 min
                                break
                else:
                    # Already filled, normal TP/SL check
                    if is_long:
                        if l <= sl: res_pts = sl - entry; break
                        if h >= tp: res_pts = tp - entry; break
                    else:
                        if h >= sl: res_pts = entry - sl; break
                        if l <= tp: res_pts = entry - tp; break

            # If order was never filled, skip it
            if not filled:
                daily_empire_equity[current_day] = net_profit
                continue

            if res_pts == 0:
                last_close = fc_arr[-1]
                res_pts = (last_close - entry) if is_long else (entry - last_close)

            net_pts = res_pts - PENALTY_PTS

            # Apply trade to every account
            for acc in accounts:
                # Skip if daily loss limit already hit
                if acc.daily_loss >= DAILY_LOSS_LIMIT: continue

                # Contract sizing capped by account state
                # Dynamic Risk Scaling turned off - flat risk for 100k accounts
                current_risk_amt = RISK_AMT
                
                max_c = MAX_CONTRACTS_EVAL if acc.state == 'EVAL' else MAX_CONTRACTS_FUNDED
                contracts = min(current_risk_amt / (risk_pts * 20.0), max_c)

                # Intraday floating DD check (worst-case float = stop hit)
                worst_float_pnl = (-risk_pts * 20.0 * contracts)
                if acc.equity + worst_float_pnl <= acc.dd_threshold:
                    acc.blow_account(t['time'].date())
                    continue

                # Process standard trade resolution
                res = acc.process_trade(t['time'].date(), res_pts, contracts, net_pts)

        # Flush final streaks
        for acc in accounts:
            if acc.cur_win_streak  > 0: acc.win_streaks.append(acc.cur_win_streak)
            if acc.cur_lose_streak > 0: acc.lose_streaks.append(acc.cur_lose_streak)
            
        # Record final day for any missing dates
        daily_empire_equity[current_day] = net_profit

        # --- Aggregate Results ---
        total_payouts_usd  = sum(a.total_payouts_usd  for a in accounts)
        total_fees         = sum(a.total_fees          for a in accounts)
        total_evals_taken  = sum(a.evals_taken         for a in accounts)
        total_evals_passed = sum(a.evals_passed        for a in accounts)
        total_blown        = sum(a.evals_blown         for a in accounts)
        total_payouts      = sum(a.total_payouts_count for a in accounts)
        total_retired      = sum(a.accounts_retired    for a in accounts)
        total_1st          = sum(a.payouts_1st         for a in accounts)
        total_2nd          = sum(a.payouts_2nd         for a in accounts)
        total_consistency  = sum(a.consistency_violations for a in accounts)
        net_profit = total_payouts_usd - total_fees

        # Timing averages (pool all accounts)
        all_eval_days = [d for a in accounts for d in a.eval_pass_days_list]
        all_p1_days   = [d for a in accounts for d in a.payout1_days_list]
        all_p2_days   = [d for a in accounts for d in a.payout2_days_list]
        all_win_str   = [s for a in accounts for s in a.win_streaks]
        all_lose_str  = [s for a in accounts for s in a.lose_streaks]

        pass_rate = (total_evals_passed / total_evals_taken * 100) if total_evals_taken else 0
        p1_rate   = (total_1st / total_evals_passed * 100) if total_evals_passed else 0
        p2_rate   = (total_2nd / total_1st * 100) if total_1st else 0
        years     = 14.0
        months    = years * 12
        monthly   = net_profit / months
        yearly    = net_profit / years

        scenario_results[scenario_name] = {
            'net_profit': net_profit,
            'gross': total_payouts_usd,
            'fees': total_fees,
            'monthly': monthly,
            'yearly': yearly,
            'evals_taken': total_evals_taken,
            'evals_passed': total_evals_passed,
            'blown': total_blown,
            'payouts': total_payouts,
            'p1_rate': p1_rate,
            'p2_rate': p2_rate,
            'pass_rate': pass_rate,
            'consistency': total_consistency,
            'avg_eval_d': np.mean(all_eval_days) if all_eval_days else 0,
            'avg_p1_d':   np.mean(all_p1_days)   if all_p1_days   else 0,
            'avg_p2_d':   np.mean(all_p2_days)   if all_p2_days   else 0,
            'avg_win':    np.mean(all_win_str)    if all_win_str   else 0,
            'max_win':    int(np.max(all_win_str))    if all_win_str   else 0,
            'avg_lose':   np.mean(all_lose_str)   if all_lose_str  else 0,
            'max_lose':   int(np.max(all_lose_str))   if all_lose_str  else 0,
            'accounts': accounts,
            'daily_equity': daily_empire_equity.copy(),
        }
        print(f"  -> Net: ${net_profit:,.0f} | Monthly: ${monthly:,.0f} | Payouts: {total_payouts} | Retired: {total_retired} | Blown: {total_blown}")

    # ─── Build Final Comparison Report ──────────────────────────────────
    report  = "# AM vs PM vs Combined Silver Bullet — 20-Account Empire (2010-2024 NSX)\n\n"
    report += "**Rules:** $250 Risk | 1R Target | EOD DD $2k | Daily Loss Limit $1k | Consistency Rule 50% | 4 Mini Cap Funded\n\n"
    report += "---\n\n"

    # Summary comparison table
    report += "## Side-by-Side Comparison\n\n"
    cols = ['AM+PM (With NFP)', 'AM+PM (No NFP)']
    report += f"| Metric | AM+PM (With NFP) | AM+PM (No NFP) |\n|---|---|---|\n"
    metrics = [
        ('Net Profit (15yr, 20 accs)', 'net_profit', '${:,.0f}'),
        ('Monthly Avg Income',         'monthly',    '${:,.0f}/mo'),
        ('Yearly Avg Income',          'yearly',     '${:,.0f}/yr'),
        ('Gross Payouts',              'gross',      '${:,.0f}'),
        ('Total Fees',                 'fees',       '${:,.0f}'),
        ('Eval Pass Rate',             'pass_rate',  '{:.1f}%'),
        ('1st Payout Rate',            'p1_rate',    '{:.1f}%'),
        ('2nd Payout Rate',            'p2_rate',    '{:.1f}%'),
        ('Total Payouts Collected',    'payouts',    '{}'),
        ('Evals Blown',                'blown',      '{}'),
        ('Consistency Violations',     'consistency','{}'),
        ('Avg Days to Pass Eval',      'avg_eval_d', '{:.1f} days'),
        ('Avg Days to 1st Payout',     'avg_p1_d',   '{:.1f} days'),
        ('Avg Days to 2nd Payout',     'avg_p2_d',   '{:.1f} days'),
        ('Avg Win Streak',             'avg_win',    '{:.1f}'),
        ('Max Win Streak',             'max_win',    '{}'),
        ('Avg Lose Streak',            'avg_lose',   '{:.1f}'),
        ('Max Lose Streak',            'max_lose',   '{}'),
    ]
    for label, key, fmt in metrics:
        vals = [fmt.format(scenario_results[c][key]) for c in cols]
        report += f"| {label} | {vals[0]} | {vals[1]} |\n"

    # Add Yearly Breakdown
    report += "\n## Yearly Performance Breakdown\n\n"
    report += f"| Year | AM+PM (With NFP) | AM+PM (No NFP) |\n|---|---|---|\n"
    
    # Process yearly eq for both
    yearly_data = {}
    for c in cols:
        eq_dict = scenario_results[c]['daily_equity']
        if not eq_dict: continue
        eq_df = pd.DataFrame(list(eq_dict.items()), columns=['date', 'net'])
        eq_df['date'] = pd.to_datetime(eq_df['date'])
        eq_df.set_index('date', inplace=True)
        # resample to year end
        ydf = eq_df.resample('YE')['net'].last().ffill().diff().fillna(eq_df.resample('YE')['net'].last().iloc[0])
        for year, val in ydf.items():
            y_str = str(year.year)
            if y_str not in yearly_data: yearly_data[y_str] = {}
            yearly_data[y_str][c] = val
            
    for y_str in sorted(yearly_data.keys()):
        v0 = yearly_data[y_str].get(cols[0], 0)
        v1 = yearly_data[y_str].get(cols[1], 0)
        report += f"| {y_str} | ${v0:,.0f} | ${v1:,.0f} |\n"

    out_path = r"C:\Users\kingcuber\.gemini\antigravity-ide\brain\8370803b-9474-4100-8b6b-158135823a70\scratch\empire_results.md"
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)

    # Compile all events across accounts
    all_events = []
    # Note: For the event compilation, we need to gather events from the scenario we want.
    # We will gather events from the 'AM+PM (No NFP)' scenario accounts.
    # To do this correctly, we need access to the accounts array. Let's just track it globally or run a specific report.
    pass

    print(f"\nDone! Full comparison report saved to empire_results.md")
    return scenario_results # Changed to return so we can access from caller
