"""Look-ahead fix impact — NIFTYBEES (index reference): old (CONFIRM_LAG=0) vs fixed (=5)."""
import warnings, sys, os
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_macd_momentum as B
from backtest_macd_momentum import _run_backtest, MacdMomentumStrategy as S
S.macd_cross_exit_enabled=True; S.macd_cross_exit_loss_only=False
S.entry_15m_confirm=False; S.exit_15m_cross=False; S.entry_adx_min=0.0; S.profit_target_pct=0.0
B.DATA_FILE = B.HERE/'data'/'NIFTYBEES_15m.feather'

def run(lag, use_2yr):
    B.CONFIRM_LAG = lag
    data = B.load_data(use_2yr=use_2yr)
    r = _run_backtest(data, S, 'long', f'lag{lag}')
    st = r['_stats']
    return {'lag': lag, 'window': '2yr' if use_2yr else '10yr', 'trades': r['trades'],
            'sharpe_net': round(r['sharpe_net'], 3), 'return%': round(r['return_pct'], 1),
            'maxDD%': round(r['max_dd'], 2), 'WR%': round(r['win_rate'], 1), 'PF': round(r['profit_factor'], 2),
            'expectancy%': round(float(st.get('Expectancy [%]', 0)), 3)}

rows = []
for win in [True, False]:
    for lag in [0, 5]:
        rows.append(run(lag, win)); print('done', rows[-1]['window'], 'lag', lag, 'Sharpe', rows[-1]['sharpe_net'], flush=True)

import pandas as pd
df = pd.DataFrame(rows)
print('\n' + '=' * 64)
print('  LOOK-AHEAD FIX IMPACT — NIFTYBEES (lag0=old/biased, lag5=fixed)')
print('=' * 64)
print(df.to_string(index=False))
for win in ['2yr', '10yr']:
    d = df[df['window'] == win].set_index('lag')
    drop = d.loc[5, 'sharpe_net'] - d.loc[0, 'sharpe_net']
    print(f"  {win}: Sharpe {d.loc[0,'sharpe_net']} (old) -> {d.loc[5,'sharpe_net']} (fixed) | delta {drop:+.3f}")
df.to_csv('lookahead_compare.csv', index=False)
print('\n  Saved: lookahead_compare.csv')
