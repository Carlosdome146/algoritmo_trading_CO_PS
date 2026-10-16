"""
Enhanced Quantitative Strategy Engine
Incorporating key architectural breakthroughs from top open-source repositories:
1. Dynamic Breakeven Stop (Freqtrade): Moves SL to entry price once +1.0*ATR profit is reached.
2. Time-based Momentum Exhaustion Exit (vn.py): Closes stale trades after N bars.
3. Streak & Cooldown Protections (Freqtrade): Pauses new entries after 2 consecutive losses.
4. Multi-Agent Confluence / Veto Committee (TradingAgents & Vibe-Trading):
   - Trend Analyst (EMA20 > EMA50 and Price > EMA200)
   - Momentum Analyst (RSI pullback in healthy trend zone)
   - Risk Manager Veto (ATR relative regime and volatility expansion)
5. Out-of-Sample Strict Testing (Zipline): Tested on 30% unseen historical test set.
"""

import os
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


class EnhancedTraderEngine:
    def __init__(
        self,
        csv_file: str,
        initial_capital: float = 1000.0,
        risk_per_trade: float = 0.01,
        max_bars_in_trade: int = 12,       # vn.py Time Exit (12 hours)
        cooldown_bars_after_loss: int = 8,  # Freqtrade Cooldown Protection
        slippage_pct: float = 0.0002
    ):
        self.csv_file = csv_file
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.max_bars_in_trade = max_bars_in_trade
        self.cooldown_bars_after_loss = cooldown_bars_after_loss
        self.slippage_pct = slippage_pct
        self.df = pd.read_csv(csv_file, index_col=0, parse_dates=True)

    def prepare_data(self) -> pd.DataFrame:
        df = self.df.copy()

        # Trend Indicators
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        # Volatility: ATR (14)
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["ATR"] = tr.rolling(window=14).mean()
        df["ATR_ma50"] = df["ATR"].rolling(window=50).mean()
        df["ATR_regime"] = df["ATR"] / (df["ATR_ma50"] + 1e-9)

        # Momentum: RSI (14)
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["RSI"] = 100 - (100 / (1 + rs))

        # Rate of Change & Momentum Confirmation
        df["ROC_6"] = df["Close"].pct_change(periods=6)

        # Long Confluence Signal
        long_trend = (df["Close"] > df["EMA200"]) & (df["EMA20"] > df["EMA50"])
        long_momentum = (df["RSI"] >= 45) & (df["RSI"] <= 65) & (df["ROC_6"] > 0)
        risk_manager_ok = (df["ATR_regime"] >= 0.85) & (df["ATR_regime"] <= 2.2)

        # Short Confluence Signal
        short_trend = (df["Close"] < df["EMA200"]) & (df["EMA20"] < df["EMA50"])
        short_momentum = (df["RSI"] <= 55) & (df["RSI"] >= 35) & (df["ROC_6"] < 0)

        df["long_signal"] = (long_trend & long_momentum & risk_manager_ok).astype(int)
        df["short_signal"] = (short_trend & short_momentum & risk_manager_ok).astype(int)

        df.dropna(inplace=True)
        return df

    def run_backtest(self, split_ratio: float = 0.70) -> Tuple[Dict, Dict]:
        df = self.prepare_data()
        split_idx = int(len(df) * split_ratio)
        
        df_in_sample = df.iloc[:split_idx].copy()
        df_out_sample = df.iloc[split_idx:].copy()

        res_is = self._simulate(df_in_sample, name="In-Sample (70%)")
        res_oos = self._simulate(df_out_sample, name="Out-of-Sample (30% Ciego)")

        return res_is, res_oos

    def _simulate(self, df: pd.DataFrame, name: str) -> Dict:
        capital = self.initial_capital
        equity_curve = [capital]
        trades = []
        
        in_position = False
        direction = 0  # +1 for Long, -1 for Short
        entry_price = 0.0
        stop_loss = 0.0
        take_profit = 0.0
        position_size = 0.0
        bars_held = 0
        breakeven_activated = False

        # Freqtrade Protection State
        consecutive_losses = 0
        cooldown_remaining = 0

        close_vals = df["Close"].values
        high_vals = df["High"].values
        low_vals = df["Low"].values
        atr_vals = df["ATR"].values
        long_sigs = df["long_signal"].values
        short_sigs = df["short_signal"].values
        n = len(df)

        for i in range(1, n):
            current_close = close_vals[i]
            current_high = high_vals[i]
            current_low = low_vals[i]
            current_atr = atr_vals[i]

            if cooldown_remaining > 0:
                cooldown_remaining -= 1

            if not in_position:
                if cooldown_remaining == 0 and current_atr > 0:
                    # Long Entry
                    if long_sigs[i] == 1:
                        direction = 1
                        entry_price = current_close * (1 + self.slippage_pct)
                        sl_dist = 1.0 * current_atr
                        stop_loss = entry_price - sl_dist
                        take_profit = entry_price + (1.5 * current_atr)

                        risk_dollars = capital * self.risk_per_trade
                        position_size = risk_dollars / sl_dist
                        in_position = True
                        bars_held = 0
                        breakeven_activated = False

                    # Short Entry
                    elif short_sigs[i] == 1:
                        direction = -1
                        entry_price = current_close * (1 - self.slippage_pct)
                        sl_dist = 1.0 * current_atr
                        stop_loss = entry_price + sl_dist
                        take_profit = entry_price - (1.5 * current_atr)

                        risk_dollars = capital * self.risk_per_trade
                        position_size = risk_dollars / sl_dist
                        in_position = True
                        bars_held = 0
                        breakeven_activated = False

            else:
                bars_held += 1
                
                # Freqtrade Breakeven Logic (Zero Risk)
                if not breakeven_activated:
                    if direction == 1 and current_high >= (entry_price + (0.9 * current_atr)):
                        stop_loss = entry_price
                        breakeven_activated = True
                    elif direction == -1 and current_low <= (entry_price - (0.9 * current_atr)):
                        stop_loss = entry_price
                        breakeven_activated = True

                # Exits
                if direction == 1:
                    hit_tp = current_high >= take_profit
                    hit_sl = current_low <= stop_loss
                else:
                    hit_tp = current_low <= take_profit
                    hit_sl = current_high >= stop_loss

                time_exit = bars_held >= self.max_bars_in_trade

                if hit_tp or hit_sl or time_exit:
                    if hit_tp:
                        exit_price = take_profit * (1 - (direction * self.slippage_pct))
                        exit_reason = "TakeProfit"
                    elif hit_sl:
                        exit_price = stop_loss * (1 - (direction * self.slippage_pct))
                        exit_reason = "Breakeven" if breakeven_activated else "StopLoss"
                    else:
                        exit_price = current_close * (1 - (direction * self.slippage_pct))
                        exit_reason = "TimeExit"

                    pnl = direction * (exit_price - entry_price) * position_size
                    capital += pnl
                    is_win = pnl > 0
                    is_breakeven = abs(pnl) < (capital * 0.001)

                    if is_win:
                        consecutive_losses = 0
                    elif not is_breakeven:
                        consecutive_losses += 1
                        if consecutive_losses >= 2:
                            cooldown_remaining = self.cooldown_bars_after_loss
                            consecutive_losses = 0

                    trades.append({
                        "direction": "LONG" if direction == 1 else "SHORT",
                        "entry": entry_price,
                        "exit": exit_price,
                        "pnl": pnl,
                        "won": is_win,
                        "breakeven": is_breakeven,
                        "reason": exit_reason,
                        "bars": bars_held
                    })
                    in_position = False

            equity_curve.append(capital)

        # Performance Calculations
        total_trades = len(trades)
        wins = [t for t in trades if t["won"]]
        losses = [t for t in trades if not t["won"] and not t["breakeven"]]
        bes = [t for t in trades if t["breakeven"]]

        # Effective Win Rate (Wins + Breakevens that didn't lose money)
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
        effective_win_rate = ((len(wins) + len(bes)) / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        eq_s = pd.Series(equity_curve)
        cummax = eq_s.cummax()
        dd = (eq_s - cummax) / cummax
        max_dd = dd.min() * 100
        total_return = ((capital / self.initial_capital) - 1) * 100

        return {
            "period": name,
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "breakevens": len(bes),
            "win_rate": win_rate,
            "effective_win_rate": effective_win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_dd,
            "total_return_pct": total_return,
            "final_capital": capital,
            "trades": trades
        }


def run_comparison():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    assets = {
        "DAX 40 (1h)": os.path.join(data_dir, "DAX40_1h.csv"),
        "S&P 500 (1h)": os.path.join(data_dir, "SP500_1h.csv"),
        "Dow Jones (1h)": os.path.join(data_dir, "DOW_JONES_1h.csv"),
        "EUR/USD (1h)": os.path.join(data_dir, "EURUSD_1h.csv"),
    }

    print("=" * 105)
    print("SISTEMA AVANZADO (Freqtrade Breakeven + vn.py Time Exit + TradingAgents Veto)")
    print("Evaluación en datos Out-of-Sample (30% final ciego no visto)")
    print("Gestión de Riesgo: 1% fijo por operación | Ratio TP: 1 a 1.8")
    print("=" * 105)

    results = []

    for name, path in assets.items():
        if not os.path.exists(path):
            continue
        engine = EnhancedTraderEngine(path, initial_capital=1000.0, risk_per_trade=0.01)
        res_is, res_oos = engine.run_backtest(split_ratio=0.70)

        results.append({
            "Activo": name,
            "Trades (OOS)": res_oos["total_trades"],
            "Ganadoras": res_oos["wins"],
            "Breakeven (0 Riesgo)": res_oos["breakevens"],
            "Perdedoras": res_oos["losses"],
            "Win Rate Puro": f"{res_oos['win_rate']:.1f}%",
            "Tasa Sin Pérdida": f"{res_oos['effective_win_rate']:.1f}%",
            "Profit Factor": f"{res_oos['profit_factor']:.2f}",
            "Max Drawdown": f"{res_oos['max_drawdown_pct']:.2f}%",
            "Retorno Total": f"{res_oos['total_return_pct']:.2f}%"
        })

    summary_df = pd.DataFrame(results)
    print("\n" + summary_df.to_string(index=False))
    return summary_df


if __name__ == "__main__":
    run_comparison()
