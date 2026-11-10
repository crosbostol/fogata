# Alternar mundos, modpacks y datapacks

Fogata admite un catálogo de servidores del mismo nodo, con **uno activo por sesión de VM**. Cada servidor conserva su mundo. El tamaño de Azure no cambia al elegir otro.

## Uso diario

1. Entra al portal. Con la VM apagada, elige el mundo en el selector y pulsa Encender.
2. Espera a Listo y usa la dirección que muestra el portal: cada servidor tiene su puerto.
3. Para cambiar, pulsa Guardar y apagar, confirma y espera Apagado. Después elige el otro mundo y enciéndelo. Esta versión hace un ciclo completo de VM; no cambia servidores en caliente.

Pelican permite gestionar ambos desde su panel. Los arranques llevan `flock -n /mnt/fogata/active.lock`, sobre un archivo compartido en la VM. El segundo proceso sale sin ejecutar Java si el otro tiene el bloqueo. No retires ese prefijo ni borres/reemplaces el archivo mientras haya una sesión: es la protección para la RAM del nodo. Una cuenta administradora puede modificar esta configuración; no es una barrera contra administradores maliciosos.

## Instalación probada: DeceasedCraft 5.10.17

- Minecraft 1.20.1, Forge 47.4.0, imagen Java 17, 234 JARs del paquete de servidor.
- Límite en Pelican: 6144 MiB. Wings puede aplicar su margen de memoria adicional. Heap: `-Xms512M -Xmx5120M`, leído expresamente desde `user_jvm_args.txt`.
- Distancia de vista 6 y simulación 4 para comenzar. Whitelist y autenticación oficial habilitadas. Ajusta después de medir partidas reales.
- Puerto TCP 25566; Paper mantiene 25565. Cada mundo tiene inventarios propios. La whitelist se copió al importar; los cambios posteriores no se sincronizan automáticamente.
- Cada jugador necesita el **cliente DeceasedCraft 5.10.17 estándar**, no el paquete Server ni la edición DH. Los mods de calidad de vida de un cliente 26.3 no reemplazan ese perfil.
- El pack publica 8 GB mínimos y 10 GB o más recomendados para servidor. Esta instalación de 6 GB es una prueba por decisión del propietario. Que complete el arranque no garantiza rendimiento al generar ciudades o con varios jugadores. El arranque frío del pack puede tardar más que Paper.
- El chat de voz incluido escucha UDP 24454 dentro del contenedor; no se publicó ese puerto en esta primera instalación. El juego por TCP funciona independientemente. Habilitar voz requiere una asignación adicional en Wings y la regla UDP de Azure.

El paquete y las recomendaciones están en [la página del autor](https://www.curseforge.com/minecraft/modpacks/deceasedcraft). Sus binarios no se redistribuyen en este repositorio.

## Hardcore Soulbound: vanilla con datapack

El tercer perfil utiliza Minecraft **vanilla 26.3**, Java 25 y Hardcore Soulbound **1.0.1**. El autor solo ha probado el datapack en vanilla; por eso no se instaló sobre Paper. No requiere mods ni resource packs en el cliente.

- Mundo nuevo independiente, puerto TCP **25567**, límite de Pelican 4096 MiB y heap máximo 3072 MiB. Whitelist y autenticación oficial habilitadas. La whitelist se copia al crear el perfil; sus cambios posteriores son independientes.
- ZIP original dentro de `world/datapacks/`, con versión y hash verificados contra la API de Modrinth. Los binarios no se publican en GitHub.
- Al primer ingreso se completa la inicialización del datapack. Su menú se abre con **G** (acciones rápidas) o desde el botón del menú de pausa. Permite iniciar partidas, configurar y consultar estadísticas. Si cambiaste las teclas, revisa la asignación de acciones rápidas.
- Predeterminados del archivo 1.0.1: una vida, dificultad difícil, regeneración natural habilitada, 10 corazones, reinicio automático de intentos y **vida compartida desactivada**. Puedes habilitarla y cambiar a español desde la configuración del pack.
- La mecánica reinicia los intentos de este perfil. Paper y DeceasedCraft conservan sus propios mundos. El bloqueo compartido sigue permitiendo una sola JVM activa.

Fuente y descarga: [Hardcore Soulbound en Modrinth](https://modrinth.com/datapack/hardcore-soulbound). Para crear otro perfil vanilla, `vm/register-vanilla.php` acepta JSON por stdin con `name`, `minecraft` y `port`, usa Java 25 y fija 4 GiB de límite/3 GiB de heap. Es una herramienta administrativa para servidores nuevos, no un instalador universal para cualquier versión de Minecraft. Después hay que instalar el datapack, aplicar `exclusive-servers.php` y registrar el perfil en ambos catálogos como se explica abajo.

## Agregar otro pack sin rehacer Fogata

La primera versión incluye herramientas CLI para un pack Forge 1.20.1; no promete detectar cualquier instalador o cargador automáticamente.

1. Descarga el **server pack** oficial y revisa Minecraft, cargador, Java y RAM. Usa un servidor nuevo para un pack diferente. Nunca mezcles mods de packs distintos sobre un mundo importante.
2. Detén y respalda los servidores existentes. Para la instalación inicial, el administrador debe ampliar de forma temporal y acotada el plazo de arranque si hace falta y restaurarlo al terminar. Detener solo el juego no desactiva la supervisión de Azure.
3. `vm/register-forge.php`, ejecutado por CLI como `www-data` desde la VM, recibe JSON por stdin con `name`, `forge` (por ejemplo `1.20.1-47.4.0`) y `port`. Registra un servidor con el egg oficial Forge, Java 17 y 6144 MiB. Espera a que Wings complete la instalación. **Para versiones que requieren otro Java hay que adaptar este helper antes.**
4. Comprime la carpeta con raíz `pack/`, calcula SHA256 y transfiere el `.tar.gz` por SCP/SFTP. `vm/install-server-pack.py` recibe el archivo, `--sha256`, `--server UUID`, `--port`, `--heap-mib` y `--accept-minecraft-eula`. Solo importa en un Forge instalado y detenido, sin mundo ni contenido previo de pack. Copia mods/configuraciones admitidas sin ejecutar scripts del archivo. El switch EULA representa la aceptación explícita del propietario. Prepara la whitelist antes de encender.
5. `vm/exclusive-servers.php` recibe por stdin un array JSON de UUIDs ya detenidos y añade el montaje compartido y el prefijo de bloqueo. Antes prepara `/var/lib/fogata/exclusive/active.lock` con permisos para el usuario de Wings, permite esa ruta en `allowed_mounts` de Wings y reinicia Wings con ambos juegos detenidos. El helper conserva el arranque de Paper y configura Forge para leer los argumentos importados. Ambos yolks deben disponer de `flock`.
6. Registra los IDs estables del catálogo en `/etc/fogata/servers.json`: objetos con `id`, `container` (UUID) y `port`. Archivo administrado por root. El agente empieza únicamente el elegido por el controlador, cuenta jugadores de todos los registrados y espera su cierre antes de confirmar el apagado.
7. Configura `SERVERS_JSON` en la Function: array de objetos públicos `id`, `name` y `address`. Los IDs deben coincidir con el archivo del agente. Guarda la misma lista en `.local/server-catalog.json`; `Deploy.ps1` la conserva al reaplicar (también acepta `-ServerCatalogPath`). No copies UUIDs, IP o catálogos personales al código versionado.
8. Añade el puerto TCP a la asignación de Pelican y al NSG. Prueba arranque, bloqueo del segundo, guardado y recuperación antes de compartirlo.

Cambiar entre los servidores ya registrados es una operación del portal. **Actualizar un pack existente es una migración**, con respaldo y revisión de compatibilidad del mundo según el autor. El importador rechaza sobrescribir un mundo existente a propósito; una actualización no se resuelve copiando JARs encima de los viejos.
