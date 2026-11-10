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

## Actualización: apagado manual y juegos

Actualización verificada el 7 de noviembre de 2026, hora de Chile:

- 36 pruebas Python, 15 del portal y sus juegos y 8 escenarios de preflight aprobados: 59 en total. Se verificaron también sintaxis JavaScript, referencias HTML y el acordeón cerrado inicialmente.
- Portal y API publicados sin recrear infraestructura ni modificar la configuración del juego. Los cuatro archivos web actualizados respondieron HTTP 200 y coincidieron byte por byte con las fuentes locales. La configuración real del portal se conservó.
- `POST /api/stop` sin contraseña devolvió 401. La petición autenticada pasó a `stopping` sin desasignar directamente desde el endpoint.
- Antes de la prueba se confirmó cero jugadores tanto en la API como consultando Minecraft. Se observó el cierre de escritura de Overworld, Nether y End y la salida del contenedor; después Azure confirmó `PowerState/deallocated`.
- El siguiente encendido mediante Fogata volvió a `ready`. Paper completó la carga; el mundo importado y los datos de jugador seguían presentes. No se verificó visualmente el contenido dentro de Minecraft en esta prueba.
- Las pruebas locales cubren confirmación/cancelación de apagado, solicitudes repetidas, espera de confirmación de cierre, protección frente a respuestas antiguas de estado, límite exacto de 15 segundos del contador y colisiones/saltos del corredor. Los juegos y la fogata interactiva no hacen llamadas a Azure.

La herramienta de navegador no obtuvo permiso para abrir la vista local, por lo que quedó pendiente la revisión visual y de interacción en un navegador real, incluyendo móvil y movimiento reducido. Las comprobaciones de DOM simulado no sustituyen esa revisión. No se implementó modo mantenimiento ni se cambió el apagado automático existente.

## Actualización: selección exclusiva de servidores

El 8 de noviembre de 2026 se importó el paquete de servidor DeceasedCraft 5.10.17, verificando su archivo SHA256 antes de extraerlo. Forge 47.4.0 se instaló con Java 17; el límite de Pelican es 6144 MiB y el heap máximo 5120 MiB. Se conservaron el tamaño de la VM y el mundo Paper. Se guardaron respaldos privados del mundo, base del panel y agente anteriores.

- 39 pruebas Python, 16 de portal/juegos y 8 de preflight aprobadas (63 en total); compilación Bicep, sintaxis PowerShell/JavaScript y lint PHP de los helpers verificados.
- Arranque real de DeceasedCraft completado y estado `ready` confirmado por heartbeat. Una muestra en reposo consumió aproximadamente 3,9 GiB dentro del límite efectivo de Docker de 6,3 GiB (incluye margen de Wings).
- Se comprobó el bloqueo compartido: otro proceso `flock` terminó con código 1 mientras el Minecraft activo mantenía el permiso, sin ejecutar una segunda JVM.
- La API rechazó con 409 elegir otro servidor mientras la VM estaba activa. Tras cierre y desasignación se pudo seleccionar Paper, cargar el mundo existente y volver a cerrarlo.
- El ciclo terminó volviendo a seleccionar DeceasedCraft desde apagado y recuperando su mundo recién creado; el portal confirmó `ready` de nuevo. Se comprobó que solo el contenedor seleccionado estaba ejecutándose.
- CORS aceptó POST con `content-type` y `x-portal-password`; los archivos web publicados coincidieron con las fuentes locales. El plazo temporal de instalación se restauró a 15 minutos.

No se hizo una partida real del modpack, ni pruebas con jugadores, hordas o generación intensiva de ciudades. El arranque exitoso por debajo de la RAM mínima publicada no demuestra capacidad bajo carga. El chat de voz del pack no está expuesto; el propietario usa Discord. La revisión visual del selector sigue pendiente; el navegador automatizado no tenía permiso para la vista local en la prueba anterior.

## Actualización: Hardcore Soulbound

El 10 de noviembre de 2026 se añadió un tercer perfil independiente, Hardcore Soulbound 1.0.1 sobre Minecraft vanilla 26.3 y Java 25. Límite de Pelican 4096 MiB, heap máximo 3072 MiB y puerto TCP 25567. La descarga se verificó con el SHA512 publicado por Modrinth; no se redistribuye en el repositorio.

- Preflight de lectura confirmó proveedores y cuota en la suscripción autorizada; se mantuvo el tamaño de la VM. Se ajustó el acceso administrativo a la nueva IP del propietario, conservando `/32`.
- Se confirmó que no había jugadores antes de detener los perfiles existentes. Se respaldaron el catálogo del nodo y la base SQLite del panel. Los mundos de Paper y DeceasedCraft no se reemplazaron.
- Vanilla completó el arranque y Fogata llegó a `ready`. Desde la consola se confirmó que estaban habilitados `vanilla` y `file/hardcore-soulbound-1.0.1.zip`. La consulta de `#pending_install HCSB.Var` devolvió 1: el pack espera al primer jugador para inicializar la partida.
- La orden Guardar y apagar guardó jugadores y las tres dimensiones; Azure confirmó la desasignación antes del siguiente arranque.
- El siguiente arranque desde Fogata recuperó el mundo y volvió a `ready`, con solo Soulbound ejecutándose. Hubo fallos transitorios de conexión durante ese arranque; al terminar se verificó desde la VM HTTP 200 tanto en discovery como en publickeys de Minecraft y el 401 esperado de la API Fogata sin contraseña.
- Se ejecutaron las 63 comprobaciones locales existentes, compilación Bicep, sintaxis JavaScript y lint PHP del helper de registro. El frontend y la política de control no requirieron cambios: el catálogo ya admite IDs adicionales.

No se inició una sesión de jugador para probar una muerte, el reinicio de intentos o el menú interactivo. La vida compartida conserva el valor predeterminado desactivado y puede habilitarse dentro del juego. El plazo temporal de instalación se restauró a 15 minutos.

## Límites de la prueba inicial

No se inició sesión con una cuenta Microsoft/Minecraft real ni se evaluó una partida con jugadores simultáneos. El propietario debe comprobar su entrada desde Minecraft Java 26.3, consola y gestor de archivos del panel en su navegador. El tiempo de arranque puede variar según la asignación de Azure y el mundo. No se configuró una programación automática de backups del mundo; revisar la operación de backups antes de usarlo como mundo importante.

La validación inicial del plan clásico Y1 falló por cuota cero; se cambió a Flex Consumption. El instalador se corrigió para definir COMPOSER_HOME y reanudar Composer tras un fallo parcial. La exportación de Wings convierte las colecciones a arrays antes de generar YAML. Estas correcciones se conservaron en las fuentes.
