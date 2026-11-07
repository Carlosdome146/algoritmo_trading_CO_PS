@echo off
chcp 65001 > nul
title OPERADOR FANTASMA EN SOMBRA - TEST A/B HIBRIDO 70/30 (MODO SOLO LECTURA)
echo ======================================================================
echo    OPERADOR FANTASMA EN SOMBRA (MODO SOLO LECTURA - ZERO RIESGO)
echo ======================================================================
echo.
echo  • Arquitectura:        Hibrido 70/30 (70%% TP Fijo + 30%% Runner Trailing EMA20)
echo  • Forex (EURUSD):      H1 Mean Reversion (TP +40 pips / SL -35 pips)
echo  • Indices y Oro:       GERMANY40, US100, [SP500], [DJI30], [IBEX35], GOLD en M30
echo  • Riesgo por operacion: 1.00%% (~30.00 EUR sobre capital virtual de 3,000 EUR)
echo  • Salvaguardas:        Filtro Macro (DE, ES, EU, US) + Campana A1 (Veto 5 min)
echo  • Seguridad Broker:    MODO SOLO LECTURA ESTRICTO (Cero ordenes enviadas a MT5)
echo  • Persistencia:        data/ghost_trader_state.json
echo.
echo ======================================================================
echo Conectando con MetaTrader 5 (Solo Lectura) y arrancando simulacion...
echo (Presiona Ctrl + C para detener el operador fantasma en cualquier momento)
echo ======================================================================
echo.

cd /d "%~dp0"
python -m trading_v2.execution.ghost_shadow_trader

echo.
echo El Operador Fantasma se ha detenido.
pause
