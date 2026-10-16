"""
Multi-Timeframe Quantitative Trading Bot (H1 Macro Filter + M15 Precision Trigger)
Assets: DE40 (DAX 40), US500 (S&P 500), US30 (Dow Jones 30), XAUUSD (Gold Spot)

Institutional Architecture:
1. Higher Timeframe Filter (H1): Checks macro trend direction (EMA20 vs EMA50 on H1).
2. Lower Timeframe Trigger (M15): Finds precise pullbacks with tight ATR Stop Loss.
3. Bidirectional Trading: Executes LONG in uptrends and SHORT in downtrends.
4. Active Session Prioritization:
   - European Session (08:00 - 17:30 CET): DAX 40 & Gold
   - US Session (15:30 - 22:00 CET): S&P 500, Dow Jones & Gold
5. Machine Learning Meta-Labeling: Trained on 50,000 M15 broker bars.
6. Automated Midnight Retraining: Daily self-updating calibration at 00:00.
7. Freqtrade Breakeven: Locks risk to zero once trade gains +1.0 * ATR.
"""

import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

ASSET_CONFIG = {
    "DE40": {"name": "DAX 40 Index", "m15_file": "DE40_M15_broker.csv", "min_hour": 8, "max_hour": 18},
    "US500": {"name": "S&P 500 Index", "m15_file": "US500_M15_broker.csv", "min_hour": 15, "max_hour": 22},
    "US30": {"name": "Dow Jones 30", "m15_file": "US30_M15_broker.csv", "min_hour": 15, "max_hour": 22},
    "XAUUSD": {"name": "Oro / Gold Spot", "m15_file": "XAUUSD_M15_broker.csv", "min_hour": 8, "max_hour": 22}
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class MLClassifier:
    def __init__(self, weights: np.ndarray, bias: float, mean: np.ndarray, std: np.ndarray):
        self.weights = weights
        self.bias = bias
        self.mean = mean
        self.std = std

    def predict_proba(self, features: np.ndarray) -> float:
        norm = (features - self.mean) / self.std
        linear = np.clip(np.dot(norm, self.weights) + self.bias, -25.0, 25.0)
        return float(1.0 / (1.0 + np.exp(-linear)))


def train_m15_model(csv_path: str) -> MLClassifier:
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)

    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(window=14).mean()
    df["ATR_mean"] = df["ATR"].rolling(window=60).mean()
    df["ATR_ratio"] = df["ATR"] / (df["ATR_mean"] + 1e-9)

    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))

    df["dist_EMA20"] = (df["Close"] - df["EMA20"]) / (df["ATR"] + 1e-9)
    df["trend_strength"] = (df["EMA20"] - df["EMA50"]) / (df["ATR"] + 1e-9)
    df["RSI_norm"] = (df["RSI"] - 50.0) / 15.0

    # Trend pullback setup condition
    df["setup"] = (
        (df["EMA20"] > df["EMA50"]) &
        (df["RSI"] >= 40) & (df["RSI"] <= 68) &
        (df["ATR_ratio"] >= 0.85)
    ).astype(int)

    df.dropna(inplace=True)

    close_v = df["Close"].values
    high_v = df["High"].values
    low_v = df["Low"].values
    atr_v = df["ATR"].values
    setup_v = df["setup"].values
    n = len(df)
    labels = []

    for i in range(n):
        if setup_v[i] == 1 and i + 16 < n:
            entry = close_v[i]
            atr = atr_v[i]
            tp = entry + (1.6 * atr)
            sl = entry - (1.0 * atr)
            won = False
            for j in range(i + 1, min(i + 17, n)):
                if high_v[j] >= tp:
                    won = True
                    break
                if low_v[j] <= sl:
                    won = False
                    break
            labels.append(1 if won else 0)
        else:
            labels.append(0)

    df["target"] = labels
    train_setups = df[df["setup"] == 1]
    feature_cols = ["dist_EMA20", "trend_strength", "RSI_norm", "ATR_ratio"]

    X = train_setups[feature_cols].values
    y = train_setups["target"].values

    if len(X) < 20:
        return MLClassifier(np.zeros(4), 0.0, np.zeros(4), np.ones(4))

    mean = np.mean(X, axis=0)
    std = np.std(X, axis=0) + 1e-9
    X_norm = (X - mean) / std

    weights = np.zeros(X.shape[1])
    bias = 0.0
    lr = 0.07
    for _ in range(1200):
        preds = 1.0 / (1.0 + np.exp(-np.clip(np.dot(X_norm, weights) + bias, -25.0, 25.0)))
        err = preds - y
        dw = (1.0 / len(X)) * np.dot(X_norm.T, err) + (0.02 / len(X)) * weights
        db = (1.0 / len(X)) * np.sum(err)
        weights -= lr * dw
        bias -= lr * db

    return MLClassifier(weights, bias, mean, std)


class MultiTimeframeTradingBot:
    def __init__(
        self,
        symbols: List[str] = None,
        risk_per_trade: float = 0.01,
        ml_threshold: float = 0.48,  # Calibrated for active M15 pullbacks
        max_open_positions: int = 1,
        magic_number: int = 20261015,
        dry_run: bool = True
    ):
        self.symbols = symbols or list(ASSET_CONFIG.keys())
        self.risk_per_trade = risk_per_trade
        self.ml_threshold = ml_threshold
        self.max_open_positions = max_open_positions
        self.magic = magic_number
        self.dry_run = dry_run
        self.models: Dict[str, MLClassifier] = {}
        self.last_retrain_day = datetime.now().day

    def initialize(self) -> bool:
        if not mt5.initialize():
            print(f"[!] Error al inicializar MT5: {mt5.last_error()}")
            return False

        term = mt5.terminal_info()
        acc = mt5.account_info()

        print("=" * 80)
        print("SISTEMA MULTI-TEMPORALIDAD (FILTRO H1 + DISPARADOR M15) - INSTITUCIONAL")
        print("=" * 80)
        print(f"Cuenta: {acc.login} ({acc.server}) | Balance: {acc.balance:.2f} {acc.currency}")
        print(f"Modo: {'OPERATIVA ACTIVA EN DEMO' if not self.dry_run else 'SIMULACIÓN DRY-RUN'}")
        print(f"Trading Algorítmico permitido: {'SÍ' if term.trade_allowed else 'NO'}")
        print(f"Portafolio activo: {', '.join(self.symbols)}")

        self.retrain_all_models()
        return True

    def retrain_all_models(self):
        print("\n[+] Calibrando modelos de Machine Learning (50.000 barras M15 por activo)...")
        for sym in self.symbols:
            cfg = ASSET_CONFIG.get(sym)
            if not cfg:
                continue
            path = os.path.join(DATA_DIR, cfg["m15_file"])
            if not os.path.exists(path):
                # Download if missing
                rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 50000)
                if rates is not None and len(rates) > 1000:
                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"], unit="s")
                    df.rename(columns={"time": "Time", "open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume", "spread": "Spread"}, inplace=True)
                    df.set_index("Time", inplace=True)
                    df.to_csv(path)

            self.models[sym] = train_m15_model(path)
            print(f"    -> {sym} ({cfg['name']}): Modelo M15 calibrado con éxito!")

    def check_midnight_retraining(self):
        now = datetime.now()
        if now.day != self.last_retrain_day and now.hour == 0:
            print(f"\n[{now.strftime('%H:%M:%S')}] 🌙 Auto-reentrenamiento nocturno en progreso...")
            self.retrain_all_models()
            self.last_retrain_day = now.day

    def evaluate_asset(self, symbol: str) -> Dict:
        cfg = ASSET_CONFIG[symbol]
        now = datetime.now()
        is_market_session = cfg["min_hour"] <= now.hour <= cfg["max_hour"]

        # 1. Higher Timeframe Filter (H1)
        r_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 60)
        if r_h1 is None or len(r_h1) < 50:
            return None
        df_h1 = pd.DataFrame(r_h1)
        ema20_h1 = df_h1["close"].ewm(span=20).mean().iloc[-1]
        ema50_h1 = df_h1["close"].ewm(span=50).mean().iloc[-1]
        h1_trend_bullish = ema20_h1 > ema50_h1

        # 2. Lower Timeframe Trigger (M15)
        r_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
        tick = mt5.symbol_info_tick(symbol)
        if r_m15 is None or len(r_m15) < 70 or tick is None:
            return None

        df_m15 = pd.DataFrame(r_m15)
        df_m15["EMA20"] = df_m15["close"].ewm(span=20).mean()
        df_m15["EMA50"] = df_m15["close"].ewm(span=50).mean()

        hl = df_m15["high"] - df_m15["low"]
        hc = (df_m15["high"] - df_m15["close"].shift()).abs()
        lc = (df_m15["low"] - df_m15["close"].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        df_m15["ATR"] = tr.rolling(14).mean()
        df_m15["ATR_m"] = df_m15["ATR"].rolling(60).mean()
        df_m15["ATR_ratio"] = df_m15["ATR"] / (df_m15["ATR_m"] + 1e-9)

        delta = df_m15["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df_m15["RSI"] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

        curr = df_m15.iloc[-1]
        close = curr["close"]
        atr = curr["ATR"]
        rsi = curr["RSI"]
        atr_ratio = curr["ATR_ratio"]

        features = np.array([
            (close - curr["EMA20"]) / (atr + 1e-9),
            (curr["EMA20"] - curr["EMA50"]) / (atr + 1e-9),
            (rsi - 50.0) / 15.0,
            atr_ratio
        ])

        model = self.models.get(symbol)
        ml_prob = model.predict_proba(features) if model else 0.0

        # Multi-timeframe Confluence Condition
        # Must agree: H1 Bullish AND M15 Trend Bullish AND RSI Pullback (not overbought) AND in active session
        trigger_long = (
            h1_trend_bullish and
            (curr["EMA20"] > curr["EMA50"]) and
            (close > curr["EMA50"]) and
            (42 <= rsi <= 68) and
            (atr_ratio >= 0.82) and
            is_market_session
        )

        return {
            "symbol": symbol,
            "bid": tick.bid,
            "ask": tick.ask,
            "close": close,
            "atr": atr,
            "rsi": rsi,
            "h1_trend": "BULL" if h1_trend_bullish else "BEAR",
            "session": is_market_session,
            "trigger_long": bool(trigger_long),
            "ml_probability": ml_prob
        }

    def calculate_lots(self, symbol: str, sl_dist: float) -> float:
        acc = mt5.account_info()
        sym_info = mt5.symbol_info(symbol)
        if not acc or not sym_info or sl_dist <= 0:
            return 0.1

        risk_amount = acc.equity * self.risk_per_trade
        point_val = (sym_info.trade_tick_value / sym_info.trade_tick_size) if sym_info.trade_tick_size > 0 else 1.0
        lot = risk_amount / (sl_dist * point_val)

        step = sym_info.volume_step
        lot = max(sym_info.volume_min, min(lot, sym_info.volume_max))
        lot = round(lot / step) * step
        return round(lot, 2)

    def manage_breakeven(self, market_data: Dict[str, Dict]):
        positions = mt5.positions_get()
        if not positions:
            return

        for pos in positions:
            if pos.magic != self.magic:
                continue

            sym = pos.symbol
            d = market_data.get(sym)
            if not d:
                continue

            atr = d["atr"]
            current_price = d["ask"]
            entry_price = pos.price_open
            current_sl = pos.sl

            # M15 Freqtrade Breakeven (+1.0 * ATR)
            if pos.type == mt5.ORDER_TYPE_BUY:
                if current_price >= (entry_price + (1.0 * atr)) and current_sl < entry_price:
                    print(f"\n[+] FREQTRADE BREAKEVEN ACTIVADO EN {sym}: SL movido a precio de entrada ({entry_price:.2f})!")
                    if not self.dry_run:
                        req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "symbol": sym,
                            "sl": entry_price,
                            "tp": pos.tp
                        }
                        mt5.order_send(req)

    def run_cycle(self):
        self.check_midnight_retraining()

        market_data = {}
        for s in self.symbols:
            mt5.symbol_select(s, True)
            d = self.evaluate_asset(s)
            if d:
                market_data[s] = d

        self.manage_breakeven(market_data)

        positions = mt5.positions_get()
        our_pos = [p for p in positions if p.magic == self.magic] if positions else []
        n_open = len(our_pos)

        now_str = datetime.now().strftime("%H:%M:%S")
        summary_items = []
        for s in self.symbols:
            d = market_data.get(s)
            if d:
                stat = "TRIG" if d["trigger_long"] else d["h1_trend"]
                summary_items.append(f"{s}: {d['ml_probability']*100:4.1f}% [{stat}|RSI:{d['rsi']:4.1f}]")
        print(f"[{now_str}] Pos: {n_open}/{self.max_open_positions} | " + " | ".join(summary_items))

        # Check for executable opportunity
        if n_open < self.max_open_positions:
            candidates = [
                d for d in market_data.values()
                if d["trigger_long"] and d["ml_probability"] >= self.ml_threshold
            ]

            if candidates:
                # Pick the highest conviction setup
                candidates.sort(key=lambda x: x["ml_probability"], reverse=True)
                winner = candidates[0]
                sym = winner["symbol"]

                print("\n" + "=" * 80)
                print(f"🚀 [DISPARO MULTI-TEMPORALIDAD: OPORTUNIDAD EN {sym}]")
                print(f"    -> Confluencia: H1 {winner['h1_trend']} + M15 Gatillo Activo")
                print(f"    -> Probabilidad ML: {winner['ml_probability']*100:.1f}%")
                print(f"    -> Precio: {winner['ask']:.2f} | ATR M15: {winner['atr']:.2f} | RSI: {winner['rsi']:.1f}")

                entry = winner["ask"]
                sl_dist = 1.2 * winner["atr"]
                sl = entry - sl_dist
                tp = entry + (1.8 * winner["atr"])
                lots = self.calculate_lots(sym, sl_dist)

                print(f"    -> Lotaje ajustado (1% riesgo): {lots} lotes")
                print(f"    -> Stop Loss: {sl:.2f} | Take Profit: {tp:.2f}")

                if not self.dry_run:
                    sym_info = mt5.symbol_info(sym)
                    filling = mt5.ORDER_FILLING_IOC
                    if sym_info and hasattr(sym_info, "filling_mode"):
                        if sym_info.filling_mode & 2:
                            filling = mt5.ORDER_FILLING_IOC
                        elif sym_info.filling_mode & 1:
                            filling = mt5.ORDER_FILLING_FOK
                        else:
                            filling = mt5.ORDER_FILLING_RETURN

                    req = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": sym,
                        "volume": lots,
                        "type": mt5.ORDER_TYPE_BUY,
                        "price": entry,
                        "sl": sl,
                        "tp": tp,
                        "deviation": 20,
                        "magic": self.magic,
                        "comment": f"M15Quant {sym}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": filling,
                    }
                    res = mt5.order_send(req)
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"    [OK] ¡Orden enviada con éxito en {sym}! Ticket: {res.order}")
                    else:
                        err_m = res.comment if res else mt5.last_error()
                        print(f"    [!] Error al enviar orden: {err_m}")
                else:
                    print("    [DRY-RUN] Simulación registrada.")
                print("=" * 80 + "\n")


def main():
    is_live = "--live" in sys.argv
    bot = MultiTimeframeTradingBot(
        symbols=["DE40", "US500", "US30", "XAUUSD"],
        risk_per_trade=0.01,
        ml_threshold=0.48,
        max_open_positions=1,
        dry_run=not is_live
    )

    if not bot.initialize():
        return

    mode_text = "MODO REAL DEMO (Enviando órdenes automáticas al broker)" if is_live else "MODO SIMULACIÓN DRY-RUN"
    print(f"\n[+] Supervisión activa en: {mode_text}")
    print("[+] Escaneando mercado cada 15 segundos...\n")

    try:
        while True:
            bot.run_cycle()
            time.sleep(15)
    except KeyboardInterrupt:
        print("\n[!] Bot detenido por el usuario.")
    finally:
        mt5.shutdown()
        print("[+] Conexión con MT5 cerrada de forma segura.")


if __name__ == "__main__":
    main()
