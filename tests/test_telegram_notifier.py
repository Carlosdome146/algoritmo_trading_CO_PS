"""Tests para el notificador de Telegram."""
from __future__ import annotations

import unittest
from trading_v2.execution.telegram_notifier import TelegramConfig, TelegramNotifier


class TelegramNotifierTests(unittest.TestCase):
    def test_disabled_by_default_without_tokens(self):
        cfg = TelegramConfig(bot_token=None, chat_id=None, enabled=False)
        notifier = TelegramNotifier(cfg)
        self.assertFalse(notifier.send_message("Test"))
        self.assertFalse(notifier.notify_bot_start(12345, 3000.0, "SIMULATION", "D1"))
        self.assertFalse(notifier.notify_order_entry("US100", "idx_rsi2_dip", "BUY", 0.02, 29000, 28000, 21.0, 90.0))
        self.assertFalse(notifier.notify_order_exit("US100", 101, 35.0, 1.6, "DAILY_RULE_EXIT_SMA5", 3))

    def test_mock_send_does_not_crash(self):
        cfg = TelegramConfig(bot_token="fake_token", chat_id="fake_chat", enabled=True)
        notifier = TelegramNotifier(cfg)
        # Apunta a un token falso, debe capturar la excepción y devolver False sin romper el programa
        result = notifier.send_message("Mensaje de prueba")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
