# Trading V2 — Exportación histórica Admirals DEMO (solo lectura)

Requiere MetaTrader 5 abierto con cuenta Admirals DEMO y el paquete
\`MetaTrader5\` instalado en el Python que ejecuta el comando.

## Ejecutar en Windows PowerShell

\`\`\`powershell
python scripts/exportar_historial_admirals_mt5.py
\`\`\`

Si Windows tiene varios terminales MT5, indicar la ruta del terminal Admirals:

\`\`\`powershell
python scripts/exportar_historial_admirals_mt5.py --terminal "C:\ruta\Admirals\terminal64.exe"
\`\`\`

Si solo dispones del script descargado en tu carpeta de trabajo:

\`\`\`powershell
python .\exportar_historial_admirals_mt5.py
\`\`\`

La exportación predeterminada solicita 12.000 velas M15 y 3.500 velas H1
por símbolo, excluyendo la posición 0 (barra en formación/última del servidor).
Activos exactos: GERMANY40, [SP500], [DJI30], GOLD y EURUSD.

Genera \`admirals_historial_local.zip\` con diez CSV (uno por activo/periodicidad)
y \`admirals_manifest.json\` (calidad, spread histórico y especificaciones).
El ZIP NO incluye login, titular, contraseñas, tokens ni rutas de máquina.

**Subir el ZIP a la conversación con ChatGPT, NO al repositorio GitHub público.**

## Limitaciones

- Solo cuenta DEMO Admirals. Cuenta real/otro bróker => bloqueado.
- Nunca envía órdenes, ni cambia Market Watch, ni modifica posiciones.
- La cantidad de barras depende del histórico ofrecido por Admirals y
  de la opción MT5 Herramientas > Opciones > Gráficos > Máx. barras en gráfico.
- Fechas interpretadas como UTC desde \`time\` del servidor MT5; hay que
  verificar zonas horarias y coherencia entre M15/H1, sin aplicar correcciones
  arbitrarias.
- Spreads en cero NO significan que la operativa sea gratuita.
- Faltan comisiones, swaps efectivamente cobrados, deslizamiento y
  tick data; no usar estas series para inferir rentabilidad real.
- Con el mercado cerrado (fin de semana) puede descargarse historial,
  pero no es posible medir spreads actuales representativos.
