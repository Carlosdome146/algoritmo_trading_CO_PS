@echo off
chcp 65001 > nul
echo ======================================================================
echo    INICIANDO SISTEMA CUANTITATIVO V3 - ADMIRALS DEMO (AUTOMATIZADO)
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/2] Iniciando Servidor de Monitorizacion Movil (Dashboard + Gist)...
start "Monitor Movil V3" /min python scripts/dashboard_movil.py --port 8080 --gist-id 58af579d3d6fc1961143e3293d51b40b

timeout /t 3 /nobreak > nul

echo [2/2] Iniciando Ejecutor en MetaTrader 5 DEMO (Modo Live Seguro)...
start "Ejecutor MT5 DEMO" python -m trading_v2.execution.demo_paper_trader --live --timeframe D1 --strategy idx_rsi2_dip_regime --symbols GERMANY40 [SP500] US100 [DJI30] --risk-fraction 0.0075 --poll-seconds 30.0

echo.
echo ======================================================================
echo  SISTEMA EN MARCHA CORRECTAMENTE
echo  • Enlace movil 4G/5G: https://gist.github.com/julio7gil/58af579d3d6fc1961143e3293d51b40b
echo  • Enlace local Wi-Fi: http://192.168.0.28:8080
echo  • App MetaTrader 5: Cuenta #58678879 (AdmiralsGroup-Demo)
echo ======================================================================
echo Puedes minimizar esta ventana. Para detener el sistema, cierra las consolas.
pause
