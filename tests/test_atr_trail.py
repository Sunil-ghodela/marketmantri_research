"""Unit tests for the chandelier (ATR-trailing) stop arithmetic used by MacdMomentumStrategy.

The strategy's ATR-trail exit is a chandelier stop: stop = high-water-mark - mult * ATR.
We test the pure arithmetic helper so the trailing math is verified independent of the
backtesting.py integration (which is verified separately by backtest on real data).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy_macd_momentum import chandelier_long_stop


def test_basic_stop_below_hwm():
    # Arrange / Act
    stop = chandelier_long_stop(hwm=100.0, atr=2.0, mult=3.0)
    # Assert: 100 - 3*2 = 94
    assert stop == 94.0


def test_tighter_mult_raises_stop():
    loose = chandelier_long_stop(hwm=100.0, atr=2.0, mult=3.0)
    tight = chandelier_long_stop(hwm=100.0, atr=2.0, mult=1.5)
    assert tight > loose          # smaller multiplier -> stop closer to price


def test_higher_atr_lowers_stop():
    calm = chandelier_long_stop(hwm=100.0, atr=1.0, mult=3.0)
    wild = chandelier_long_stop(hwm=100.0, atr=4.0, mult=3.0)
    assert wild < calm            # more volatility -> wider (lower) stop


def test_zero_mult_stop_equals_hwm():
    assert chandelier_long_stop(hwm=100.0, atr=5.0, mult=0.0) == 100.0
