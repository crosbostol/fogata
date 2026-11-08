# Fogata · Minecraft en Azure bajo demanda

Una URL, una contraseña compartida y un botón para encender tu servidor. Mientras arranca, el portal muestra etapas verificadas y un minijuego local; cuando Minecraft y Pelican están listos, ofrece redirigir al panel. Sin una VM de entrada permanente, sin dominio comprado y sin Docker instalado en el PC del administrador.

Cada persona despliega su propia copia y paga su consumo de Azure. Este repositorio no distribuye Minecraft ni reemplaza sus licencias.

## Qué se despliega

```text
Navegador → portal estático HTTPS en Azure Storage
                 ↓ contraseña compartida por HTTPS
            Azure Function (Flex Consumption)
                 ↓ identidad administrada, permisos sobre una VM
            VM Ubuntu: Pelican + Wings + Docker + Paper
                 ↑ heartbeat de estado y jugadores
```

La VM conserva IP y disco cuando se desasigna. El portal continúa accesible. Pelican, consola y archivos están disponibles mientras la VM está encendida. El acceso a Minecraft es directo a `IP:25565`; la web no retransmite las partidas. El panel usa un nombre gratuito de Azure (`<nombre>.<region>.cloudapp.azure.com`) con HTTPS; no hace falta comprar un dominio.

**La primera instalación de Pelican requiere terminar su configuración y crear el servidor en su panel.** El despliegue de infraestructura no implica que ya exista un mundo listo. Revisa [la puesta en marcha](docs/OPERACION.md) y el estado real de las comprobaciones antes de compartir la URL.

## Antes de gastar crédito de Visual Studio

Microsoft limita ese beneficio a uso individual de desarrollo y pruebas; no autoriza automáticamente hospedar un servicio habitual de juegos por ser privado o gratuito. Confirma que tu uso y las reglas de tu organización encajan. Para un servidor de juego operativo, utiliza una oferta de Azure que permita ese uso. No se combinan los créditos de varios compañeros. [Condiciones y preguntas oficiales](https://learn.microsoft.com/en-us/visualstudio/subscriptions/faq/subscriber/azure/), [guía de licenciamiento](https://www.microsoft.com/licensing/guidance/Visual-Studio).

El monto, las cuotas y las regiones disponibles dependen de cada suscripción. No cambies ni elimines su spending limit como parte de estas instrucciones. Los scripts requieren el ID de destino y pasan `--subscription` explícitamente; no dependen de la suscripción predeterminada del terminal.

## Requisitos del administrador

- Azure CLI y PowerShell; Git para obtener el repositorio.
- Python 3.11 o posterior para las comprobaciones locales.
- OpenSSH y un par de claves SSH. Comparte únicamente la clave pública `.pub`.
- Suscripción Azure habilitada para los recursos y la región elegida. Crear roles requiere permisos para asignar roles, además de crear recursos.
- IP pública del administrador en formato CIDR, por ejemplo `203.0.113.10/32`.

Docker, PHP, Composer y Java de producción se instalan en Linux en Azure. Docker Desktop y WSL son opcionales para este proyecto. La CLI puede descargar Bicep durante la validación; no requiere instalar Terraform.

## Elegir región

La primera opción de esta copia es **Central US (`centralus`, Iowa)**, priorizando costo. **Brazil South (`brazilsouth`, estado de São Paulo)** queda como alternativa si la diferencia real de latencia justifica el mayor gasto. Central US y South Central US son regiones distintas; no intercambies sus nombres al copiar comandos. [Lista oficial de regiones](https://learn.microsoft.com/en-us/azure/reliability/regions-list).

La región más cercana en el mapa no garantiza el mejor recorrido desde cada proveedor de Internet. Todavía no hay mediciones de ping de este despliegue. Después de provisionar, prueba la conexión al puerto Minecraft desde las redes reales de los jugadores; un ping ICMP aislado no confirma por sí solo el comportamiento de una partida. Si la experiencia es aceptable, evita migrar solo por una diferencia pequeña.

Mantén VM, almacenamiento y controlador juntos en la región elegida. Un cambio de región no mueve automáticamente el mundo ni conserva la IP: requiere respaldar, desplegar otra instalación, restaurar y retirar la anterior cuando esté verificada.

## Desplegar tu copia

Desde la raíz del repositorio, en PowerShell:

```powershell
az login
# Alternativa si el navegador de inicio de sesión no funciona:
# az login --use-device-code

az account list --query "[].{Nombre:name,Id:id,Estado:state}" --output table
$subscriptionId = '<ID de TU suscripción autorizada>'
az account show --subscription $subscriptionId --query '{Nombre:name,Id:id,Estado:state}' --output table
```

No pegues contraseñas, tokens, códigos de Authenticator ni claves privadas en el chat con una IA. Para organizaciones con varias cuentas, puedes iniciar sesión indicando `az login --tenant '<tenant autorizado>'`.

Si todavía no tienes clave SSH:

```powershell
ssh-keygen -t ed25519
```

Primero comprueba suscripción, región y cuotas. Este paso no crea recursos:

```powershell
.\scripts\Preflight.ps1 -SubscriptionId $subscriptionId -Location centralus -VmSize Standard_D2as_v7
```

Prepara parámetros. Cambia `AdminCidr` por tu IP pública real; el ejemplo usa una dirección de documentación que no permite acceso desde tu equipo:

```powershell
$deployment = @{
    SubscriptionId = $subscriptionId
    Location = 'centralus'
    VmSize = 'Standard_D2as_v7'
    Name = 'fogata'
    AdminCidr = '203.0.113.10/32'
    SshPublicKeyPath = "$env:USERPROFILE\.ssh\id_ed25519.pub"
    MonthlyHours = 180
}
.\scripts\Deploy.ps1 @deployment
```

Sin `-Apply`, se muestra el plan de infraestructura. Comprueba el ID de suscripción, nombre, región, tamaño y recursos. Si es la copia que quieres crear:

```powershell
.\scripts\Deploy.ps1 @deployment -Apply -AcceptMinecraftEula
```

El último switch solo debe pasarlo la persona que haya leído y acepte la [EULA de Minecraft](https://www.minecraft.net/eula). Una IA no debe aceptarla por ella. El script pide una contraseña compartida de al menos 16 caracteres. Los secretos no se incluyen en el repositorio; conserva tu contraseña en un gestor de contraseñas.

Para una instalación asistida sin pegar contraseñas en el chat, puedes añadir `-GeneratePortalPassword`: genera una contraseña aleatoria y la guarda en `.local/private/portal-password.txt`, en una carpeta restringida al usuario local. Esa carpeta está excluida de Git. Abre el archivo localmente y guarda el valor en tu gestor; no lo adjuntes a incidencias. El valor no se imprime en los logs. Repetir ese modo al reaplicar cambia la contraseña.

Por defecto los scripts esperan una suscripción cuyo nombre identifique el beneficio de Visual Studio. Para otra suscripción que tú hayas revisado y autorizado, añade `AllowOtherSubscription = $true` al bloque de parámetros; esto no concede permisos ni valida términos de uso.

Preflight comprueba el SKU exacto, su familia/vCPU, restricciones y cuotas disponibles. Una cuota ausente, una restricción o un proveedor sin registrar no cuentan como validación exitosa. No se registra automáticamente un proveedor ni se cambia de suscripción para avanzar. Si eliges otro `VmSize`, vuelve a ejecutar Preflight y recalcula costos antes de aplicar: la tabla de abajo y sus horas orientativas solo corresponden a `Standard_D2as_v7`.

En la suscripción de prueba, D2as_v5 apareció restringida y D2as_v7 sin restricciones, con cuota de su familia disponible en Central US. Por eso la base usa v7. Esto no garantiza capacidad en el momento del despliegue ni que otra suscripción tenga las mismas condiciones: ejecuta Preflight en tu cuenta.

El despliegue deja datos de conexión sin secretos en `.local/deployment.json`. Después debes completar [Pelican y el servidor](docs/OPERACION.md). El portal debe quedar en modo real apuntando a la Function; el modo demo local no enciende recursos.

Para reaplicar cambios sobre una instalación existente, primero guarda y cierra el juego y espera la desasignación normal. El script rechaza actualizar una VM todavía asignada para evitar cortar una partida. Reutiliza el mismo nombre y región; cambiar el nombre puede crear otra instalación con nuevos cargos.

## Compartirlo con ayuda de cualquier IA

### Despliegue local y CI/CD

El despliegue documentado se ejecuta desde la consola del administrador con `az login`. No requiere GitHub Actions, una aplicación de Entra ni secretos Azure en GitHub. Puedes usar GitHub solo para versionar y compartir este código. El workflow incluido ejecuta comprobaciones locales: no publica ni crea recursos Azure.

Para añadir despliegue automatizado más adelante, se puede configurar GitHub Actions con OpenID Connect y una identidad con permisos limitados al proyecto. Necesita una credencial federada y asignaciones de roles; los permisos para crear una VM con tu cuenta no implican permisos para crear aplicaciones en Entra o configurar esa identidad. Un fallo anterior de CI/CD no demuestra que la oferta Visual Studio prohíba todo despliegue automatizado. Revisa el error concreto y las políticas del tenant antes de cambiar permisos. [Guía oficial de Azure y GitHub OIDC](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect).

Puedes entregar el repositorio a Copilot u otro agente y usar este encargo:

> Lee README.md, AGENTS.md y docs/OPERACION.md. Ayúdame a desplegar mi propia copia de Fogata. Primero identifica las herramientas que faltan y comprueba la suscripción explícita que yo indique. Ejecuta las comprobaciones y muéstrame el plan antes de crear recursos. Pídeme solo los datos necesarios que no estén disponibles. No uses producción, no aceptes la EULA por mí y no me pidas secretos en el chat. Explícame cualquier paso de Pelican que deba completar yo. No declares éxito sin verificar un encendido, entrada y apagado con guardado.

Cada persona usa sus propios ID, claves, contraseña y crédito. No debe editar los scripts para poner tus datos personales ni copiar `.local/` de otro equipo.

## Prueba local sin Azure

```powershell
python -m http.server 8080 --directory web
```

Abre `http://localhost:8080`. La configuración de ejemplo está marcada como demostración y simula el arranque. No usa la cuenta Azure ni reproduce las credenciales reales. Para probar la lógica del controlador:

```powershell
python -m unittest discover -s tests -v
```

La validación inicial tiene 47 pruebas locales aprobadas; todavía no hay una prueba completa de extremo a extremo en Azure. Las pruebas locales no sustituyen una prueba de integración de Azure y un cliente Minecraft real. La Function necesita las dependencias de `api/requirements.txt` para ejecutarse en su host; los tests del núcleo pueden ejecutarse sin credenciales.

## Costos y controles

Referencia retail consultada el 7 de noviembre de 2026 para Linux D2as_v7 (2 vCPU / 8 GiB), SSD Standard LRS de 64 GiB y una IPv4 Standard:

| Concepto | Central US | Brazil South |
|---|---:|---:|
| Disco e IP persistentes, convención 730 h/mes | US$8,45/mes | US$12,61/mes |
| VM por hora encendida | US$0,0908 | US$0,146 |
| Total con 60 h/mes de VM | US$13,90 | US$21,37 |
| Total con 120 h/mes de VM | US$19,35 | US$30,13 |
| Total con 180 h/mes de VM | US$24,79 | US$38,89 |

Faltan API, almacenamiento asociado, operaciones de disco, backups, salida de red cobrable e impuestos. Los precios pueden cambiar y no son una cotización de la suscripción. Verifica [Azure Retail Prices](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) y [transferencia](https://azure.microsoft.com/en-us/pricing/details/bandwidth/).

La tarifa publicada de salida a Internet por la red Microsoft incluye los primeros 100 GB mensuales gratuitos; no son 100 GB nuevos por VM. En el primer tramo cobrable, la referencia es US$0,087/GB desde Norteamérica y US$0,181/GB desde Sudamérica. La entrada es gratuita. Comprueba el ámbito de facturación y si otros recursos consumen esa franquicia; el tráfico puede alterar la comparación de regiones.

Con US$50, dejando US$5 estimados para extras, caben aproximadamente 402,5 h/mes en Central US o 221,8 h/mes en Brasil. Son 13,4 o 7,4 horas por día en un mes de 30 días. Un promedio inicial de 12 o 7 h/día deja más margen incluso en meses de 31 días. Las horas incluyen arranque y espera por inactividad; los jugadores simultáneos no multiplican esas horas, pero pueden exigir más recursos o tráfico.

A 60 horas mensuales, Brasil añade unos US$7,47 frente a Central US; a 180 horas, unos US$14,10, antes de extras. Empieza en Central US y compara una partida real; solo considera Brasil si la mejora observada te compensa ese gasto.

El controlador limita por defecto a 180 h/mes (unas seis horas diarias en un mes de 30 días), sesiones de 8 horas y 15 minutos sin jugadores. Para el tamaño base, el despliegue admite inicialmente hasta 390 h/mes en Central US y 220 en Brasil; esos límites conservan margen estimado y no equivalen a gastar exactamente US$50. El límite de sesión o de horas puede cerrar una partida aunque queden jugadores; ajusta esos valores antes de compartirlo. Son controles operativos, no un límite de facturación garantizado. Una interrupción de Azure, del monitor o del controlador puede retrasar el apagado. Los budgets de Azure notifican y sus datos llegan con retraso; no paran la VM por sí solos. [Documentación de budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).

## Operación, seguridad y recuperación

El registro de pruebas de la primera implementación está en [VALIDACION.md](docs/VALIDACION.md): incluye encendido y apagado reales, tiempo medido, latencia y límites de lo comprobado.

Para medir latencia cuando exista un servidor autorizado y encendido, ejecuta desde la conexión de un jugador:

```powershell
python scripts/Measure-Latency.py HOST_O_IP:25565 --samples 5
```

Mide el intercambio ping/pong del protocolo Minecraft Java y muestra mediana, mínimo y máximo. No crea recursos ni inicia sesión de jugador. Si ya hay servidores en ambas regiones, puedes pasar dos direcciones y compararlas desde la misma red y horario. No despliegues dos copias permanentes solo para medir. Esta medición no mide TPS del servidor ni sustituye una partida real; repetir desde los proveedores de Internet de los jugadores ayuda a detectar rutas distintas.

- [Puesta en marcha de Pelican y operación diaria](docs/OPERACION.md).
- [Arquitectura y contrato de la API](docs/ARQUITECTURA.md).
- [Migrar un servidor existente y hacer backups](docs/MIGRACION.md).
- [Problemas frecuentes](docs/PROBLEMAS.md).

No se debe subir a Git el mundo, logs de jugadores, credenciales, claves, archivos `.env`, paquetes de despliegue con secretos ni el contenido de `.local/`. Pelican es un proyecto independiente: [código y licencia](https://github.com/pelican/panel). El agente intenta cerrar el contenedor ordenadamente; si deja de responder, el controlador puede desasignar tras el plazo de emergencia aunque no haya confirmación de guardado. Mantén backups probados.
