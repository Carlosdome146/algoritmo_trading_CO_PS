@echo off
chcp 65001 >nul
echo =====================================================================
echo  📊 GENERANDO CUADRO DE MANDO EJECUTIVO Y FISCAL (V3)
echo =====================================================================
cd /d "%~dp0"
python -m trading_v2.reporting.daily_executive_dashboard
echo.
echo Abriendo informe en el editor/navegador predeterminado...
start "" "%~dp0CUADRO_MANDO_DIARIO.md"
