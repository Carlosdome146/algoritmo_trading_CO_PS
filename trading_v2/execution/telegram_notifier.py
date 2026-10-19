"""Notificador de telemetría para Telegram (y logs locales).

Permite recibir en el teléfono móvil:
- Alertas inmediatas de ejecución (entradas, SL, lotes, comisiones/spreads).
- Avisos de cierre de posición con resultado en EUR y motivo.
- Notificaciones periódicas del estado del cerebro del sistema (por qué opera o por qué espera).
- Alertas de salvaguarda de riesgo (RiskPause, límite diario).

Usa únicamente la librería estándar (urllib) para no añadir dependencias pesadas.
Si no se configuran tokens, opera en modo silencioso/log local sin interrumpir la operativa.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TelegramConfig:
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: bool = False

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or None
        return cls(bot_token=token, chat_id=chat_id, enabled=bool(token and chat_id))


class TelegramNotifier:
    def __init__(self, config: Optional[TelegramConfig] = None):
        self.config = config or TelegramConfig.from_env()

    def send_message(self, text: str) -> bool:
        """Envía un mensaje de texto formateado por Telegram."""
        if not self.config.enabled or not self.config.bot_token or not self.config.chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except Exception as exc:
            # Nunca bloquear la operativa del robot si falla la red o Telegram
            print(f"[TELEGRAM_ERROR] No se pudo enviar notificación: {exc}")
            return False

    def notify_bot_start(self, account_login: int, balance: float, mode: str, timeframe: str) -> bool:
        msg = (
            f"🚀 <b>ROBOT CUANTITATIVO INICIADO</b>\n\n"
            f"• <b>Cuenta:</b> DEMO #{account_login} (Admirals)\n"
            f"• <b>Balance:</b> {balance:.2f} EUR\n"
            f"• <b>Modo:</b> {mode}\n"
            f"• <b>Timeframe:</b> {timeframe}\n"
            f"• <b>Hora UTC:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S')}\n\n"
            f"<i>Monitorizando índices para la sesión...</i>"
        )
        return self.send_message(msg)

    def notify_order_entry(
        self,
        symbol: str,
        strategy: str,
        side: str,
        lots: float,
        price: float,
        sl: float,
        risk_eur: float,
        spread_pts: float,
    ) -> bool:
        side_label = "🟢 COMPRA (LONG)" if side.upper() == "BUY" else "🔴 VENTA (SHORT)"
        msg = (
            f"⚡ <b>ORDEN EJECUTADA EN DEMO</b>\n\n"
            f"• <b>Activo:</b> {symbol}\n"
            f"• <b>Tipo:</b> {side_label}\n"
            f"• <b>Estrategia:</b> <code>{strategy}</code>\n"
            f"• <b>Volumen:</b> {lots:.2f} lotes\n"
            f"• <b>Precio Entrada:</b> {price:.2f}\n"
            f"• <b>Stop Loss:</b> {sl:.2f}\n"
            f"• <b>Riesgo Monetario:</b> {risk_eur:.2f} EUR\n"
            f"• <b>Spread Bróker:</b> {spread_pts:.1f} pts\n"
            f"• <b>Comisión Bróker:</b> 0.00 EUR (Trade.MT5)"
        )
        return self.send_message(msg)

    def notify_order_exit(
        self,
        symbol: str,
        ticket: int,
        pnl_eur: float,
        pnl_r: float,
        reason: str,
        bars_held: int,
    ) -> bool:
        icon = "🎉" if pnl_eur >= 0 else "🛑"
        res_label = "GANANCIA" if pnl_eur >= 0 else "PÉRDIDA"
        msg = (
            f"{icon} <b>POSICIÓN CERRADA ({res_label})</b>\n\n"
            f"• <b>Activo:</b> {symbol} (Ticket #{ticket})\n"
            f"• <b>Resultado Neto:</b> {pnl_eur:+.2f} EUR ({pnl_r:+.2f} R)\n"
            f"• <b>Motivo Salida:</b> <code>{reason}</code>\n"
            f"• <b>Velas en Mercado:</b> {bars_held}\n"
            f"• <b>Hora UTC:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
        )
        return self.send_message(msg)

    def notify_market_status(self, summary_lines: list[str]) -> bool:
        content = "\n".join(summary_lines)
        msg = (
            f"📊 <b>ESTADO DEL CEREBRO CUANTITATIVO</b>\n\n"
            f"{content}\n\n"
            f"<i>Hora UTC: {datetime.now(timezone.utc).strftime('%H:%M:%S')}</i>"
        )
        return self.send_message(msg)
