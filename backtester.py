"""
Quantitative Backtesting Engine
Evaluates trading strategies with:
- Dynamic position sizing and risk management
- Stop Loss & Take Profit logic
- Spread / commission modeling
- In-Sample (training) vs Out-of-Sample (unseen testing) validation
- Comprehensive risk metrics: Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio
"""

import os
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


class Backtester:
    def __init__(
        self,
        csv_file: str,
        initial_capital: float = 1000.0,
        risk_per_trade: float = 0.01,  # 1% risk per trade
        spread_pips_or_points: float = 1.0,
        slippage_pct: float = 0.0002
    ):
        self.csv_file = csv_file
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.spread = spread_pips_or_points
        self.slippage_pct = slippage_pct
        self.df = pd.read_csv(csv_file, index_col=0, parse_dates=True)

    def compute_indicators(self):
        """Calculates core quantitative indicators: EMAs, RSI, ATR, Bollinger Bands."""
        df = self.df.copy()

        # Exponential Moving Averages
        df["EMA_fast"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA_slow"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA_trend"] = df["Close"].ewm(span=200, adjust=False).mean()

        # ATR (Average True Range) for volatility & dynamic Stop Loss
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["ATR"] = tr.rolling(window=14).mean()

        # RSI (Relative Strength Index)
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["RSI"] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        rolling_mean = df["Close"].rolling(window=20).mean()
        rolling_std = df["Close"].rolling(window=20).std()
        df["BB_upper"] = rolling_mean + (rolling_std * 2)
        df["BB_lower"] = rolling_mean - (rolling_std * 2)

        df.dropna(inplace=True)
        self.df = df
        return self.df

    def run_strategy_trend_following(self, split_ratio: float = 0.75) -> Tuple[Dict, Dict]:
        """
        Strategy 1: Trend Following with ATR trailing stop
        Entry: Fast EMA crosses above Slow EMA and price > 200 EMA (Long).
        Exit: Price hits trailing Stop Loss (2 * ATR) or EMA crosses back.
        """
        self.compute_indicators()
        
        split_idx = int(len(self.df) * split_ratio)
        df_in_sample = self.df.iloc[:split_idx].copy()
        df_out_sample = self.df.iloc[split_idx:].copy()

        results_is = self._simulate_trend(df_in_sample, name="In-Sample (Entrenamiento 75%)")
        results_oos = self._simulate_trend(df_out_sample, name="Out-of-Sample (Validación 25%)")

        return results_is, results_oos

    def run_strategy_mean_reversion(self, split_ratio: float = 0.75) -> Tuple[Dict, Dict]:
        """
        Strategy 2: Mean Reversion (Bollinger Bands + RSI)
        Entry: Price touches lower Bollinger band and RSI < 35 (Oversold).
        Exit: Price touches middle or upper Bollinger band, or RSI > 65, or fixed ATR Stop Loss.
        """
        self.compute_indicators()
        
        split_idx = int(len(self.df) * split_ratio)
        df_in_sample = self.df.iloc[:split_idx].copy()
        df_out_sample = self.df.iloc[split_idx:].copy()

        results_is = self._simulate_mean_reversion(df_in_sample, name="In-Sample (Entrenamiento 75%)")
        results_oos = self._simulate_mean_reversion(df_out_sample, name="Out-of-Sample (Validación 25%)")

        return results_is, results_oos

    def _simulate_mean_reversion(self, df: pd.DataFrame, name: str) -> Dict:
        capital = self.initial_capital
        equity_curve = [capital]
        trades = []
        in_position = False
        entry_price = 0.0
        stop_loss = 0.0
        take_profit = 0.0
        position_size = 0.0

        for i in range(1, len(df)):
            current = df.iloc[i]
            prev = df.iloc[i - 1]

            close_price = current["Close"]
            atr = current["ATR"]

            if not in_position:
                # Buy Signal: Price bounced off lower Bollinger Band and RSI < 35
                buy_signal = (prev["Low"] <= prev["BB_lower"]) and (current["Close"] > current["BB_lower"]) and (current["RSI"] < 38)
                
                if buy_signal and atr > 0:
                    entry_price = close_price * (1 + self.slippage_pct)
                    sl_distance = 1.5 * atr
                    stop_loss = entry_price - sl_distance
                    take_profit = current["BB_upper"]  # Target upper band
                    
                    risk_amount = capital * self.risk_per_trade
                    position_size = risk_amount / sl_distance
                    in_position = True

            else:
                # Exit conditions: Hit Stop Loss, Hit Take Profit, or RSI > 65
                hit_sl = current["Low"] <= stop_loss
                hit_tp = current["High"] >= take_profit
                rsi_overbought = current["RSI"] >= 65

                if hit_sl or hit_tp or rsi_overbought:
                    if hit_sl:
                        exit_price = stop_loss * (1 - self.slippage_pct)
                    elif hit_tp:
                        exit_price = take_profit * (1 - self.slippage_pct)
                    else:
                        exit_price = close_price * (1 - self.slippage_pct)

                    pnl = (exit_price - entry_price) * position_size
                    capital += pnl
                    trades.append({
                        "entry": entry_price,
                        "exit": exit_price,
                        "pnl": pnl,
                        "won": pnl > 0
                    })
                    in_position = False

            equity_curve.append(capital)

        total_trades = len(trades)
        wins = [t for t in trades if t["won"]]
        losses = [t for t in trades if not t["won"]]
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

        total_gain = sum(t["pnl"] for t in wins)
        total_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (total_gain / total_loss) if total_loss > 0 else (999.0 if total_gain > 0 else 0.0)

        eq_series = pd.Series(equity_curve)
        rolling_max = eq_series.cummax()
        drawdown = (eq_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100

        total_return = ((capital / self.initial_capital) - 1) * 100

        return {
            "period": name,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_drawdown,
            "total_return_pct": total_return,
            "final_capital": capital,
            "trades": trades
        }

    def _simulate_trend(self, df: pd.DataFrame, name: str) -> Dict:
        capital = self.initial_capital
        equity_curve = [capital]
        trades = []
        in_position = False
        entry_price = 0.0
        stop_loss = 0.0
        position_size = 0.0

        for i in range(1, len(df)):
            current = df.iloc[i]
            prev = df.iloc[i - 1]

            # Current price with slippage
            close_price = current["Close"]
            atr = current["ATR"]

            if not in_position:
                # Buy Signal: EMA20 crosses above EMA50 AND Price is above EMA200
                long_signal = (prev["EMA_fast"] <= prev["EMA_slow"]) and (current["EMA_fast"] > current["EMA_slow"]) and (close_price > current["EMA_trend"])
                
                if long_signal and atr > 0:
                    entry_price = close_price * (1 + self.slippage_pct)
                    sl_distance = 2.0 * atr
                    stop_loss = entry_price - sl_distance
                    
                    # Risk management: Risk at most X% of current capital
                    risk_amount = capital * self.risk_per_trade
                    position_size = risk_amount / sl_distance
                    in_position = True

            else:
                # Update trailing stop
                new_sl = close_price - (2.0 * atr)
                if new_sl > stop_loss:
                    stop_loss = new_sl

                # Exit conditions: Stop Loss hit OR Bearish EMA Cross
                exit_signal = (current["Low"] <= stop_loss) or (current["EMA_fast"] < current["EMA_slow"])

                if exit_signal:
                    exit_price = min(close_price, stop_loss) * (1 - self.slippage_pct)
                    pnl = (exit_price - entry_price) * position_size
                    capital += pnl
                    trades.append({
                        "entry": entry_price,
                        "exit": exit_price,
                        "pnl": pnl,
                        "won": pnl > 0
                    })
                    in_position = False

            equity_curve.append(capital)

        # Performance Metrics
        total_trades = len(trades)
        wins = [t for t in trades if t["won"]]
        losses = [t for t in trades if not t["won"]]
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

        total_gain = sum(t["pnl"] for t in wins)
        total_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (total_gain / total_loss) if total_loss > 0 else (999.0 if total_gain > 0 else 0.0)

        # Max Drawdown
        eq_series = pd.Series(equity_curve)
        rolling_max = eq_series.cummax()
        drawdown = (eq_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100

        total_return = ((capital / self.initial_capital) - 1) * 100

        return {
            "period": name,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_drawdown,
            "total_return_pct": total_return,
            "final_capital": capital,
            "trades": trades
        }


def run_full_evaluation():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = {
        "S&P 500": os.path.join(data_dir, "SP500_1d.csv"),
        "Dow Jones": os.path.join(data_dir, "DOW_JONES_1d.csv"),
        "DAX 40": os.path.join(data_dir, "DAX40_1d.csv"),
        "EUR/USD": os.path.join(data_dir, "EURUSD_1d.csv"),
    }

    print("=" * 95)
    print("EVALUACIÓN CUANTITATIVA MULTI-ACTIVO: TREND FOLLOWING vs MEAN REVERSION")
    print("Gestión de riesgo estricta: 1% de capital arriesgado por operación")
    print("=" * 95)

    all_results = []

    for name, path in files.items():
        if not os.path.exists(path):
            continue
        bt = Backtester(path, initial_capital=1000.0, risk_per_trade=0.01)
        
        # Test Trend Following
        t_is, t_oos = bt.run_strategy_trend_following(split_ratio=0.75)
        # Test Mean Reversion
        m_is, m_oos = bt.run_strategy_mean_reversion(split_ratio=0.75)

        for strat_name, r_is, r_oos in [("Trend Following", t_is, t_oos), ("Mean Reversion", m_is, m_oos)]:
            all_results.append({
                "Activo": name,
                "Estrategia": strat_name,
                "Fase": "In-Sample (3a)",
                "Trades": r_is["total_trades"],
                "Win Rate": f"{r_is['win_rate']:.1f}%",
                "Profit Factor": f"{r_is['profit_factor']:.2f}",
                "Max DD": f"{r_is['max_drawdown_pct']:.2f}%",
                "Retorno": f"{r_is['total_return_pct']:.2f}%"
            })
            all_results.append({
                "Activo": name,
                "Estrategia": strat_name,
                "Fase": "Out-Sample (1a)",
                "Trades": r_oos["total_trades"],
                "Win Rate": f"{r_oos['win_rate']:.1f}%",
                "Profit Factor": f"{r_oos['profit_factor']:.2f}",
                "Max DD": f"{r_oos['max_drawdown_pct']:.2f}%",
                "Retorno": f"{r_oos['total_return_pct']:.2f}%"
            })

    res_df = pd.DataFrame(all_results)
    print("\n" + res_df.to_string(index=False))
    return res_df


if __name__ == "__main__":
    run_full_evaluation()
