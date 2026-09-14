import pandas as pd

def extract_trades(df, vol_data, nfp_dates, use_filter=True, use_nfp=False, session='AM+PM'):
    """
    Extracts True Limit Execution trades from the NSX dataset.
    """
    days = df['date'].unique()
    trades = []
    
    for d in days:
        date_str = str(d)
        
        # Volatility Filter
        if use_filter:
            if date_str not in vol_data: continue
            if vol_data[date_str].get('atr') is None or vol_data[date_str]['atr'] <= 100:
                continue
                
        # NFP Filter
        if not use_nfp and d in nfp_dates:
            continue
            
        day_df = df[df['date'] == d]
        
        # AM Session
        if session in ['AM', 'AM+PM']:
            liq_start = pd.Timestamp(f"{d} 09:30:00").tz_localize('US/Eastern')
            liq_end   = pd.Timestamp(f"{d} 09:59:00").tz_localize('US/Eastern')
            sb_start  = pd.Timestamp(f"{d} 10:00:00").tz_localize('US/Eastern')
            sb_end    = pd.Timestamp(f"{d} 11:00:00").tz_localize('US/Eastern')
            
            if liq_end in day_df.index:
                liq_data = day_df.loc[liq_start:liq_end]
                if len(liq_data) > 0:
                    liq_high, liq_low = liq_data['high'].max(), liq_data['low'].min()
                    sb_window = day_df.loc[sb_start:sb_end]
                    
                    if len(sb_window) >= 3:
                        state = 'WAITING'; sweep_extreme = 0
                        for ts, row in sb_window.iterrows():
                            h, l, c = row['high'], row['low'], row['close']
                            if state == 'WAITING':
                                if l < liq_low:   state = 'SWEEPING_LOW';  sweep_extreme = l
                                elif h > liq_high: state = 'SWEEPING_HIGH'; sweep_extreme = h
                            elif state == 'SWEEPING_LOW':
                                if l < sweep_extreme: sweep_extreme = l
                                if c > liq_low: # Close back above liquidity
                                    trades.append({'date': d, 'time': ts, 'is_long': True, 'entry': c, 'sweep': sweep_extreme, 'session': 'AM'})
                                    break
                            elif state == 'SWEEPING_HIGH':
                                if h > sweep_extreme: sweep_extreme = h
                                if c < liq_high: # Close back below liquidity
                                    trades.append({'date': d, 'time': ts, 'is_long': False, 'entry': c, 'sweep': sweep_extreme, 'session': 'AM'})
                                    break
                                    
        # PM Session
        if session in ['PM', 'AM+PM']:
            liq_start = pd.Timestamp(f"{d} 13:30:00").tz_localize('US/Eastern')
            liq_end   = pd.Timestamp(f"{d} 13:59:00").tz_localize('US/Eastern')
            sb_start  = pd.Timestamp(f"{d} 14:00:00").tz_localize('US/Eastern')
            sb_end    = pd.Timestamp(f"{d} 15:00:00").tz_localize('US/Eastern')
            
            if liq_end in day_df.index:
                liq_data = day_df.loc[liq_start:liq_end]
                if len(liq_data) > 0:
                    liq_high, liq_low = liq_data['high'].max(), liq_data['low'].min()
                    sb_window = day_df.loc[sb_start:sb_end]
                    
                    if len(sb_window) >= 3:
                        state = 'WAITING'; sweep_extreme = 0
                        for ts, row in sb_window.iterrows():
                            h, l, c = row['high'], row['low'], row['close']
                            if state == 'WAITING':
                                if l < liq_low:   state = 'SWEEPING_LOW';  sweep_extreme = l
                                elif h > liq_high: state = 'SWEEPING_HIGH'; sweep_extreme = h
                            elif state == 'SWEEPING_LOW':
                                if l < sweep_extreme: sweep_extreme = l
                                if c > liq_low:
                                    trades.append({'date': d, 'time': ts, 'is_long': True, 'entry': c, 'sweep': sweep_extreme, 'session': 'PM'})
                                    break
                            elif state == 'SWEEPING_HIGH':
                                if h > sweep_extreme: sweep_extreme = h
                                if c < liq_high:
                                    trades.append({'date': d, 'time': ts, 'is_long': False, 'entry': c, 'sweep': sweep_extreme, 'session': 'PM'})
                                    break
                                    
    return trades
