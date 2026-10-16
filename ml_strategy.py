"""
Quantitative Machine Learning & Multi-Factor Algorithm (Pure NumPy & Pandas)
100% Native - No external DLL dependencies (bypasses Windows AppControl restrictions)

Architecture:
1. Multi-factor Feature Extraction (Momentum Z-Score, Volatility Regime, Trend Alignment)
2. Vectorized Logistic Regression with L2 Regularization (trained via Gradient Descent in pure NumPy)
3. Chronological Walk-Forward Split (70% Train In-Sample, 30% Test Out-of-Sample)
4. Dynamic ATR Position Sizing & 1% Capital Risk Management
"""

import os
from typing import Dict, Tuple
import numpy as np
import pandas as pd


class PureNumPyLogisticRegression:
    """Vectorized Logistic Regression with L2 Ridge Regularization in pure NumPy."""
    def __init__(self, lr: float = 0.05, epochs: int = 1000, lambda_reg: float = 0.01):
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
            # Forward pass: sigmoid(X @ w + b)
            linear_model = np.dot(X, self.weights) + self.bias
            # Numerical stability clip
            linear_model = np.clip(linear_model, -25.0, 25.0)
            y_predicted = 1.0 / (1.0 + np.exp(-linear_model))

            # Gradients with L2 regularization
            error = y_predicted - y
            dw = (1.0 / n_samples) * np.dot(X.T, error) + (self.lambda_reg / n_samples) * self.weights
            db = (1.0 / n_samples) * np.sum(error)

            # Update weights
            self.weights -= self.lr * dw
            self.bias -= self.lr * db

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        linear_model = np.dot(X, self.weights) + self.bias
        linear_model = np.clip(linear_model, -25.0, 25.0)
        return 1.0 / (1.0 + np.exp(-linear_model))


class QuantitativeModel:
    def __init__(
        self,
        csv_file: str,
        initial_capital: float = 1000.0,
        risk_per_trade: float = 0.01,
        ml_confidence_threshold: float = 0.52
    ):
        self.csv_file = csv_file
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.threshold = ml_confidence_threshold
        self.df = pd.read_csv(csv_file, index_col=0, parse_dates=True)

    def extract_features(self) -> pd.DataFrame:
        df = self.df.copy()

        # 1. Moving Averages
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        # 2. ATR & Volatility
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["ATR"] = tr.rolling(window=14).mean()
        df["ATR_mean"] = df["ATR"].rolling(window=50).mean()
        df["ATR_ratio"] = df["ATR"] / (df["ATR_mean"] + 1e-9)

        # 3. Momentum (RSI)
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["RSI"] = 100 - (100 / (1 + rs))

        # Normalized features (Z-Score scaling)
        df["dist_EMA20"] = (df["Close"] - df["EMA20"]) / (df["ATR"] + 1e-9)
        df["dist_EMA200"] = (df["Close"] - df["EMA200"]) / (df["ATR"] + 1e-9)
        df["trend_strength"] = (df["EMA20"] - df["EMA50"]) / (df["ATR"] + 1e-9)
        df["RSI_norm"] = (df["RSI"] - 50.0) / 15.0

        # Base technical setup: Trend alignment + RSI pullback
        df["base_signal"] = (
            (df["Close"] > df["EMA200"]) &
            (df["EMA20"] > df["EMA50"]) &
            (df["RSI"] >= 42) &
            (df["RSI"] <= 68) &
            (df["ATR_ratio"] > 0.8) # Avoid dead sessions
        ).astype(int)

        df.dropna(inplace=True)
        return df

    def label_trades(self, df: pd.DataFrame, horizon: int = 12, risk_reward: float = 1.5) -> pd.DataFrame:
        """Meta-Labeling: 1 if trade hits Take Profit (+1.5 * ATR) before Stop Loss (-1.0 * ATR)"""
        labels = []
        close_vals = df["Close"].values
        high_vals = df["High"].values
        low_vals = df["Low"].values
        atr_vals = df["ATR"].values
        sig_vals = df["base_signal"].values
        n = len(df)

        for i in range(n):
            if sig_vals[i] == 1 and i + horizon < n:
                entry = close_vals[i]
                atr = atr_vals[i]
                tp = entry + (risk_reward * atr)
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

    def run_training_and_validation(self, split_ratio: float = 0.70) -> Dict:
        df = self.extract_features()
        df = self.label_trades(df)

        feature_cols = ["dist_EMA20", "dist_EMA200", "trend_strength", "RSI_norm", "ATR_ratio"]

        split_idx = int(len(df) * split_ratio)
        train_df = df.iloc[:split_idx].copy()
        test_df = df.iloc[split_idx:].copy()

        # Training data
        train_setups = train_df[train_df["base_signal"] == 1]
        X_train = train_setups[feature_cols].values
        y_train = train_setups["target"].values

        # Testing data (Out-of-Sample)
        test_setups = test_df[test_df["base_signal"] == 1]
        X_test = test_setups[feature_cols].values
        y_test = test_setups["target"].values

        if len(X_train) < 20 or len(X_test) < 5:
            return {"error": "Muestra insuficiente"}

        # Normalize features with Train statistics
        mean_X = np.mean(X_train, axis=0)
        std_X = np.std(X_train, axis=0) + 1e-9
        X_train_norm = (X_train - mean_X) / std_X
        X_test_norm = (X_test - mean_X) / std_X

        # Fit pure NumPy Logistic Classifier
        clf = PureNumPyLogisticRegression(lr=0.08, epochs=1200, lambda_reg=0.02)
        clf.fit(X_train_norm, y_train)

        # Predict Out-of-Sample
        probs_test = clf.predict_proba(X_test_norm)

        # Base strategy results
        base_wins = np.sum(y_test == 1)
        base_trades = len(y_test)
        base_win_rate = (base_wins / base_trades * 100) if base_trades > 0 else 0.0
        base_sim = self._simulate_performance(y_test, risk_reward=1.5)

        # ML Filtered strategy results
        ml_mask = probs_test >= self.threshold
        ml_targets = y_test[ml_mask]
        ml_trades = len(ml_targets)
        ml_wins = np.sum(ml_targets == 1)
        ml_win_rate = (ml_wins / ml_trades * 100) if ml_trades > 0 else 0.0
        ml_sim = self._simulate_performance(ml_targets, risk_reward=1.5)

        return {
            "total_bars_oos": len(test_df),
            "base_trades": base_trades,
            "base_win_rate": base_win_rate,
            "base_pf": base_sim["profit_factor"],
            "base_return": base_sim["return_pct"],
            "base_dd": base_sim["max_dd"],
            "ml_trades": ml_trades,
            "ml_win_rate": ml_win_rate,
            "ml_pf": ml_sim["profit_factor"],
            "ml_return": ml_sim["return_pct"],
            "ml_dd": ml_sim["max_dd"],
        }

    def _simulate_performance(self, outcomes: np.ndarray, risk_reward: float = 1.5) -> Dict:
        capital = self.initial_capital
        eq = [capital]
        wins = 0
        losses = 0

        for won in outcomes:
            risk = capital * self.risk_per_trade
            if won == 1:
                capital += risk * risk_reward
                wins += 1
            else:
                capital -= risk
                losses += 1
            eq.append(capital)

        eq_s = pd.Series(eq)
        cummax = eq_s.cummax()
        dd = (eq_s - cummax) / cummax
        max_dd = dd.min() * 100
        ret_pct = ((capital / self.initial_capital) - 1) * 100

        gross_profit = wins * (self.initial_capital * self.risk_per_trade * risk_reward)
        gross_loss = losses * (self.initial_capital * self.risk_per_trade)
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        return {"return_pct": ret_pct, "max_dd": max_dd, "profit_factor": pf}


def run_experiment():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    assets = {
        "DAX 40 (Horario 1h)": os.path.join(data_dir, "DAX40_1h.csv"),
        "S&P 500 (Horario 1h)": os.path.join(data_dir, "SP500_1h.csv"),
        "Dow Jones (Horario 1h)": os.path.join(data_dir, "DOW_JONES_1h.csv"),
        "EUR/USD (Horario 1h)": os.path.join(data_dir, "EURUSD_1h.csv"),
    }

    print("=" * 105)
    print("ALGORITMO HÍBRIDO CUANTITATIVO + MACHINE LEARNING (META-LABELING)")
    print("Entrenado en 70% In-Sample | Evaluado rigurosamente en 30% Out-of-Sample (Ciego)")
    print("Gestión de Riesgo: 1% fijo por operación | Ratio Riesgo/Beneficio: 1 a 1.5")
    print("=" * 105)

    results = []

    for name, path in assets.items():
        if not os.path.exists(path):
            continue
        model = QuantitativeModel(path, initial_capital=1000.0, risk_per_trade=0.01, ml_confidence_threshold=0.52)
        res = model.run_training_and_validation(split_ratio=0.70)

        if "error" in res:
            continue

        results.append({
            "Activo": name,
            "Trades Base": res["base_trades"],
            "Win Rate Base": f"{res['base_win_rate']:.1f}%",
            "PF Base": f"{res['base_pf']:.2f}",
            "Retorno Base": f"{res['base_return']:.2f}%",
            "Trades ML": res["ml_trades"],
            "Win Rate ML": f"{res['ml_win_rate']:.1f}%",
            "PF ML": f"{res['ml_pf']:.2f}",
            "Retorno ML": f"{res['ml_return']:.2f}%",
            "Max DD ML": f"{res['ml_dd']:.2f}%"
        })

    summary_df = pd.DataFrame(results)
    print("\n" + summary_df.to_string(index=False))
    return summary_df


if __name__ == "__main__":
    run_experiment()
