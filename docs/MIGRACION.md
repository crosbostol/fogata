# Migrar un mundo y recuperarlo

Este repositorio no incluye mundos, listas de jugadores ni configuraciones privadas. Cada propietario decide qué servidor migrar y conserva una copia fuera de la VM.

## Preparar el respaldo

1. Anota versión exacta de Paper/Minecraft, Java y plugins.
2. Guarda el mundo y detén el proceso de Minecraft de forma ordenada.
3. Copia mundo(s), plugins y sus datos, configuraciones, whitelist y permisos. Incluye el inventario de versiones. No publiques estos archivos en el repositorio.
4. Verifica tamaño e integridad del archivo y conserva otra copia fuera de Azure o fuera del resource group del servidor.

Una copia de archivos mientras el juego escribe no es automáticamente consistente. Para un snapshot, coordina guardado/cierre o usa un mecanismo de backup de la aplicación cuya restauración hayas probado.

## Importar en Pelican

Crea primero un servidor compatible y deténlo. Usa el gestor de archivos o SFTP de Wings para transferir la copia al volumen de ese servidor, preservando propietarios/permisos Linux. Ajusta el archivo de inicio y las variables del egg en vez de copiar un `.bat` de Windows. No incluyas los binarios o cachés locales sin necesitarlos.

Mantén inicialmente la misma versión del juego y de plugins; migra y actualiza en pasos distintos. Verifica mundos secundarios y nombres de carpetas. Comprueba que el disco tenga espacio suficiente para importación, descompresión y backups.

Si el servidor anterior usa `online-mode=false`, cambiarlo a autenticación oficial puede cambiar los UUID y dejar inventarios/permisos asociados a identidades distintas. Respalda y prepara una migración explícita antes de modificarlo. La contraseña del portal solo protege el encendido y no autentica a quienes entran al juego.

## Validar y restaurar

Entra con un cliente real y comprueba posición, inventario, dimensiones, permisos y plugins. Guarda un cambio reconocible, cierra ordenadamente, vuelve a encender y verifica que persiste. Una restauración de prueba en una copia separada es la evidencia útil de que el backup sirve.

El disco persistente protege frente al apagado normal; no es un backup frente a borrado, corrupción o un cambio de versión incompatible. Define retención y tamaño antes de automatizar copias: ambos tienen costo.
