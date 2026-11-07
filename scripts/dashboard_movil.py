#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Servidor de Dashboard Móvil para seguimiento en tiempo real (Solo Lectura).

Permite a Julio y Carlos monitorizar desde el teléfono móvil:
- El estado de la cuenta DEMO (Balance, Equity, Margen).
- Las posiciones abiertas, sus Stops y beneficio/pérdida en EUR en vivo.
- El "semáforo" del cerebro cuantitativo para cada índice:
  - Si compra, vende o espera, y exactamente POR QUÉ (RSI2, IBS, SMA200, ATR).
- Las comisiones y costes del bróker aplicados.

Funciona en cualquier navegador de móvil (iPhone / Android) accediendo a la IP local
o mediante un túnel seguro (Cloudflare / Ngrok).
"""
from __future__ import annotations

import argparse
import http.server
import json
import socket
import socketserver
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.scanner_diario_senales import SYMBOLS_TO_SCAN, scan_markets
from trading_v2.execution.demo_paper_trader import get_mt5_module


def get_local_ip() -> str:
    """Detecta la IP local en la red Wi-Fi para acceder desde el móvil."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_dashboard_data(mt5) -> dict:
    if mt5 is None:
        return {"connected": False, "error": "Módulo MetaTrader 5 no disponible"}

    acc = mt5.account_info()
    if acc is None:
        try:
            mt5.initialize()
            acc = mt5.account_info()
        except Exception:
            pass

    if acc is None:
        return {"connected": False, "error": "No conectado a MetaTrader 5"}

    equity = float(getattr(acc, "equity", 0.0))
    balance = float(getattr(acc, "balance", 0.0))
    login = int(getattr(acc, "login", 0))
    server = str(getattr(acc, "server", ""))

    # Posiciones abiertas
    positions_raw = mt5.positions_get() or ()
    positions = []
    for pos in positions_raw:
        positions.append({
            "ticket": int(pos.ticket),
            "symbol": str(pos.symbol),
            "type": "COMPRA" if pos.type == 0 else "VENTA",
            "volume": float(pos.volume),
            "price_open": float(pos.price_open),
            "price_current": float(pos.price_current),
            "sl": float(pos.sl),
            "profit_eur": float(pos.profit),
            "swap": float(pos.swap),
        })

    # Escaneo de señales del cerebro cuantitativo
    scan_res = scan_markets(mt5, account_equity=equity, risk_fraction=0.0075, verbose=False)

    # Historial real consolidado
    history_summary = None
    try:
        from trading_v2.execution.trade_journal import get_live_trade_records
        records = get_live_trade_records(mt5)
        if records:
            wins = sum(1 for r in records if r["net_pnl"] > 0)
            losses = sum(1 for r in records if r["net_pnl"] < 0)
            total_trades = len(records)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            net_pnl_total = sum(r["net_pnl"] for r in records)
            gross_win = sum(r["net_pnl"] for r in records if r["net_pnl"] > 0)
            gross_loss = abs(sum(r["net_pnl"] for r in records if r["net_pnl"] < 0))
            pf = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
            history_summary = {
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "net_pnl": net_pnl_total,
                "profit_factor": pf,
            }
    except Exception:
        history_summary = None

    # Cargar estado del Operador Fantasma (Modelo B - Híbrido 70/30)
    ghost_summary = None
    try:
        ghost_file = ROOT / "data" / "ghost_trader_state.json"
        if ghost_file.exists():
            with open(ghost_file, "r", encoding="utf-8") as f:
                ghost_summary = json.load(f)
    except Exception:
        ghost_summary = None

    return {
        "connected": True,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "account": {
            "login": login,
            "server": server,
            "balance": round(balance, 2),
            "equity": round(equity, 2),
            "floating_pnl": round(equity - balance, 2),
        },
        "positions": positions,
        "signals": scan_res,
        "history_summary": history_summary,
        "ghost": ghost_summary,
    }


def render_html(data: dict) -> str:
    if not data.get("connected"):
        return f"<html><body style='font-family:sans-serif;padding:20px;background:#111;color:#fff;'><h1>Error de Conexión</h1><p>{data.get('error')}</p></body></html>"

    acc = data["account"]
    pnl = acc["floating_pnl"]
    pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
    pnl_sign = "+" if pnl > 0 else ""

    # Tarjetas de posiciones reales
    pos_html = ""
    if data["positions"]:
        for p in data["positions"]:
            pos_pnl_col = "#10b981" if p["profit_eur"] >= 0 else "#ef4444"
            pos_html += f"""
            <div style="background:#1f2937;border-radius:10px;padding:14px;margin-bottom:10px;border-left:4px solid {pos_pnl_col};">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:bold;font-size:16px;">{p['symbol']} ({p['type']})</span>
                    <span style="font-size:16px;font-weight:bold;color:{pos_pnl_col};">{p['profit_eur']:+.2f} EUR</span>
                </div>
                <div style="font-size:13px;color:#9ca3af;margin-top:6px;">
                    Lotes: {p['volume']:.2f} | Entrada: {p['price_open']:.2f} | Actual: {p['price_current']:.2f}<br>
                    Stop Loss: {p['sl']:.2f} | Swap acumulado: {p['swap']:.2f} EUR | Comisión: 0.00 EUR
                </div>
            </div>
            """
    else:
        pos_html = "<div style='background:#1f2937;border-radius:10px;padding:16px;color:#9ca3af;text-align:center;'>Sin posiciones abiertas en este momento.</div>"

    # Datos A/B
    hist = data.get("history_summary") or {}
    live_trades = hist.get("total_trades", 0)
    live_wins = hist.get("wins", 0)
    live_losses = hist.get("losses", 0)
    live_wr = hist.get("win_rate", 0.0)
    live_pnl = hist.get("net_pnl", 0.0)

    ghost = data.get("ghost") or {}
    ghost_balance = ghost.get("virtual_balance", 3000.0)
    ghost_equity = ghost.get("virtual_equity", 3000.0)
    ghost_pnl = ghost.get("net_pnl_eur", 0.0)
    ghost_wr = ghost.get("win_rate", 0.0)
    ghost_trades = ghost.get("total_trades", 0)
    ghost_wins = ghost.get("wins", 0)
    ghost_losses = ghost.get("losses", 0)
    ghost_positions = ghost.get("open_positions", [])

    diff_pnl = ghost_pnl - live_pnl
    diff_pnl_col = "#10b981" if diff_pnl >= 0 else "#ef4444"
    diff_pnl_sign = "+" if diff_pnl > 0 else ""

    ab_html = f"""
    <div style="background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%); border: 1px solid #4338ca; border-radius: 12px; padding: 16px; margin-bottom: 20px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
            <span style="font-weight:bold; font-size:15px; color:#c7d2fe;">⚔️ BATALLA DE MODELOS A/B EN VIVO</span>
            <span style="font-size:11px; background:#312e81; color:#a5b4fc; padding:2px 8px; border-radius:10px; font-weight:bold;">PARALELO</span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <div style="background:#111827; border-radius:8px; padding:12px; border-top: 3px solid #3b82f6;">
                <div style="font-size:12px; font-weight:bold; color:#60a5fa;">MODELO A (LIVE DEMO)</div>
                <div style="font-size:10px; color:#9ca3af; margin-bottom:8px;">100% Scalp M15/M30</div>
                <div style="font-size:14px; font-weight:bold; color:{'#10b981' if live_pnl>=0 else '#ef4444'};">{live_pnl:+.2f} €</div>
                <div style="font-size:11px; color:#d1d5db; margin-top:4px;">WR: <b>{live_wr:.1f}%</b> ({live_wins}W/{live_losses}L)</div>
                <div style="font-size:11px; color:#9ca3af; margin-top:2px;">Trades: {live_trades} | Open: {len(data['positions'])}</div>
            </div>
            <div style="background:#111827; border-radius:8px; padding:12px; border-top: 3px solid #8b5cf6;">
                <div style="font-size:12px; font-weight:bold; color:#a78bfa;">MODELO B (FANTASMA)</div>
                <div style="font-size:10px; color:#9ca3af; margin-bottom:8px;">Híbrido 70/30 + H1 Forex</div>
                <div style="font-size:14px; font-weight:bold; color:{'#10b981' if ghost_pnl>=0 else '#ef4444'};">{ghost_pnl:+.2f} €</div>
                <div style="font-size:11px; color:#d1d5db; margin-top:4px;">WR: <b>{ghost_wr:.1f}%</b> ({ghost_wins}W/{ghost_losses}L)</div>
                <div style="font-size:11px; color:#9ca3af; margin-top:2px;">Trades: {ghost_trades} | Open: {len(ghost_positions)}</div>
            </div>
        </div>
        <div style="margin-top:12px; padding-top:10px; border-top: 1px solid #312e81; display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:12px; color:#9ca3af;">Diferencial Modelo B vs A:</span>
            <span style="font-size:13px; font-weight:bold; color:{diff_pnl_col};">{diff_pnl_sign}{diff_pnl:.2f} EUR</span>
        </div>
    </div>
    """

    # Tarjetas de posiciones del Fantasma
    ghost_pos_html = ""
    if ghost_positions:
        for gp in ghost_positions:
            g_col = "#10b981" if gp.get("current_floating_pnl_eur", 0.0) >= 0 else "#ef4444"
            dir_str = "COMPRA" if gp.get("direction", 1) == 1 else "VENTA"
            status_badge = "30% RUNNER" if gp.get("status") == "TRAILING_RUNNER" else "ACTIVO 70/30"
            ghost_pos_html += f"""
            <div style="background:#1f2937;border-radius:10px;padding:14px;margin-bottom:10px;border-left:4px solid #8b5cf6;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:bold;font-size:15px;">👻 {gp['symbol']} ({dir_str}) <small style="background:#4c1d95; color:#ddd6fe; padding:2px 6px; border-radius:4px; font-size:10px;">{status_badge}</small></span>
                    <span style="font-size:15px;font-weight:bold;color:{g_col};">{gp.get('current_floating_pnl_eur', 0.0):+.2f} EUR</span>
                </div>
                <div style="font-size:12px;color:#9ca3af;margin-top:6px;">
                    Lotes: {gp.get('lots_total', 0.0):.2f} (70%: {gp.get('lots_70', 0.0):.2f} | 30%: {gp.get('lots_30', 0.0):.2f})<br>
                    Entrada: {gp.get('entry_price', 0.0):.4f} | TP Fijo: {gp.get('fixed_tp', 0.0):.4f} | SL Trailing: {gp.get('current_sl', 0.0):.4f}
                </div>
            </div>
            """
    else:
        ghost_pos_html = "<div style='background:#1f2937;border-radius:10px;padding:12px;color:#9ca3af;text-align:center;font-size:13px;'>Sin posiciones en sombra actualmente.</div>"

    # Tarjetas de señales / cerebro
    sig_html = ""
    for s in data["signals"]:
        is_buy = s.get("signal_active", False)
        badge_bg = "#065f46" if is_buy else "#374151"
        badge_col = "#34d399" if is_buy else "#9ca3af"
        badge_text = "🟢 COMPRA ACTIVA" if is_buy else "🟡 ESPERAR"

        reasons = "<br>• ".join(s.get("reasons", []))
        sig_html += f"""
        <div style="background:#1f2937;border-radius:10px;padding:14px;margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:bold;font-size:15px;">{s['market']} <small style="color:#9ca3af;">({s['symbol']})</small></span>
                <span style="background:{badge_bg};color:{badge_col};padding:3px 8px;border-radius:6px;font-size:12px;font-weight:bold;">{badge_text}</span>
            </div>
            <div style="font-size:13px;color:#d1d5db;margin-top:8px;">
                Cierre: <b>{s.get('close', 0.0):.2f}</b> | SMA200: <b>{s.get('sma200', 0.0):.2f}</b><br>
                RSI(2): <b>{s.get('rsi2', 0.0):.1f}</b> | IBS: <b>{s.get('ibs', 0.0):.2f}</b> | Vol ATR: <b>{s.get('atr_regime', 0.0):.2f}</b>
            </div>
            <div style="font-size:12px;color:#9ca3af;margin-top:6px;border-top:1px solid #374151;padding-top:6px;">
                <b>Criterio del Cerebro:</b><br>• {reasons}
            </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta http-equiv="refresh" content="15">
    <title>Monitor Cuantitativo V3</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #111827; color: #f9fafb; margin: 0; padding: 12px; }}
        .header {{ background: #1f2937; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
        .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
        .stat-box {{ background: #111827; padding: 10px; border-radius: 8px; text-align: center; }}
        .stat-label {{ font-size: 11px; color: #9ca3af; text-transform: uppercase; }}
        .stat-val {{ font-size: 17px; font-weight: bold; margin-top: 4px; }}
        h2 {{ font-size: 14px; text-transform: uppercase; color: #9ca3af; margin: 18px 0 8px 4px; letter-spacing: 0.5px; }}
        .footer {{ font-size: 11px; color: #6b7280; text-align: center; margin-top: 24px; padding-bottom: 16px; }}
    </style>
</head>
<body>
    <div class="header">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:12px; background:#065f46; color:#34d399; padding:2px 8px; border-radius:12px; font-weight:bold;">● EN VIVO DEMO</span>
            <span style="font-size:12px; color:#9ca3af;">{data['timestamp_utc']}</span>
        </div>
        <div style="font-size:18px; font-weight:bold; margin-top:8px;">Cuenta #{acc['login']}</div>
        <div style="font-size:12px; color:#9ca3af;">{acc['server']}</div>
        <div class="stat-grid">
            <div class="stat-box">
                <div class="stat-label">Balance</div>
                <div class="stat-val">{acc['balance']:.2f} €</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Equity (Flotante)</div>
                <div class="stat-val" style="color:{pnl_color};">{acc['equity']:.2f} € <small>({pnl_sign}{pnl:.2f} €)</small></div>
            </div>
        </div>
    </div>

    {ab_html}

    <h2>Posiciones en Mercado Real (Modelo A)</h2>
    {pos_html}

    <h2>Posiciones en Sombra (Modelo B - Fantasma 70/30)</h2>
    {ghost_pos_html}

    <h2>Cerebro Cuantitativo (Semáforo de Índices)</h2>
    {sig_html}

    <div class="footer">
        Algoritmo Cuantitativo V3 • Actualización automática cada 15s • Solo Lectura
    </div>
</body>
</html>"""


def render_markdown(data: dict) -> str:
    if not data.get("connected"):
        return f"# Error de Conexión\n\n{data.get('error')}"

    acc = data["account"]
    pnl = acc["floating_pnl"]
    pnl_sign = "+" if pnl > 0 else ""
    local_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    utc_ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    hist = data.get("history_summary") or {}
    live_trades = hist.get("total_trades", 0)
    live_wins = hist.get("wins", 0)
    live_losses = hist.get("losses", 0)
    live_wr = hist.get("win_rate", 0.0)
    live_pnl = hist.get("net_pnl", 0.0)

    ghost = data.get("ghost") or {}
    ghost_balance = ghost.get("virtual_balance", 3000.0)
    ghost_equity = ghost.get("virtual_equity", 3000.0)
    ghost_pnl = ghost.get("net_pnl_eur", 0.0)
    ghost_wr = ghost.get("win_rate", 0.0)
    ghost_trades = ghost.get("total_trades", 0)
    ghost_wins = ghost.get("wins", 0)
    ghost_losses = ghost.get("losses", 0)
    ghost_positions = ghost.get("open_positions", [])

    diff_pnl = ghost_pnl - live_pnl
    diff_sign = "+" if diff_pnl > 0 else ""

    lines = [
        "# 🤖 Monitor Cuantitativo V3 (Admirals DEMO)",
        "",
        f"**Última actualización:** `{local_ts} (Hora España)` | `{utc_ts}`",
        "",
        "### 💰 Estado de la Cuenta DEMO",
        f"- **Cuenta:** DEMO #{acc['login']} ({acc['server']})",
        f"- **Balance:** {acc['balance']:.2f} EUR",
        f"- **Equity Flotante:** {acc['equity']:.2f} EUR ({pnl_sign}{pnl:.2f} EUR)",
        f"- **Historial Real:** {live_trades} operaciones cerradas / {live_wins} victorias (**{live_wr:.1f}% Win Rate**, {live_pnl:+.2f} EUR ganancia neta).",
        "",
        "### ⚔️ Batalla de Modelos A/B en Vivo (Cuenta Real DEMO vs Operador Fantasma)",
        "",
        "| Métrica / Parámetro | Modelo A (En Vivo DEMO) | Modelo B (Fantasma Híbrido 70/30) | Diferencial (B vs A) |",
        "| :--- | :---: | :---: | :---: |",
        "| **Arquitectura de Salida** | 100% Scalp (M15/M30) | 70% TP rápido + 30% Runner Trailing EMA20 | Runner dinámico de tendencia |",
        "| **Estrategia Forex (EURUSD)** | M15 Scalp | H1 Mean Reversion (+40 pips / -35 pips) | Sin fricción de spread |",
        "| **Riesgo por Operación** | **1.00%** (~30.58 €) | **1.00%** (~30.00 €) | Idéntico |",
        "| **Filtro Macro / Campana A1** | ✅ Activo (DE, ES, EU, US) | ✅ Activo (DE, ES, EU, US) | Idéntico |",
        f"| **Balance Acumulado** | **{acc['balance']:.2f} €** | **{ghost_balance:.2f} €** | **{ghost_balance - acc['balance']:+.2f} €** |",
        f"| **Equity Flotante** | **{acc['equity']:.2f} €** | **{ghost_equity:.2f} €** | **{ghost_equity - acc['equity']:+.2f} €** |",
        f"| **Operaciones Cerradas** | {live_trades} | {ghost_trades} | - |",
        f"| **Aciertos / Fallos** | {live_wins}W / {live_losses}L | {ghost_wins}W / {ghost_losses}L | - |",
        f"| **Tasa de Acierto (Win Rate)** | **{live_wr:.1f}%** | **{ghost_wr:.1f}%** | **{ghost_wr - live_wr:+.1f}%** |",
        f"| **PnL Neto Acumulado** | **{live_pnl:+.2f} €** | **{ghost_pnl:+.2f} €** | **{diff_sign}{diff_pnl:.2f} €** |",
        f"| **Posiciones Abiertas** | {len(data['positions'])} | {len(ghost_positions)} | - |",
        "",
        "### 📈 Posiciones Abiertas en Mercado Real (Modelo A)",
    ]
    if data["positions"]:
        lines.append("| Ticket | Símbolo | Tipo | Lotes | Entrada | Precio Actual | Stop Loss | PnL (EUR) |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
        for p in data["positions"]:
            lines.append(
                f"| #{p['ticket']} | {p['symbol']} | {p['type']} | {p['volume']:.2f} | "
                f"{p['price_open']:.2f} | {p['price_current']:.2f} | {p['sl']:.2f} | {p['profit_eur']:+.2f} € |"
            )
    else:
        lines.append("*Sin posiciones abiertas en este momento.*")

    if ghost_positions:
        lines.extend([
            "",
            "### 👻 Posiciones Abiertas en Sombra (Modelo B - Fantasma 70/30)",
            "| Ticket | Símbolo | Dirección | Lotes (70%/30%) | Entrada | TP Fijo (70%) | Stop Trailing | Estado | PnL Flotante |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for gp in ghost_positions:
            dir_str = "COMPRA" if gp.get("direction", 1) == 1 else "VENTA"
            lines.append(
                f"| #{gp['ticket']} | {gp['symbol']} | {dir_str} | {gp['lots_total']:.2f} ({gp['lots_70']:.2f}/{gp['lots_30']:.2f}) | "
                f"{gp['entry_price']:.4f} | {gp['fixed_tp']:.4f} | {gp['current_sl']:.4f} | `{gp['status']}` | {gp.get('current_floating_pnl_eur', 0.0):+.2f} € |"
            )

    lines.extend([
        "",
        "### 🧠 Semáforo del Cerebro Cuantitativo (Decisiones de los Algoritmos)",
        "| Mercado | Estrategia | Estado | Cierre | SMA200 | RSI(2) | IBS | Criterio / Motivo |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])
    for s in data.get("signals", []):
        is_buy = s.get("signal_active", False)
        status = "🟢 **COMPRA**" if is_buy else "🟡 *ESPERA*"
        reasons = "; ".join(s.get("reasons", []))
        close = s.get("close", 0.0)
        sma200 = s.get("sma200", 0.0)
        rsi2 = s.get("rsi2", 0.0)
        ibs = s.get("ibs", 0.0)
        lines.append(
            f"| {s['market']} | `{s['strategy']}` | {status} | {close:.2f} | {sma200:.2f} | {rsi2:.1f} | {ibs:.2f} | {reasons} |"
        )

    lines.extend([
        "",
        "### ⚡ Configuración y Salvaguardas en Producción",
        "- **Timeframe Principal:** M30 (GERMANY40, US100, [DJI30], [SP500], GOLD) / M15 ([IBEX35]) / H1 (EURUSD en Fantasma).",
        "- **Riesgo por Operación:** **1.00%** (~30.58 EUR sobre balance en cuenta DEMO).",
        "- **Filtro Macro:** Blindaje multi-país (DE, ES, EU, US) contra noticias de alto impacto Tier-1.",
        "- **Filtro de Apertura (Opción A1):** Veto de 5 minutos post-campana Frankfurt (07:00 UTC), Madrid (08:00 UTC) y Wall Street (13:30 UTC).",
        "- **Salvaguarda RiskPause:** Pausa de 60 min tras 2 pérdidas consecutivas; veto diario tras -1.5% sin reinicio.",
        "",
        "---",
        "*Actualizado automáticamente desde el motor local en segundo plano.*",
    ])
    return "\n".join(lines)


def sync_gist_worker(gist_id: str, interval_sec: int = 30):
    import shutil
    import subprocess
    import time
    gh_cmd = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
    while True:
        try:
            mt5 = get_mt5_module()
            if mt5:
                # Si no está inicializado, inicializarlo una vez
                mt5.initialize()
                d = get_dashboard_data(mt5)
                md = render_markdown(d)
                md_path = ROOT / "monitor_trading.md"
                md_path.write_text(md, encoding="utf-8")
                hist_path = ROOT / "HISTORICO_OPERACIONES.md"

                # 1. Sincronizar monitor_trading.md de forma individual
                subprocess.run(
                    [gh_cmd, "gist", "edit", gist_id, "-f", "monitor_trading.md", str(md_path)],
                    capture_output=True,
                    check=False,
                )

                # 2. Sincronizar HISTORICO_OPERACIONES.md de forma individual
                if hist_path.exists():
                    subprocess.run(
                        [gh_cmd, "gist", "edit", gist_id, "-f", "HISTORICO_OPERACIONES.md", str(hist_path)],
                        capture_output=True,
                        check=False,
                    )
        except Exception:
            pass
        time.sleep(interval_sec)


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    mt5 = None

    def do_GET(self):
        if self.path == "/json":
            data = get_dashboard_data(self.mt5)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))
            return

        if self.path == "/markdown":
            data = get_dashboard_data(self.mt5)
            md = render_markdown(data)
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.end_headers()
            self.wfile.write(md.encode("utf-8"))
            return

        data = get_dashboard_data(self.mt5)
        html = render_html(data)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        return


def main():
    import threading
    p = argparse.ArgumentParser(description="Servidor Web de Monitor Móvil")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--gist-id", default="58af579d3d6fc1961143e3293d51b40b", help="ID del Gist para sincronizar a la nube")
    args = p.parse_args()

    mt5 = get_mt5_module()
    if not mt5 or not mt5.initialize():
        print("ERROR: No se pudo conectar con MetaTrader 5.")
        return 1

    DashboardHandler.mt5 = mt5
    local_ip = get_local_ip()

    if args.gist_id:
        t = threading.Thread(target=sync_gist_worker, args=(args.gist_id, 30), daemon=True)
        t.start()
        print(f"• Sincronización nube 4G/5G: https://gist.github.com/julio7gil/{args.gist_id}")

    print("=" * 70)
    print("MONITOR MÓVIL EN VIVO INICIADO")
    print(f"• Acceso Local en esta máquina: http://localhost:{args.port}")
    print(f"• Acceso móvil (misma Wi-Fi): http://{local_ip}:{args.port}")
    print(f"• Acceso móvil (cualquier sitio 4G/5G): https://gist.github.com/julio7gil/{args.gist_id}")
    print("• Enlace API JSON: http://localhost:8080/json")
    print("Presiona Ctrl+C para detener.")
    print("=" * 70)

    try:
        with socketserver.TCPServer(("", args.port), DashboardHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

