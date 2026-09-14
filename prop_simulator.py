import numpy as np

class PropAccount:
    """
    Simulates a Prop Firm Account through the Evaluation and Funded phases.
    Uses 50k Account Rules ($250 Risk, $2k DD, $1k Daily Loss, $3k Target).
    """
    def __init__(self, start_date):
        self.start_date = start_date
        self.state = 'EVAL'
        self.equity = 50000.0
        self.eod_peak = 50000.0
        self.dd_threshold = 48000.0
        self.daily_loss = 0.0
        self.funded_pcount = 0
        self.days_in_state = 0
        self.funded_total_profit = 0.0
        self.funded_pnls = []
        
        # Stats
        self.total_fees = 49.0
        self.evals_taken = 1
        self.evals_passed = 0
        self.evals_blown = 0
        self.accounts_retired = 0
        self.payouts_1st = 0
        self.payouts_2nd = 0
        self.total_payouts_count = 0
        self.total_payouts_usd = 0.0
        
        # Streaks
        self.win_streaks = []
        self.lose_streaks = []
        self.cur_win_streak = 0
        self.cur_lose_streak = 0

    def reset_eval(self):
        self.state = 'EVAL'
        self.equity = 50000.0
        self.eod_peak = 50000.0
        self.dd_threshold = 48000.0
        self.daily_loss = 0.0
        self.funded_pcount = 0
        self.days_in_state = 0

    def reset_funded(self):
        self.state = 'FUNDED'
        self.equity = 50000.0
        self.eod_peak = 50000.0
        self.dd_threshold = 50000.0
        self.daily_loss = 0.0
        self.funded_pcount = 0
        self.days_in_state = 0
        self.funded_total_profit = 0.0
        self.funded_pnls = []

    def next_day(self):
        self.days_in_state += 1
        self.daily_loss = 0.0
        if self.state == 'FUNDED':
            new_floor = self.eod_peak - 2000.0
            if new_floor < 50000.0: new_floor = 50000.0
            if new_floor > self.dd_threshold:
                self.dd_threshold = new_floor
        else:
            new_floor = self.eod_peak - 2000.0
            if new_floor > self.dd_threshold:
                self.dd_threshold = new_floor

    def blow_account(self):
        self.evals_blown += 1
        self.total_fees += 49.0
        self.evals_taken += 1
        self.reset_eval()
        if self.cur_win_streak > 0:
            self.win_streaks.append(self.cur_win_streak)
            self.cur_win_streak = 0
        self.cur_lose_streak += 1

    def retire_account(self):
        self.accounts_retired += 1
        self.total_fees += 49.0
        self.evals_taken += 1
        self.reset_eval()
        self.cur_win_streak = 0
        self.cur_lose_streak = 0

    def process_trade(self, res_pts, contracts, net_pts):
        net_pnl = net_pts * 20.0 * contracts
        self.equity += net_pnl
        if self.equity > self.eod_peak:
            self.eod_peak = self.equity

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

        if net_pnl < 0:
            self.daily_loss += abs(net_pnl)

        if self.state == 'FUNDED':
            self.funded_pnls.append(net_pnl)
            self.funded_total_profit += max(net_pnl, 0)

        if self.equity <= self.dd_threshold:
            self.blow_account()
            return 'blown'

        if self.state == 'EVAL':
            if self.equity >= 53000.0:
                self.evals_passed += 1
                self.total_fees += 139.0
                self.reset_funded()
                return 'passed'

        elif self.state == 'FUNDED':
            if self.equity >= 51500.0 and self.days_in_state >= 10:
                max_single = max(self.funded_pnls) if self.funded_pnls else 0
                if self.funded_total_profit > 0:
                    if max_single > 0.50 * self.funded_total_profit:
                        return 'consistency_blocked'
                
                self.funded_pcount += 1
                self.total_payouts_count += 1
                self.total_payouts_usd += 1500.0
                
                if self.funded_pcount == 1: self.payouts_1st += 1
                elif self.funded_pcount == 2: self.payouts_2nd += 1
                    
                self.equity -= 1500.0

                if self.funded_pcount >= 6:
                    self.retire_account()
                    return 'retired'
                else:
                    self.eod_peak = self.equity
                    self.dd_threshold = self.eod_peak - 2000.0
                    self.daily_loss = 0.0
                    self.days_in_state = 0
                    self.funded_pnls = []
                    self.funded_total_profit = 0.0
                    return 'payout'
        return 'ok'

def simulate_trades(trades, df, num_accounts=20):
    """
    Simulates tick-by-tick true limit order execution for an array of prop accounts.
    """
    accounts = [PropAccount(trades[0]['date'] if trades else None) for _ in range(num_accounts)]
    df_index = df.index.values
    daily_equity = {}
    
    current_date = None
    TARGET_R = 1.0
    RISK_AMT = 250.0
    PENALTY_PTS = 0.75
    MAX_CONTRACTS_EVAL = 5.0
    MAX_CONTRACTS_FUNDED = 4.0
    DAILY_LOSS_LIMIT = 1000.0

    for t in trades:
        if current_date != t['date']:
            current_date = t['date']
            for acc in accounts:
                acc.next_day()

        entry = t['entry']
        is_long = t['is_long']
        sweep = t['sweep']
        
        if is_long:
            sl = sweep - 1.0
            if sl >= entry: sl = entry - 0.25
            risk_pts = abs(entry - sl)
            tp = entry + (risk_pts * TARGET_R)
        else:
            sl = sweep + 1.0
            if sl <= entry: sl = entry + 0.25
            risk_pts = abs(entry - sl)
            tp = entry - (risk_pts * TARGET_R)

        start_ts = t['time'].to_numpy()
        start_idx = np.searchsorted(df_index, start_ts)
        end_ts = pd.Timestamp(f"{t['date']} 15:59:00").tz_localize('US/Eastern').to_numpy()
        end_idx = np.searchsorted(df_index, end_ts)

        if start_idx >= len(df) or start_idx >= end_idx: continue
        eval_window = df.iloc[start_idx+1:end_idx+1]
        
        res_pts = 0
        filled = False
        
        for idx, row in eval_window.iterrows():
            h, l = row['high'], row['low']
            if not filled:
                if is_long:
                    if l <= entry:
                        filled = True
                        if l <= sl: res_pts = sl - entry; break
                        if h >= tp: res_pts = tp - entry; break
                else:
                    if h >= entry:
                        filled = True
                        if h >= sl: res_pts = entry - sl; break
                        if l <= tp: res_pts = entry - tp; break
            else:
                if is_long:
                    if l <= sl: res_pts = sl - entry; break
                    if h >= tp: res_pts = tp - entry; break
                else:
                    if h >= sl: res_pts = entry - sl; break
                    if l <= tp: res_pts = entry - tp; break

        if not filled: continue
        if res_pts == 0:
            c = eval_window.iloc[-1]['close']
            res_pts = (c - entry) if is_long else (entry - c)
            
        net_pts = res_pts - PENALTY_PTS

        for acc in accounts:
            if acc.daily_loss >= DAILY_LOSS_LIMIT: continue
            
            max_c = MAX_CONTRACTS_EVAL if acc.state == 'EVAL' else MAX_CONTRACTS_FUNDED
            contracts = min(RISK_AMT / (risk_pts * 20.0), max_c)
            
            worst_float_pnl = (-risk_pts * 20.0 * contracts)
            if acc.equity + worst_float_pnl <= acc.dd_threshold:
                acc.blow_account()
                continue
                
            acc.process_trade(res_pts, contracts, net_pts)
            
        daily_equity[current_date] = sum([acc.equity if acc.state=='FUNDED' else 50000 for acc in accounts])

    for acc in accounts:
        if acc.cur_win_streak > 0: acc.win_streaks.append(acc.cur_win_streak)
        if acc.cur_lose_streak > 0: acc.lose_streaks.append(acc.cur_lose_streak)

    return accounts, daily_equity
