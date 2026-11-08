# Problemas frecuentes

| Síntoma | Qué revisar |
|---|---|
| `az` no existe | Instala Azure CLI o usa su ruta instalada; abre un terminal nuevo. No se necesita Docker local |
| CLI muestra otras suscripciones | Comprueba cuenta/tenant y el ID explícito. No selecciones producción para avanzar |
| CLI no puede escribir su log/cache | Revisa permisos de su carpeta de configuración. Un sandbox de IA puede restringirla; no copies tokens al repositorio |
| Región o tamaño no disponibles | Cuotas y restricciones de tu oferta; prueba una región autorizada y vuelve a cotizar |
| Fallo de asignación de rol | El operador necesita permisos RBAC para el rol limitado a la VM, no acceso global del controlador |
| Web siempre dice demostración | Se está sirviendo la configuración local; no valida Azure. Comprueba el `config.js` desplegado |
| Web da error de CORS | La Function debe admitir el origen HTTPS exacto del portal, sin barras/rutas adicionales |
| Contraseña rechazada | Comprueba que se configuró el hash de la contraseña correcta. No imprimas ni pegues el secreto para depurar |
| VM encendida pero Minecraft no listo | Instalación final de Pelican, estado Wings, contenedor, EULA, Java y logs de Paper |
| VM lista pero Pelican no abre | Hostname gratuito Azure, certificado/Caddy, puertos 80/443, servicio web y disponibilidad del panel |
| Consola o archivos no conectan | URL/puerto/esquema de Wings desde el navegador; abrir el panel no comprueba esta ruta |
| Servidor no se apaga | Monitor/heartbeat, jugadores reales, timer de Function, permisos ARM y logs del controlador |
| VM está `Stopped` y sigue cobrando | Debe estar `Deallocated`; además discos/IP siguen facturando |
| Cuota mensual alcanzada | Revisa horas y período del controlador. No borres el estado para evadir el límite sin analizar los costos |

Para pedir ayuda, incluye versión del repositorio, etapa que falla, comando con secretos retirados y mensaje de error completo. No adjuntes tokens, archivos `.env`, claves, el perfil de Azure CLI, mundo o datos personales de jugadores. Los archivos `.local/` tampoco deben publicarse en una issue.

Ante un arranque fallido, revisa primero la causa. Repetir despliegues puede crear más recursos si cambias nombres; usa los mismos parámetros para reparar la instalación existente. El controlador debe informar estados de error; una barra que sigue animándose no prueba progreso.

## Cuota cero del plan clásico Y1

Si Azure devuelve `SubscriptionIsOverQuotaForSku` con `Current Limit (Y1 VMs): 0`, la VM Minecraft puede tener cuota suficiente y aun así fallar el controlador. La plantilla usa Flex Consumption (FC1), sin instancias always-ready ni Azure Files. Comprueba disponibilidad regional y cuota propia de Flex; no cambies a un plan dedicado con costo fijo como solución automática. El paquete se publica mediante Azure CLI con remote build, compatible con Flex.
