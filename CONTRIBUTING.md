# Colaboración en Trading V2

## Flujo de trabajo acordado

**No subir cambios directamente a `main`**. Cada persona trabaja en una rama propia y abre una Pull Request (PR).

1. Actualizar el repositorio local: `git switch main && git pull origin main`.
2. Crear una rama descriptiva: `git switch -c feature/nombre-del-cambio`.
3. Modificar el código y ejecutar las pruebas offline:
   `python -m unittest discover -s tests -p 'test_*.py' -v`.
4. Confirmar los cambios con Git, y subir la rama: `git push -u origin feature/nombre-del-cambio`.
5. Abrir Pull Request hacia `main`. Pedir revisión de la otra persona y esperar a CI verde.
6. Fusionar solo después de revisión y sin alertas; borrar la rama fusionada (desde la UI de GitHub).

## Requisitos de una Pull Request

- Objetivo del cambio y limitaciones documentados.
- Tests nuevos para cambios en cálculo, riesgo, señales, modelos o ejecución.
- Ningún acceso nuevo a ejecución MT5 sin revisión explícita de seguridad, demo-only guard y pruebas específicas.
- No afirmar que un backtest prueba rentabilidad futura.
- Nunca modificar con un resultado del holdout los parámetros que generaron ese resultado.

## Seguridad del repositorio público

- No subir nunca contraseñas, tokens, números de cuenta, claves privadas, datos personales ni capturas con información sensible.
- No publicar ZIP históricos descargados de una cuenta personal sin revisarlos; los ficheros locales están ignorados en `.gitignore`.
- Toda PR debe distinguir entre análisis offline, diagnóstico MT5 solo lectura y ejecución que envía órdenes.
- El viejo `live_trader_mt5.py --live` no es apto para activarse. Tampoco hay autorización de auto-ejecución para los módulos V2.

## Protección recomendada de main (configuración manual en GitHub)

En el repositorio: Settings > Rules > Rulesets > New branch ruleset.
Configurar para la rama **main**:

- Activar y aplicar a todos los usuarios que puedan escribir, incluidos administradores si es posible.
- Require a pull request before merging: mínimo 1 aprobación de otro colaborador.
- Require status checks to pass: añadir **tests** del workflow **V2 offline tests**.
- Require conversation resolution before merging.
- Block force pushes; impedir borrado de `main`.
- No activar auto-merge de código sensible sin revisión.

**Nota:** para poder seleccionar el status check, GitHub debe haber ejecutado el workflow al menos una vez con éxito en el repositorio. Estas reglas afectan a PR futuras, no constituyen validación de ningún modelo.

## Incorporar compañero

El propietario invita a través de Settings > Collaborators > Add people y el compañero debe aceptar la invitación. Para un repositorio personal, el rol de colaborador suele otorgar acceso de escritura, no hace falta compartir las credenciales del propietario.

Si hay conflictos al subir: traer los cambios de `main` a la rama de trabajo y resolverlos antes de fusionar. No utilizar `--force` sobre `main`.
