# Instrucciones para agentes que trabajen en Fogata

Lee primero README.md y docs/OPERACION.md. Este proyecto es un portal estático y un controlador de una VM Azure bajo demanda; Pelican se ejecuta dentro de la VM que se desasigna.

## Trabajo local

- Conserva un repositorio portátil: no introduzcas ID de suscripción/tenant personales, claves, contraseñas, mundos o logs de jugadores en archivos versionados.
- Los secretos se solicitan por entrada oculta local y se guardan fuera de Git. No pidas al usuario pegarlos en el chat ni los imprimas en una salida.
- No instales Docker Desktop o WSL como requisito si solo se despliega en Azure.
- Para la web usa la configuración demo claramente etiquetada; no presentes un arranque simulado como verificación de Azure.
- Ejecuta `python -m unittest discover -s tests -v` tras cambiar la lógica de control. Verifica también sintaxis de PowerShell/Bicep y los cambios de UI adecuados al alcance.

## Azure

- Todas las operaciones usan el `SubscriptionId` que el propietario haya identificado explícitamente. No uses la suscripción predeterminada como destino y no ejecutes `az account set` para corregirla.
- Comienza por `scripts/Preflight.ps1`. Revisa el plan de `scripts/Deploy.ps1` sin `-Apply` antes de aplicar. Si el usuario ya autorizó el despliegue de ese plan, no inventes otra ronda de permiso.
- No uses una suscripción de producción como alternativa ante errores de cuota o permisos. Informa el recurso y la limitación concreta, y sigue con el trabajo local que no dependa de ella.
- No aceptes la EULA de Minecraft en nombre del usuario. `-AcceptMinecraftEula` representa su aceptación explícita; no añadas el switch por conveniencia.
- Un error al listar o asignar roles no se soluciona concediendo Owner global. El controlador solo necesita leer/iniciar/desasignar su VM; no debe poder cambiar RBAC.
- Un fallo de instalación no autoriza borrar un resource group ajeno. Usa el procedimiento dedicado con nombre y etiquetas del proyecto, tras revisar su contenido.
- No afirmes que US$50 sean un techo garantizado ni que el beneficio de Visual Studio admita cualquier uso. Explica el tipo de oferta, controles reales y cargos persistentes.

## Antes de declarar que funciona

Comprueba credenciales y suscripción sin mostrarlas, despliegue de Function/portal, configuración final de Pelican/Wings y una prueba real de encendido y apagado ordenado con mundo guardado. Verifica que consultas de estado o visitas al portal no enciendan la VM. El modo listo requiere juego y panel saludables, no solo VM encendida.

Si faltan región, CIDR de administración, clave pública, suscripción o aceptación de EULA, pregunta solo por lo que no pueda determinarse con fuentes autorizadas. Continúa con cambios y comprobaciones independientes mientras tanto.
