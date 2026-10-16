"""
Master Quantitative Trading Algorithm
The complete fusion of:
1. Multi-factor Feature Extraction
2. Machine Learning Meta-Labeling Classifier (Pure NumPy Vectorized Logistic Model)
3. Freqtrade Dynamic Breakeven Protection (Locks 0-risk at +1.0*ATR)
4. vn.py Time-based Momentum Exhaustion Exit
5. Freqtrade Streak Cooldown (Protects against whipsaw regimes)
"""

import os
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


class PureNumPyLogisticRegression:
    def __init__(self, lr: float = 0.08, epochs: int = 1200, lambda_reg: float = 0.02):
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
            y_pred = 1.0 / (1.0 + np.exp(-linear))
            err = y_pred - y
            dw = (1.0 / n_samples) * np.dot(X.T, err) + (self.lambda_reg / n_samples) * self.weights
            db = (1.0 / n_samples) * np.sum(err)
            self.weights -= self.lr * dw
            self.bias -= self.lr * db

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        linear = np.clip(np.dot(X, self.weights) + self.bias, -25.0, 25.0)
        return 1.0 / (1.0 + np.exp(-linear))


class MasterQuantBot:
    def __init__(
        self,
        csv_file: str,
        initial_capital: float = 1000.0,
        risk_per_trade: float = 0.01,
        ml_confidence_threshold: float = 0.54,
        max_bars_in_trade: int = 14,
        cooldown_bars: int = 6,
        slippage_pct: float = 0.0002
    ):
        self.csv_file = csv_file
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.threshold = ml_confidence_threshold
        self.max_bars_in_trade = max_bars_in_trade
        self.cooldown_bars = cooldown_bars
        self.slippage_pct = slippage_pct
        self.df = pd.read_csv(csv_file, index_col=0, parse_dates=True)

    def prepare_features(self) -> pd.DataFrame:
        df = self.df.copy()

        # Moving Averages
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        # ATR & Volatility Regime
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["ATR"] = tr.rolling(window=14).mean()
        df["ATR_mean50"] = df["ATR"].rolling(window=50).mean()
        df["ATR_ratio"] = df["ATR"] / (df["ATR_mean50"] + 1e-9)

        # Momentum (RSI)
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["RSI"] = 100 - (100 / (1 + rs))

        # Normalized Features
        df["dist_EMA20"] = (df["Close"] - df["EMA20"]) / (df["ATR"] + 1e-9)
        df["dist_EMA200"] = (df["Close"] - df["EMA200"]) / (df["ATR"] + 1e-9)
        df["trend_strength"] = (df["EMA20"] - df["EMA50"]) / (df["ATR"] + 1e-9)
        df["RSI_norm"] = (df["RSI"] - 50.0) / 15.0

        # Base technical setup
        df["base_setup"] = (
            (df["Close"] > df["EMA200"]) &
            (df["EMA20"] > df["EMA50"]) &
            (df["RSI"] >= 45) &
            (df["RSI"] <= 65) &
            (df["ATR_ratio"] >= 0.85)
        ).astype(int)

        df.dropna(inplace=True)
        return df

    def label_historical_setups(self, df: pd.DataFrame, horizon: int = 12, rr: float = 1.5) -> pd.DataFrame:
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

    def run_master_pipeline(self, split_ratio: float = 0.70) -> Dict:
        df = self.prepare_features()
        df = self.label_historical_setups(df)

        features = ["dist_EMA20", "dist_EMA200", "trend_strength", "RSI_norm", "ATR_ratio"]

        split_idx = int(len(df) * split_ratio)
        train_df = df.iloc[:split_idx].copy()
        test_df = df.iloc[split_idx:].copy()

        # Training set
        train_setups = train_df[train_df["base_setup"] == 1]
        X_train = train_setups[features].values
        y_train = train_setups["target"].values

        if len(X_train) < 30:
            return {"error": "Insuficientes muestras de entrenamiento"}

        mean_X = np.mean(X_train, axis=0)
        std_X = np.std(X_train, axis=0) + 1e-9
        X_train_norm = (X_train - mean_X) / std_X

        # Train ML Model
        clf = PureNumPyLogisticRegression(lr=0.08, epochs=1200, lambda_reg=0.02)
        clf.fit(X_train_norm, y_train)

        # Evaluate Out-of-Sample with Freqtrade Breakeven & vn.py Time Exits
        X_test_all = (test_df[features].values - mean_X) / std_X
        test_df = test_df.copy()
        test_df["ml_prob"] = clf.predict_proba(X_test_all)

        return self._simulate_live_execution(test_df)

    def _simulate_live_execution(self, df: pd.DataFrame) -> Dict:
        capital = self.initial_capital
        equity_curve = [capital]
        trades = []

        in_pos = False
        entry_price = 0.0
        stop_loss = 0.0
        take_profit = 0.0
        pos_size = 0.0
        bars_held = 0
        breakeven = False
        cooldown = 0
        consecutive_losses = 0

        close_vals = df["Close"].values
        high_vals = df["High"].values
        low_vals = df["Low"].values
        atr_vals = df["ATR"].values
        base_sigs = df["base_setup"].values
        ml_probs = df["ml_prob"].values
        n = len(df)

        for i in range(1, n):
            c_close = close_vals[i]
            c_high = high_vals[i]
            c_low = low_vals[i]
            c_atr = atr_vals[i]

            if cooldown > 0:
                cooldown -= 1

            if not in_pos:
                # Signal condition: Base Technical Setup AND ML Probability >= threshold AND No Cooldown
                if base_sigs[i] == 1 and ml_probs[i] >= self.threshold and cooldown == 0 and c_atr > 0:
                    entry_price = c_close * (1 + self.slippage_pct)
                    sl_dist = 1.0 * c_atr
                    stop_loss = entry_price - sl_dist
                    take_profit = entry_price + (1.6 * c_atr)

                    risk_amt = capital * self.risk_per_trade
                    pos_size = risk_amt / sl_dist
                    in_pos = True
                    bars_held = 0
                    breakeven = False

            else:
                bars_held += 1

                # Freqtrade Breakeven Lock (+0.9 * ATR)
                if not breakeven and c_high >= (entry_price + (0.9 * c_atr)):
                    stop_loss = entry_price
                    breakeven = True

                hit_tp = c_high >= take_profit
                hit_sl = c_low <= stop_loss
                time_exit = bars_held >= self.max_bars_in_trade

                if hit_tp or hit_sl or time_exit:
                    if hit_tp:
                        exit_price = take_profit * (1 - self.slippage_pct)
                        reason = "TakeProfit"
                    elif hit_sl:
                        exit_price = stop_loss * (1 - self.slippage_pct)
                        reason = "Breakeven" if breakeven else "StopLoss"
                    else:
                        exit_price = c_close * (1 - self.slippage_pct)
                        reason = "TimeExit"

                    pnl = (exit_price - entry_price) * pos_size
                    capital += pnl
                    is_win = pnl > 0
                    is_be = abs(pnl) < (capital * 0.001)

                    if is_win:
                        consecutive_losses = 0
                    elif not is_be:
                        consecutive_losses += 1
                        if consecutive_losses >= 2:
                            cooldown = self.cooldown_bars
                            consecutive_losses = 0

                    trades.append({
                        "entry": entry_price,
                        "exit": exit_price,
                        "pnl": pnl,
                        "won": is_win,
                        "breakeven": is_be,
                        "reason": reason
                    })
                    in_pos = False

            equity_curve.append(capital)

        total_t = len(trades)
        wins = [t for t in trades if t["won"]]
        bes = [t for t in trades if t["breakeven"]]
        losses = [t for t in trades if not t["won"] and not t["breakeven"]]

        win_rate = (len(wins) / total_t * 100) if total_t > 0 else 0.0
        no_loss_rate = ((len(wins) + len(bes)) / total_t * 100) if total_t > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        eq_s = pd.Series(equity_curve)
        cummax = eq_s.cummax()
        dd = (eq_s - cummax) / cummax
        max_dd = dd.min() * 100
        ret_pct = ((capital / self.initial_capital) - 1) * 100

        return {
            "trades": total_t,
            "wins": len(wins),
            "breakevens": len(bes),
            "losses": len(losses),
            "win_rate": win_rate,
            "no_loss_rate": no_loss_rate,
            "profit_factor": pf,
            "max_drawdown": max_dd,
            "return_pct": ret_pct,
            "trades_log": trades
        }


def run_master_suite():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    assets = {
        "DAX 40 (1h)": os.path.join(data_dir, "DAX40_1h.csv"),
        "S&P 500 (1h)": os.path.join(data_dir, "SP500_1h.csv"),
        "Dow Jones (1h)": os.path.join(data_dir, "DOW_JONES_1h.csv"),
        "EUR/USD (1h)": os.path.join(data_dir, "EURUSD_1h.csv"),
    }

    print("=" * 105)
    print("MASTER QUANTITATIVE BOT: FUSIÓN DE MACHINE LEARNING + PROTECCIONES INSTITUCIONALES")
    print("Evaluación en datos Out-of-Sample (30% final ciego no visto)")
    print("Riesgo: 1% fijo por operación | Breakeven dinámico Freqtrade + Time-Exit vn.py")
    print("=" * 105)

    summary = []

    for name, path in assets.items():
        if not os.path.exists(path):
            continue
        bot = MasterQuantBot(path, initial_capital=1000.0, risk_per_trade=0.01, ml_confidence_threshold=0.54)
        res = bot.run_master_pipeline(split_ratio=0.70)

        if "error" in res:
            continue

        summary.append({
            "Activo": name,
            "Trades Ciegos": res["trades"],
            "Ganadas": res["wins"],
            "Breakeven (0 Riesgo)": res["breakevens"],
            "Perdidas": res["losses"],
            "Win Rate Puro": f"{res['win_rate']:.1f}%",
            "Tasa Sin Pérdida": f"{res['no_loss_rate']:.1f}%",
            "Profit Factor": f"{res['profit_factor']:.2f}",
            "Max Drawdown": f"{res['max_drawdown']:.2f}%",
            "Retorno Total": f"{res['return_pct']:.2f}%"
        })

    summary_df = pd.DataFrame(summary)
    print("\n" + summary_df.to_string(index=False))
    return summary_df


if __name__ == "__main__":
    run_master_suite()
