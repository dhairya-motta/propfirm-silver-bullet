from data_loader import load_nsx_data, get_nfp_dates, load_volatility_data
from trade_extractor import extract_trades
from prop_simulator import simulate_trades
import numpy as np
import warnings
warnings.filterwarnings('ignore')

def get_metrics(accounts):
    total_evals_taken = sum([a.evals_taken for a in accounts])
    total_evals_passed = sum([a.evals_passed for a in accounts])
    total_blown = sum([a.evals_blown for a in accounts])
    total_payouts = sum([a.total_payouts_count for a in accounts])
    total_payouts_usd = sum([a.total_payouts_usd for a in accounts])
    total_fees = sum([a.total_fees for a in accounts])
    net_profit = total_payouts_usd - total_fees
    pass_rate = (total_evals_passed / total_evals_taken) * 100 if total_evals_taken > 0 else 0
    return {
        'net_profit': net_profit,
        'gross': total_payouts_usd,
        'fees': total_fees,
        'evals_blown': total_blown,
        'evals_passed': total_evals_passed,
        'payouts': total_payouts,
        'pass_rate': pass_rate
    }

def print_markdown_table(results):
    print("| Scenario | Net Profit | Gross Payouts | Fees Paid | Blown Evals | Passed Evals | Total Payouts | Pass Rate |")
    print("|---|---|---|---|---|---|---|---|")
    for name, m in results.items():
        print(f"| {name} | ${m['net_profit']:,.0f} | ${m['gross']:,.0f} | ${m['fees']:,.0f} | {m['evals_blown']} | {m['evals_passed']} | {m['payouts']} | {m['pass_rate']:.1f}% |")

def main():
    nsx_path = r"C:\Users\kingcuber\.gemini\antigravity-ide\scratch\nsx_cleaned_2010_2024.csv"
    vol_path = r"C:\Users\kingcuber\.gemini\antigravity-ide\scratch\propfirm-silver-bullet\volatility_data.json"
    
    df = load_nsx_data(nsx_path)
    nfp_dates = get_nfp_dates(df)
    vol_data = load_volatility_data(vol_path)
    
    scenarios = [
        {'name': 'AM+PM (No NFP) [No Filter]', 'session': 'AM+PM', 'nfp': False, 'filter': False},
        {'name': 'AM+PM (No NFP) [ATR Filter]', 'session': 'AM+PM', 'nfp': False, 'filter': True},
        {'name': 'AM Only (No NFP) [No Filter]', 'session': 'AM', 'nfp': False, 'filter': False},
        {'name': 'AM Only (No NFP) [ATR Filter]', 'session': 'AM', 'nfp': False, 'filter': True},
        {'name': 'PM Only (No NFP) [No Filter]', 'session': 'PM', 'nfp': False, 'filter': False},
        {'name': 'PM Only (No NFP) [ATR Filter]', 'session': 'PM', 'nfp': False, 'filter': True},
        {'name': 'AM+PM (With NFP) [ATR Filter]', 'session': 'AM+PM', 'nfp': True, 'filter': True}
    ]
    
    results = {}
    print("\n--- Running Permutations ---")
    for s in scenarios:
        print(f"Running {s['name']}...")
        trades = extract_trades(df, vol_data, nfp_dates, use_filter=s['filter'], use_nfp=s['nfp'], session=s['session'])
        if len(trades) == 0:
            print("  -> 0 trades found.")
            continue
        accounts, _ = simulate_trades(trades, df, num_accounts=20)
        results[s['name']] = get_metrics(accounts)
        
    print("\n\n=== RESULTS TABLE ===")
    print_markdown_table(results)

if __name__ == "__main__":
    main()
