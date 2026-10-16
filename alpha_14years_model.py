"""
Multi-Factor Alpha Model (14-Year Walk-Forward Institutional Evaluation)
Inspired by Microsoft Qlib & Top Quantitative Repositories

Dataset: 61,393 continuous hourly candles (2012 - 2026) for DAX 40 (DE40)
Split:
- Training (In-Sample): 2012-08 to 2021-12 (~9.5 years covering European Debt Crisis, Brexit, COVID crash)
- Testing (Out-of-Sample): 2022-01 to 2026-10 (~4.8 years of completely UNSEEN data through inflation, rate hikes, bull markets)

Risk Management: Strict 1% risk per trade with dynamic ATR Stop Loss & Freqtrade Breakeven Lock
"""

import os
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


class PureNumPyLogisticModel:
    def __init__(self, lr: float = 0.05, epochs: int = 1500, lambda_reg: float = 0.03):
        self.lr = lr
        self.epochs = epochs
        self.lambda_reg = lambda_reg
        self.weights = None
        self.bias = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray):
        n_samples, n_features = X.shape
        self.weights = np.zeros(n_features)
        self.bias = 0.0

        for _ in range(self.epochs):
            linear = np.clip(np.dot(X, self.weights) + self.bias, -25.0, 25.0)
            preds = 1.0 / (1.0 + np.exp(-linear))
            err = preds - y
            dw = (1.0 / n_samples) * np.dot(X.T, err) + (self.lambda_reg / n_samples) * self.weights
            db = (1.0 / n_samples) * np.sum(err)
            self.weights -= self.lr * dw
            self.bias -= self.lr * db

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        linear = np.clip(np.dot(X, self.weights) + self.bias, -25.0, 25.0)
        return 1.0 / (1.0 + np.exp(-linear))


class FourteenYearAlphaEngine:
    def __init__(self, csv_path: str, initial_capital: float = 3000.0, risk_per_trade: float = 0.01):
        self.csv_path = csv_path
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.df = pd.read_csv(csv_path, index_col=0, parse_dates=True)

    def extract_alpha_factors(self) -> pd.DataFrame:
        df = self.df.copy()

        # Trend Ensembles
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        # Volatility: ATR
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["ATR"] = tr.rolling(window=14).mean()
        df["ATR_mean"] = df["ATR"].rolling(window=80).mean()
        df["ATR_regime"] = df["ATR"] / (df["ATR_mean"] + 1e-9)

        # Momentum: RSI & ROC
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["RSI"] = 100 - (100 / (1 + rs))

        # Volume confirmation
        vol_mean = df["Volume"].rolling(window=30).mean()
        df["vol_ratio"] = df["Volume"] / (vol_mean + 1e-9)

        # Qlib-inspired Alpha Factors (Normalized by ATR)
        df["alpha_dist_ema20"] = (df["Close"] - df["EMA20"]) / (df["ATR"] + 1e-9)
        df["alpha_dist_ema200"] = (df["Close"] - df["EMA200"]) / (df["ATR"] + 1e-9)
        df["alpha_trend_slope"] = (df["EMA20"] - df["EMA50"]) / (df["ATR"] + 1e-9)
        df["alpha_rsi_norm"] = (df["RSI"] - 50.0) / 15.0
        df["alpha_vol_regime"] = df["ATR_regime"]
        df["alpha_vol_flow"] = np.clip(df["vol_ratio"], 0.2, 4.0)

        # European Trading Session Filter (08:00 - 17:00 UTC)
        if isinstance(df.index, pd.DatetimeIndex):
            df["is_european_session"] = ((df.index.hour >= 8) & (df.index.hour <= 17)).astype(int)
        else:
            df["is_european_session"] = 1

        # Base Technical Setup
        df["base_setup"] = (
            (df["Close"] > df["EMA200"]) &
            (df["EMA20"] > df["EMA50"]) &
            (df["RSI"] >= 44) &
            (df["RSI"] <= 66) &
            (df["ATR_regime"] >= 0.82) &
            (df["is_european_session"] == 1)
        ).astype(int)

        df.dropna(inplace=True)
        return df

    def label_historical_setups(self, df: pd.DataFrame, horizon: int = 14, rr: float = 1.6) -> pd.DataFrame:
        labels = []
        close_vals = df["Close"].values
        high_vals = df["High"].values
        low_vals = df["Low"].values
        atr_vals = df["ATR"].values
        sig_vals = df["base_setup"].values
        n = len(df)

        for i in range(n):
            if sig_vals[i] == 1 and i + horizon < n:
                entry = close_vals[i]
                atr = atr_vals[i]
                tp = entry + (rr * atr)
                sl = entry - (1.0 * atr)

                won = False
                for j in range(i + 1, min(i + 1 + horizon, n)):
                    if high_vals[j] >= tp:
                        won = True
                        break
                    if low_vals[j] <= sl:
                        won = False
                        break
                labels.append(1 if won else 0)
            else:
                labels.append(0)

        df["target"] = labels
        return df

    def run_14year_evaluation(self, test_start_year: int = 2022) -> Dict:
        df = self.extract_alpha_factors()
        df = self.label_historical_setups(df)

        feature_cols = [
            "alpha_dist_ema20", "alpha_dist_ema200", "alpha_trend_slope",
            "alpha_rsi_norm", "alpha_vol_regime", "alpha_vol_flow"
        ]

        # Chronological Split by Date:
        train_mask = df.index.year < test_start_year
        test_mask = df.index.year >= test_start_year

        train_df = df[train_mask].copy()
        test_df = df[test_mask].copy()

        train_setups = train_df[train_df["base_setup"] == 1]
        X_train = train_setups[feature_cols].values
        y_train = train_setups["target"].values

        print(f"[+] Total velas históricas: {len(df):,}")
        print(f"[+] Periodo de Entrenamiento (In-Sample): {train_df.index[0].strftime('%Y-%m')} a {train_df.index[-1].strftime('%Y-%m')} ({len(train_df):,} barras | {len(train_setups):,} señales)")
        print(f"[+] Periodo de Validación Ciega (Out-of-Sample): {test_df.index[0].strftime('%Y-%m')} a {test_df.index[-1].strftime('%Y-%m')} ({len(test_df):,} barras)")

        # Normalization
        mean_X = np.mean(X_train, axis=0)
        std_X = np.std(X_train, axis=0) + 1e-9
        X_train_norm = (X_train - mean_X) / std_X

        # Train model
        clf = PureNumPyLogisticModel(lr=0.06, epochs=1800, lambda_reg=0.03)
        clf.fit(X_train_norm, y_train)

        # Predict Out-of-Sample test set
        test_setups = test_df[test_df["base_setup"] == 1].copy()
        X_test_norm = (test_setups[feature_cols].values - mean_X) / std_X
        test_setups["ml_prob"] = clf.predict_proba(X_test_norm)

        # Simulate Base vs ML Filtered on Unseen 2022-2026 data
        base_results = self._simulate_test_period(test_df, signal_col="base_setup")
        
        # Add ML filter column to test_df
        test_df = test_df.copy()
        test_df["ml_filter"] = 0
        test_df.loc[test_setups[test_setups["ml_prob"] >= 0.52].index, "ml_filter"] = 1

        ml_results = self._simulate_test_period(test_df, signal_col="ml_filter")

        return {
            "train_range": f"{train_df.index[0].strftime('%Y-%m')} a {train_df.index[-1].strftime('%Y-%m')}",
            "test_range": f"{test_df.index[0].strftime('%Y-%m')} a {test_df.index[-1].strftime('%Y-%m')}",
            "test_bars": len(test_df),
            "base": base_results,
            "ml": ml_results,
            "weights": dict(zip(feature_cols, clf.weights))
        }

    def _simulate_test_period(self, df: pd.DataFrame, signal_col: str, rr: float = 1.6) -> Dict:
        capital = self.initial_capital
        equity_curve = [capital]
        trades = []

        in_pos = False
        entry = 0.0
        sl = 0.0
        tp = 0.0
        pos_size = 0.0
        bars_held = 0
        breakeven = False

        close_vals = df["Close"].values
        high_vals = df["High"].values
        low_vals = df["Low"].values
        atr_vals = df["ATR"].values
        sigs = df[signal_col].values
        n = len(df)

        for i in range(1, n):
            c_close = close_vals[i]
            c_high = high_vals[i]
            c_low = low_vals[i]
            c_atr = atr_vals[i]

            if not in_pos:
                if sigs[i] == 1 and c_atr > 0:
                    entry = c_close * 1.0002
                    sl_dist = 1.0 * c_atr
                    sl = entry - sl_dist
                    tp = entry + (rr * c_atr)
                    risk_amt = capital * self.risk_per_trade
                    pos_size = risk_amt / sl_dist
                    in_pos = True
                    bars_held = 0
                    breakeven = False

            else:
                bars_held += 1

                # Freqtrade Breakeven
                if not breakeven and c_high >= (entry + (0.9 * c_atr)):
                    sl = entry
                    breakeven = True

                hit_tp = c_high >= tp
                hit_sl = c_low <= sl
                time_exit = bars_held >= 14

                if hit_tp or hit_sl or time_exit:
                    if hit_tp:
                        exit_price = tp * 0.9998
                        reason = "TakeProfit"
                    elif hit_sl:
                        exit_price = sl * 0.9998
                        reason = "Breakeven" if breakeven else "StopLoss"
                    else:
                        exit_price = c_close * 0.9998
                        reason = "TimeExit"

                    pnl = (exit_price - entry) * pos_size
                    capital += pnl
                    trades.append({"pnl": pnl, "won": pnl > 0, "be": abs(pnl) < (capital * 0.001), "reason": reason})
                    in_pos = False

            equity_curve.append(capital)

        total_t = len(trades)
        wins = [t for t in trades if t["won"]]
        bes = [t for t in trades if t["be"]]
        losses = [t for t in trades if not t["won"] and not t["be"]]

        win_rate = (len(wins) / total_t * 100) if total_t > 0 else 0.0
        no_loss_rate = ((len(wins) + len(bes)) / total_t * 100) if total_t > 0 else 0.0

        gross_gain = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        pf = (gross_gain / gross_loss) if gross_loss > 0 else 999.0

        eq_s = pd.Series(equity_curve)
        cummax = eq_s.cummax()
        dd = (eq_s - cummax) / cummax
        max_dd = dd.min() * 100
        total_ret = ((capital / self.initial_capital) - 1) * 100

        return {
            "total_trades": total_t,
            "wins": len(wins),
            "breakevens": len(bes),
            "losses": len(losses),
            "win_rate": win_rate,
            "no_loss_rate": no_loss_rate,
            "profit_factor": pf,
            "max_drawdown": max_dd,
            "total_return_pct": total_ret,
            "final_capital": capital
        }


def main():
    csv_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "DE40_H1_14years.csv")
    engine = FourteenYearAlphaEngine(csv_file, initial_capital=3000.0, risk_per_trade=0.01)
    
    print("=" * 80)
    print("AUDITORÍA CUANTITATIVA A 14 AÑOS (ENTRENADO EN 2012-2021 | PROBADO EN 2022-2026)")
    print("=" * 80)

    res = engine.run_14year_evaluation(test_start_year=2022)

    base = res["base"]
    ml = res["ml"]

    table_data = [
        {
            "Estrategia": "Base (Sin Filtro ML)",
            "Trades (4.8 años)": base["total_trades"],
            "Ganadoras": base["wins"],
            "Breakeven (0 Riesgo)": base["breakevens"],
            "Perdedoras": base["losses"],
            "Win Rate": f"{base['win_rate']:.1f}%",
            "Tasa Sin Pérdida": f"{base['no_loss_rate']:.1f}%",
            "Profit Factor": f"{base['profit_factor']:.2f}",
            "Max Drawdown": f"{base['max_drawdown']:.2f}%",
            "Capital Final": f"${base['final_capital']:.2f}",
            "Retorno Neto": f"{base['total_return_pct']:.2f}%"
        },
        {
            "Estrategia": "Algoritmo con Machine Learning",
            "Trades (4.8 años)": ml["total_trades"],
            "Ganadoras": ml["wins"],
            "Breakeven (0 Riesgo)": ml["breakevens"],
            "Perdedoras": ml["losses"],
            "Win Rate": f"{ml['win_rate']:.1f}%",
            "Tasa Sin Pérdida": f"{ml['no_loss_rate']:.1f}%",
            "Profit Factor": f"{ml['profit_factor']:.2f}",
            "Max Drawdown": f"{ml['max_drawdown']:.2f}%",
            "Capital Final": f"${ml['final_capital']:.2f}",
            "Retorno Neto": f"{ml['total_return_pct']:.2f}%"
        }
    ]

    out_df = pd.DataFrame(table_data)
    print("\n" + out_df.to_string(index=False))

    print("\n[+] Ponderación de Factores Alfa aprendidos por el modelo de ML:")
    for factor, weight in sorted(res["weights"].items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"    -> {factor:<22}: {weight:+.4f}")


if __name__ == "__main__":
    main()
