"""Script de verificación y diagnóstico de conexión de bróker en MetaTrader 5.

Audita automáticamente:
1. Conexión con MT5 y estado de la cuenta (Login, Servidor, Balance, Equity, Apalancamiento).
2. Detección automática del bróker activo (IC Markets vs Admirals).
3. Verificación de cotizaciones en tiempo real y spread de los 4 activos de la cartera:
   - DAX 40 (DE40 / GERMANY40)
   - S&P 500 (US500 / [SP500])
   - EUR/USD (EURUSD)
   - IBEX 35 (ES35 / SPA35 / [IBEX35])
4. Dimensionamiento exacto de lote con riesgo del 1.0% (20 EUR en cuenta de 2.000 EUR).
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

# Asegurar path de importación
WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("[ERROR] El paquete MetaTrader5 no está instalado en este entorno de Python.")
    sys.exit(1)

from trading_v2.backtesting.contract_specs import (
    calculate_lot_size,
    get_contract_spec,
    resolve_broker_symbol,
)


def main():
    print("=" * 70)
    print(" AUDITORÍA Y VERIFICACIÓN DE CONEXIÓN DE BRÓKER - MT5")
    print("=" * 70)

    if not mt5.initialize():
        err = mt5.last_error()
        print(f"[ERROR CRÍTICO] No se pudo conectar con MetaTrader 5. Código: {err}")
        print("Verifica que el terminal de MetaTrader 5 esté abierto en Windows.")
        sys.exit(1)

    acc = mt5.account_info()
    if acc is None:
        print("[ERROR CRÍTICO] account_info() devolvió None.")
        mt5.shutdown()
        sys.exit(1)

    # 1. Diagnóstico de la cuenta
    server_lower = acc.server.lower()
    company_lower = acc.company.lower()
    if "icmarket" in server_lower or "icmarket" in company_lower:
        broker_key = "icmarkets"
        broker_title = "IC Markets Global (Raw Spread)"
    elif "admiral" in server_lower or "admiral" in company_lower:
        broker_key = "admirals"
        broker_title = "Admirals Group"
    else:
        broker_key = "admirals"
        broker_title = f"Desconocido / Genérico ({acc.company})"

    is_demo = (acc.trade_mode == 0)
    mode_text = "DEMO (Seguro para pruebas)" if is_demo else "REAL / CONCURSO"

    print(f"Bróker detectado     : {broker_title}")
    print(f"Cuenta / Login       : #{acc.login}")
    print(f"Servidor             : {acc.server}")
    print(f"Tipo de cuenta       : {mode_text} (trade_mode={acc.trade_mode})")
    print(f"Balance              : {acc.balance:,.2f} {acc.currency}")
    print(f"Equidad (Equity)     : {acc.equity:,.2f} {acc.currency}")
    print(f"Apalancamiento       : 1:{acc.leverage}")
    print("-" * 70)

    # 2. Cartera de 4 activos canónicos
    canonical_symbols = ["GERMANY40", "[SP500]", "EURUSD", "[IBEX35]"]
    print(f"{'Activo Canónico':<16} | {'Símbolo MT5':<12} | {'Bid / Ask':<20} | {'Spread':<10} | {'Lote 1% (20€)'}")
    print("-" * 70)

    eurusd_tick = mt5.symbol_info_tick("EURUSD")
    eurusd_rate = float(eurusd_tick.bid) if eurusd_tick and eurusd_tick.bid > 0 else 1.0850

    all_symbols_ok = True

    for canon in canonical_symbols:
        mt5_sym = resolve_broker_symbol(canon, broker=broker_key)
        # Habilitar en Observación de Mercado si no está visible
        mt5.symbol_select(mt5_sym, True)
        
        info = mt5.symbol_info(mt5_sym)
        if info is None:
            # Fallback para IBEX en IC Markets: probar SPA35 si ES35 no existe
            if canon == "[IBEX35]" and broker_key == "icmarkets":
                mt5_sym = "SPA35"
                mt5.symbol_select(mt5_sym, True)
                info = mt5.symbol_info(mt5_sym)

        if info is None:
            print(f"{canon:<16} | {mt5_sym:<12} | NO ENCONTRADO EN MT5 - Habilitar en Market Watch")
            all_symbols_ok = False
            continue

        tick = mt5.symbol_info_tick(mt5_sym)
        bid = tick.bid if tick else 0.0
        ask = tick.ask if tick else 0.0
        spread_pts = round((ask - bid) / info.point) if tick and info.point > 0 else 0

        # Dimensionar lote con 1% de riesgo (o 20 EUR en caso de saldo distinto)
        try:
            spec = get_contract_spec(mt5_sym, broker=broker_key)
            # Suponemos un stop loss estándar de 2.0 ATR o distancia típica
            test_stop_pts = 40.0 if "40" in mt5_sym or "GER" in mt5_sym or "DE40" in mt5_sym else (
                15.0 if "500" in mt5_sym or "SP" in mt5_sym else (
                    0.0030 if "EUR" in mt5_sym else 30.0
                )
            )
            entry_p = ask if ask > 0 else (19000.0 if "40" in mt5_sym else 5800.0)
            lot_res = calculate_lot_size(
                spec=spec,
                account_equity=acc.equity if acc.equity > 0 else 2000.0,
                risk_fraction=0.01,
                stop_distance_price=test_stop_pts,
                entry_price=entry_p,
                eurusd_rate=eurusd_rate,
                leverage=float(acc.leverage),
            )
            lote_str = f"{lot_res.lots:.2f} lotes ({lot_res.actual_risk_account_ccy:.2f} {acc.currency})"
        except Exception as e:
            lote_str = f"Error spec: {e}"

        bid_ask_str = f"{bid:.{info.digits}f} / {ask:.{info.digits}f}" if bid > 0 else "Mercado Cerrado"
        print(f"{canon:<16} | {mt5_sym:<12} | {bid_ask_str:<20} | {spread_pts:<5} pts | {lote_str}")

    print("-" * 70)
    mt5.shutdown()

    if all_symbols_ok:
        print("[ESTADO]: EXCELENTE. Todos los activos están mapeados y operativos.")
        print(f"Para ejecutar el bot con esta cuenta, usa:")
        if broker_key == "icmarkets":
            print("  python -m trading_v2.execution.demo_paper_trader --live --broker icmarkets --symbols DE40 US500 EURUSD ES35 --risk-fraction 0.01")
        else:
            print("  python -m trading_v2.execution.demo_paper_trader --live --broker admirals --symbols GERMANY40 [SP500] EURUSD [IBEX35] --risk-fraction 0.01")
    else:
        print("[ATENCIÓN]: Algunos símbolos no están visibles en Market Watch de MT5.")
        print("Presiona Ctrl+U en MT5 para buscarlos y habilitarlos.")
    print("=" * 70)


if __name__ == "__main__":
    main()
