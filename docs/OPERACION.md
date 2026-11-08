# Puesta en marcha y operación

## Después de desplegar Azure

1. Lee `.local/deployment.json` y comprueba que corresponde a tu suscripción, región y nombre de proyecto.
2. Comprueba el resultado de la extensión de instalación. Que la VM exista no confirma que Pelican esté instalado ni que Wings gestione un servidor.
3. Accede por SSH como `azureuser` con tu clave privada. SSH y SFTP se restringen al CIDR que indicaste; si cambia tu IP, actualiza ese parámetro mediante el despliegue.
4. Prepara el entorno de Pelican mediante el comando de abajo; después abre `https://<nombre-Azure>/installer` desde la IP administrativa y termina el instalador web, incluida la cuenta administradora. Conserva su contraseña y un backup de `APP_KEY` fuera del repositorio y de la VM.
5. Crea un nodo Wings, instala su configuración y habilita su servicio. Crea una asignación para el puerto `25565` y un servidor Paper con una imagen Java compatible.
6. Configura el UUID real del contenedor para el monitor de Fogata como se indica abajo. No inventes una ruta del volumen antes de crear el servidor.
7. Acepta la EULA cuando corresponda, arranca el contenedor y verifica consola, conexión Minecraft y heartbeat.
8. Prueba un cierre ordenado, desasigna la VM y comprueba desde el portal que puedes volver a encenderla.

Desde SSH, inicializa el entorno del panel:

```bash
cd /var/www/pelican
sudo -u www-data php8.4 artisan p:environment:setup
```

Sigue las opciones de la versión instalada; SQLite es suficiente para esta instalación pequeña. Cuando el instalador web haya terminado y hayas guardado la configuración del nodo en `/etc/pelican/config.yml`, inicia los servicios:

```bash
sudo systemctl enable --now wings pelican-queue
sudo systemctl status wings pelican-queue --no-pager
```

El nodo usa el hostname Azure y el puerto externo HTTPS `8443`. Caddy termina TLS y reenvía a Wings por HTTP en `127.0.0.1:8080`; configura coherentemente el proxy y la escucha local de Wings según su documentación. No copies un puerto o esquema distinto solo porque aparezca por defecto en el panel.

En la versión que ofrece dos puertos distintos, establece **Daemon Listening Port = 8080** y **Daemon Connecting Port = 8443**. El primero corresponde a la escucha local de Wings; el segundo es el puerto HTTPS externo de Caddy usado por Pelican y el navegador. La opción de estar detrás de un proxy debe estar habilitada.

En el panel, el nodo debe usar el FQDN gratuito, HTTPS, puerto `8443` y la opción de estar detrás de un proxy. En `/etc/pelican/config.yml`, conserva el UUID, token y resto de la configuración generada, pero ajusta estos campos locales:

```yaml
ignore_panel_config_updates: true
api:
  host: 127.0.0.1
  port: 8080
  ssl:
    enabled: false
```

No reemplaces todo el YAML por ese fragmento: combina únicamente esos campos con el archivo generado. El ajuste impide que una actualización del panel reemplace el puerto interno por el externo; los cambios posteriores de configuración deberán revisarse en el archivo local. Guarda el archivo con permisos `600`, reinicia Wings y comprueba consola y archivos desde Pelican antes de habilitar el monitor. [Configuración oficial de Wings](https://pelican.dev/docs/wings/optional-config/).

Después de crear y probar el servidor, encuentra su contenedor sin imprimir secretos:

```bash
sudo docker ps -a --format '{{.Names}}  {{.Status}}'
sudoedit /etc/fogata/agent.env
```

Establece `CONTAINER_NAME` al nombre exacto que administra Wings para ese servidor. `SERVER_DIR` puede registrar la ruta real de su volumen (habitualmente `/var/lib/pelican/volumes/<UUID>`), pero no reemplaza el nombre del contenedor: el agente actual inspecciona y detiene por `CONTAINER_NAME`. Ajusta `MC_HOST`/`MC_PORT` a la asignación alcanzable desde el host. Conserva `API_BASE_URL`, `HEARTBEAT_SECRET`, `PANEL_HOSTNAME` y `PANEL_HEALTH_URL` generados; no los pegues en un chat o issue.

```bash
sudo chmod 600 /etc/fogata/agent.env
sudo systemctl restart fogata-agent
sudo journalctl -u fogata-agent -n 30 --no-pager
```

El agente solicita a la API local de Wings arrancar ese servidor una vez al iniciarse y consulta el estado público del protocolo Minecraft para contar jugadores. Un contenedor que falla durante la sesión se investiga en Pelican; no se reinicia en bucle desde Fogata. Para cerrar, pide a Wings la acción `stop` y comprueba posteriormente que el contenedor haya terminado. La aceptación HTTP 202 de Wings no significa que el mundo ya esté guardado.

El helper `/opt/fogata/wings.py` lee el token existente de `/etc/pelican/config.yml`, con el parser seguro del paquete Ubuntu `python3-yaml`, y lo envía únicamente a `127.0.0.1:8080`. No se necesita otra clave de API en el portal. Las operaciones de energía pasan por Wings para respetar su detección de cierre intencional: detener el contenedor directamente puede disparar su reinicio por detección de crash. [Contrato del servidor](https://github.com/pelican/wings/blob/main/router/router_server.go), [configuración de crash detection](https://pelican.dev/docs/wings/optional-config/).

La supervisión aplica un plazo de arranque de 15 minutos (`BOOT_TIMEOUT_MINUTES`, configuración de la Function). Para una instalación inicial larga, prepara los pasos antes de encender y ajusta temporalmente ese plazo con un límite razonable de horas. No desactives todos los controles para terminar la configuración. Restablece los valores de operación después de verificar el primer inicio.

Documentación oficial que prevalece para cada versión: [instalación del panel](https://pelican.dev/docs/panel/getting-started/), [configuración](https://pelican.dev/docs/panel/panel-setup/), [Wings](https://pelican.dev/docs/wings/install/). No ejecutes instaladores de terceros que prometan automatizarlo todo sin revisar sus cambios.

## Acceso al panel

El portal estático tiene HTTPS. La IP pública de la VM recibe un nombre gratuito de Azure, por ejemplo `<etiqueta>.centralus.cloudapp.azure.com`. Caddy usa ese nombre para obtener y renovar el certificado. No hace falta comprar dominio ni configurar un DNS externo. Los puertos 80/443 deben permitir la validación del certificado y el panel HTTPS; no introduzcas credenciales si el navegador indica un problema de certificado.

Durante la instalación inicial Caddy restringe el panel a `AdminCidr`: solo esa IP puede crear la cuenta del propietario. Después de completar y probar el instalador, el administrador puede habilitar el panel público mediante el helper de la VM:

```bash
sudo fogata-open-panel --confirm-setup-complete
```

Este paso debe cerrar permanentemente la ruta del instalador antes de abrir el acceso público. No retires la restricción manualmente para que otra persona termine la instalación: alguien ajeno podría reclamar el panel.

La URL del panel es `https://<nombre-Azure>`. Wings se publica como `https://<nombre-Azure>:8443`, con proxy al servicio local `127.0.0.1:8080`. El nodo de Pelican debe usar ese hostname, puerto externo y esquema HTTPS. Abrir el panel no comprueba automáticamente consola y gestor de archivos: prueba ambas funciones desde el navegador.

Como panel y Wings comparten VM, el instalador resuelve ese hostname a `127.0.0.1` dentro del propio Linux, mediante una entrada marcada `fogata-panel-loopback` en `/etc/hosts`. Los visitantes siguen usando el DNS público de Azure. Esto conserva TLS y evita depender de la ruta hacia la propia IP pública durante un arranque en frío.

El helper opcional `vm/setup-demo.php` permite a un asistente preparar una instalación nueva usando los servicios de la versión instalada de Pelican. Recibe los datos por stdin, no por argumentos. Su cuenta de demostración es `admin`, con correo de marcador `admin@fogata.invalid`; no configura envío de correo. Guarda la contraseña generada en un gestor y sustituye el correo cuando configures correo real. Para una instalación que ya contiene datos, conserva el procedimiento manual y revisa la compatibilidad antes de usar el helper.

SSH se mantiene restringido al CIDR del administrador y usa clave pública. La contraseña compartida del portal autoriza consultar, encender y solicitar el apagado completo; Pelican tiene su propio acceso. Comparte el portal solo con personas de confianza: también pueden cerrar una partida. Para jugar basta con el portal y `IP:25565`; no necesitan la cuenta administradora de Pelican. Si compartes el panel, crea permisos adecuados en Pelican y no reutilices la contraseña del portal.

## Prueba de aceptación

- Con la VM desasignada, el portal debe cargar. Consultar estado, introducir contraseña o jugar al minijuego no debe arrancarla.
- Un clic en Encender solicita una sola operación. Repetirlo o abrir otra pestaña no duplica el servidor.
- La barra cambia por señales reales. Un error de Azure o de Paper se muestra como error, no como avance hasta 100 %.
- El estado listo solo aparece cuando funcionan Minecraft y Pelican. La redirección se puede cancelar y hay enlace manual.
- Un cliente Minecraft real entra usando la IP pública y se verifica un cambio del mundo.
- Al salir todos, se cuenta el período de inactividad. Si alguien vuelve antes de cerrar, el apagado debe cancelarse cuando sea seguro hacerlo.
- Tras cerrar y desasignar, el mundo conserva el cambio anterior. El estado Azure debe ser `VM deallocated`.
- La contraseña incorrecta no permite leer información privada ni encender; la petición directa a la API tampoco debe saltarse la autenticación.
- Los límites de horas, arranque fallido y heartbeat perdido se prueban en una copia de desarrollo con límites pequeños antes de confiar en ellos.

## Uso diario

Si hay más de un servidor registrado, elige en Fogata cuál iniciar antes de encender la VM. Para cambiar, espera a que Guardar y apagar termine y vuelva a Apagado. El [procedimiento de modpacks](MODPACKS.md) explica el catálogo, el bloqueo compartido y cómo importar otro paquete.

Abre el portal, introduce la contraseña y pulsa Encender. Puedes cerrar la pestaña; el controlador continúa supervisando. El servidor se apaga cuando corresponde aunque ya nadie tenga la web abierta. El límite de sesión de ocho horas y el mensual también se aplican si todavía hay jugadores. La contraseña compartida da acceso al encendido; no debe coincidir con la contraseña administradora de Pelican.

Para terminar antes, usa **Guardar y apagar** en Fogata y confirma. El aviso indica los jugadores del último estado consultado; otros pueden entrar después. La orden cierra la partida aunque haya jugadores. El agente pide el cierre a Wings, espera que termine Minecraft y confirma al controlador antes de desasignar la VM. El portal muestra Apagando hasta que Azure confirme la desasignación. Repetir la orden no reinicia el plazo. Si el agente falla, sigue aplicando el plazo de emergencia documentado en [ARQUITECTURA.md](ARQUITECTURA.md); no se garantiza el guardado en ese caso.

Detener Minecraft desde Pelican no equivale a desasignar la VM. Todavía no existe un modo mantenimiento: el controlador puede considerar el juego detenido como un fallo una vez superado el plazo de arranque y apagar la VM. No cuentes con mantenerla encendida indefinidamente para editar archivos.

**Juegos de la fogata** comienza cerrado y se abre como acordeón. Incluye chispas, una ronda de clics por segundo de 15 segundos y un juego de saltos. Funciona también con el servidor encendido o apagado y sin iniciar sesión. Abrirlo cancela la redirección automática a Pelican. Cerrar el acordeón o pasar la página a segundo plano termina las rondas locales; los juegos no consultan Azure ni encienden la VM. La animación de la fogata respeta la preferencia de movimiento reducido.

Realiza cambios de plugins y mundos con el servidor detenido ordenadamente, pero manteniendo la VM encendida. Conserva un backup probado antes de actualizar Paper, Java o el panel.

## Retirar una instalación

Primero descarga y prueba un backup de los datos que quieras conservar. Eliminar el resource group borra también discos y almacenamiento del proyecto.

```powershell
.\scripts\Remove.ps1 -SubscriptionId '<TU_ID>' -Name fogata -ConfirmName fogata
```

Revisa sus comprobaciones de nombre, etiquetas y contenido. No uses este procedimiento para eliminar recursos ajenos al proyecto. Desasignar la VM ahorra cómputo, pero no elimina cargos de discos, IP y almacenamiento.
