import pandas as pd
import json

def load_nsx_data(filepath):
    print(f"Loading NSX dataset from {filepath}...")
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    df.set_index('timestamp', inplace=True)
    df = df.between_time('09:30', '16:00')
    df['date'] = df.index.date
    return df

def get_nfp_dates(df):
    """
    Identifies the first Friday of every month (Non-Farm Payroll day).
    """
    first_fridays = df.groupby([df.index.year, df.index.month]).apply(
        lambda x: x[x.index.dayofweek == 4].index.min()
    ).dropna()
    return set(first_fridays.dt.date)

def load_volatility_data(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)
