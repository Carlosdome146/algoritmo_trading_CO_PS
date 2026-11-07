@echo off
chcp 65001 > nul
echo ======================================================================
echo    INICIANDO SISTEMA DUAL CUANTITATIVO V3 - ADMIRALS DEMO (TEST A/B)
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/3] Iniciando Servidor de Monitorizacion Movil (Dashboard + Gist)...
start "Monitor Movil V3" /min python scripts/dashboard_movil.py --port 8080 --gist-id 58af579d3d6fc1961143e3293d51b40b

timeout /t 3 /nobreak > nul

echo [2/3] Iniciando Modelo A: Ejecutor en MetaTrader 5 DEMO (Modo Live 1.0%% Riesgo)...
start "Modelo A - MT5 DEMO" python -m trading_v2.execution.demo_paper_trader --live --strategy institutional_sniper_scalp --timeframe M15_M30 --symbols GERMANY40 US100 [SP500] [DJI30] [IBEX35] GOLD EURUSD --risk-fraction 0.0100 --max-concurrent-indices 2 --poll-seconds 15.0

timeout /t 3 /nobreak > nul

echo [3/3] Iniciando Modelo B: Operador Fantasma en Sombra (Hibrido 70/30 + H1 Forex)...
start "Modelo B - Fantasma 70/30" python -m trading_v2.execution.ghost_shadow_trader

echo.
echo ======================================================================
echo  SISTEMA DUAL EN MARCHA CORRECTAMENTE
echo  • Batalla A/B: Modelo A (Live Demo) vs Modelo B (Fantasma 70/30)
echo  • Enlace movil 4G/5G: https://gist.github.com/julio7gil/58af579d3d6fc1961143e3293d51b40b
echo  • Enlace local Wi-Fi: http://localhost:8080
echo  • App MetaTrader 5: Cuenta #58678879 (AdmiralsGroup-Demo)
echo ======================================================================
echo Puedes minimizar esta ventana. Para detener el sistema, cierra las consolas.
pause
