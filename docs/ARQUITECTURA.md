# Arquitectura y decisiones

Fogata mantiene la web y su API disponibles, y desasigna la VM más costosa mientras no se juega. Azure Storage sirve el frontend HTTPS. Azure Functions administra el ciclo de vida con identidad administrada. La VM aloja Pelican, Wings y el contenedor del juego, con datos en disco persistente y dirección IPv4 estática.

## Separación de responsabilidades

| Componente | Responsabilidad |
|---|---|
| Portal | Contraseña compartida, encender, consultar estado, minijuego local, redirección |
| API | Autenticar, coordinar solicitudes, aplicar límites y ejecutar operaciones Azure |
| Blob de control | Estado compartido y bloqueo para evitar arranques concurrentes |
| Monitor de la VM | Estado real de Minecraft, jugadores y cierre ordenado |
| Pelican y Wings | Consola, archivos y contenedor Minecraft |
| Timer de la Function | Supervisar arranque, inactividad y límites aunque se cierre el navegador |

El navegador no tiene permisos de Azure. La contraseña del portal no es una credencial Azure. El heartbeat de la VM utiliza un secreto distinto. No se deben incluir secretos en URLs o parámetros de consulta.

El panel se apaga con la VM: no puede ser el único lugar donde viva el botón de arranque. El portal enlaza a Pelican después de comprobar disponibilidad. Azure proporciona un nombre gratuito para la IP pública. Caddy termina HTTPS para el panel en 443 y Wings en 8443; Wings atiende localmente en 8080. Inicialmente el panel se restringe a la IP administrativa; solo se abre después de completar el instalador y bloquear permanentemente su ruta. El panel y Wings públicos conservan la autenticación propia de Pelican. SSH permanece restringido al CIDR del administrador; no se deben transmitir credenciales por HTTP en Internet.

## Interfaz del portal

Las peticiones autenticadas envían `X-Portal-Password` por HTTPS. La API devuelve JSON y no almacena credenciales en el frontend versionado.

| Método y ruta | Uso |
|---|---|
| `GET /api/status` | Estado sin encender el servidor |
| `POST /api/start` | Solicitud explícita e idempotente de encendido |
| `POST /api/heartbeat` | Reporte interno del monitor, autenticación separada |

Contrato esperado por el frontend:

```json
{
  "phase": "loading",
  "players": 0,
  "usedHours": 12.5,
  "maxHours": 180,
  "minecraftAddress": "IP:25565",
  "panelUrl": "URL_DEL_PANEL",
  "message": "Minecraft está cargando",
  "updatedAt": 1794052800
}
```

Fases: `off`, `starting`, `booting`, `loading`, `ready`, `stopping`, `blocked`, `error`. `updatedAt` es Unix epoch en segundos. `ready` no se deduce de un cronómetro. Códigos habituales: `401` contraseña incorrecta, `409` operación incompatible en curso, `429` límite alcanzado. La UI puede reintentar consultas con pausa; no debe repetir automáticamente un encendido tras un fallo desconocido.

## Apagado y límites

El apagado exige guardar el mundo y cerrar el proceso antes de desasignar. Para el ahorro importa `Deallocated`; un contenedor parado o `shutdown` dentro de Linux no garantizan que Azure deje de cobrar cómputo. El almacenamiento y la IP siguen costando. [Estados Azure](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing).

Las horas miden VM, no jugadores. El temporizador de control no depende de que haya una pestaña abierta. El período mensual del controlador es el mes UTC, que puede no coincidir con el ciclo de crédito de la oferta. La pérdida del heartbeat se trata como fallo de supervisión, no como evidencia de cero jugadores. Una parada solicitada solo por inactividad puede cancelarse si entra alguien y el cierre aún no empezó. Los límites de sesión y presupuesto pueden detener una partida con jugadores. Tras solicitar un cierre, el controlador espera confirmación del agente; si no llega, usa un plazo de emergencia (por defecto cinco minutos) antes de desasignar para contener gasto. Esto puede perder cambios sin guardar. Los límites son defensa operativa y requieren observar fallos; no representan una garantía financiera ni sustituyen backups.

El primer arranque debe probarse en la región y con el mundo real. El objetivo de dos a cinco minutos no es un SLA. Precargar imágenes y dependencias reduce las descargas en cada sesión.
