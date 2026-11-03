@echo off
chcp 65001 > nul
title BOT DE TRADING CUANTITATIVO INTRADIA - ADMIRALS DEMO 1:100
echo ======================================================================
echo       BOT DE TRADING CUANTITATIVO INTRADIA (M15 / M30) - ADMIRALS DEMO
echo ======================================================================
echo.
echo  • Activos monitorizados: GERMANY40, US100, [SP500], [DJI30], [IBEX35], GOLD, EURUSD
echo  • Timeframe adaptativo:  M15 (EURUSD, [IBEX35]) / M30 (Indices y Oro)
echo  • Estrategia:            institutional_sniper_scalp (Micro-Sweep Reclaim Multi-Gatillo)
echo  • Riesgo calibrado:      0.80%% por operacion (Drawdown cartera < 5.0%%)
echo  • Limite correlacion:    Maximo 2 indices bursatiles simultaneos
echo  • Broker:                Admirals DEMO (Apalancamiento 1:100, Capital 3,000 EUR)
echo.
echo ======================================================================
echo Conectando con MetaTrader 5 y arrancando escaneo continuo...
echo (Presiona Ctrl + C para detener el bot en cualquier momento)
echo ======================================================================
echo.

cd /d "%~dp0"
python -m trading_v2.execution.demo_paper_trader --live --strategy institutional_sniper_scalp --timeframe M15_M30 --symbols GERMANY40 US100 [SP500] [DJI30] [IBEX35] GOLD EURUSD --risk-fraction 0.0080 --max-concurrent-indices 2 --poll-seconds 15.0

echo.
echo El bot se ha detenido.
pause
