# Validación inicial

Prueba realizada el 7 de noviembre de 2026 con Central US, D2as_v7 (2 vCPU / 8 GiB), Ubuntu 24.04, un mundo nuevo Paper 26.3 sobre Java 25 y Functions Flex Consumption.

## Comprobado

- 31 pruebas Python, 8 del portal y 8 escenarios de preflight aprobados; sintaxis PowerShell y compilación Bicep verificadas.
- Creación de infraestructura y publicación del código desde Azure CLI local con la sesión del propietario. GitHub Actions no fue necesario.
- Portal HTTPS en modo real, API con 401 sin contraseña y 200 con la contraseña correcta; preflight CORS 204 para el origen publicado.
- Panel HTTPS 200; instalador bloqueado con 404 después de crear el administrador; Wings público exige autenticación (401).
- Paper completó el arranque y el portal llegó al estado ready por heartbeat real.
- Prueba de apagado sin jugadores con un minuto temporal: Paper guardó los mundos y cerró la escritura; Azure terminó en Deallocated y el portal volvió a off.
- El siguiente arranque recuperó el mundo existente. Tras resolver la comunicación local entre panel y Wings por loopback, el ciclo medido desde la solicitud hasta ready fue de **107,5 segundos**.
- Cinco ping/pong del protocolo Minecraft desde el equipo administrador: mediana **139,2 ms**, mínimo 136,6 y máximo 146,7. Es una muestra de una conexión, no una garantía para otras redes.
- Valores finales restaurados: inactividad 15 minutos, plazo de arranque 15 minutos, máximo de sesión 8 horas y presupuesto operativo de 180 horas mensuales.

Se guardaron respaldos privados de la configuración del panel, Wings y agente fuera de Git. Los identificadores y secretos de esta instalación no forman parte de este documento portátil.

## Límites de la prueba

No se inició sesión con una cuenta Microsoft/Minecraft real ni se evaluó una partida con jugadores simultáneos. El propietario debe comprobar su entrada desde Minecraft Java 26.3, consola y gestor de archivos del panel en su navegador. El tiempo de arranque puede variar según la asignación de Azure y el mundo. No se configuró una programación automática de backups del mundo; revisar la operación de backups antes de usarlo como mundo importante.

La validación inicial del plan clásico Y1 falló por cuota cero; se cambió a Flex Consumption. El instalador se corrigió para definir COMPOSER_HOME y reanudar Composer tras un fallo parcial. La exportación de Wings convierte las colecciones a arrays antes de generar YAML. Estas correcciones se conservaron en las fuentes.
