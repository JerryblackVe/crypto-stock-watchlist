# Aplicación de Lista de Seguimiento de Activos

Esta aplicación web permite crear y gestionar una lista de seguimiento de
activos (criptomonedas y acciones de EE. UU.) directamente desde un
navegador. El usuario puede agregar o eliminar activos, configurar
alertas de precio y visualizar gráficas de velas japonesas sin tener
conocimientos de programación.  La aplicación está pensada para
ejecutarse de forma gratuita mediante GitHub Pages para la interfaz y
GitHub Actions para las actualizaciones automáticas de precios.

## Características principales

* **Lista de seguimiento personalizable**: agregue tantos activos como
  desee especificando su símbolo (por ejemplo `AAPL` o `BTC-USD`), un
  nombre opcional y niveles de alerta superior e inferior.
* **Precios en tiempo casi real**: un flujo de trabajo de GitHub
  Actions se ejecuta cada 10 minutos, consulta los precios más
  recientes de Yahoo Finance y actualiza la lista de seguimiento.
* **Alertas por correo electrónico**: se envían mensajes cuando el
  precio de un activo supera o cae por debajo de los niveles
  configurados. Puede especificar un correo de alerta global en la
  configuración o un correo específico por activo.
* **Gráficas de velas japonesas**: al seleccionar un activo puede
  visualizar una gráfica interactiva con datos históricos en intervalos
  de 4 horas, 1 día o 1 semana.  Los datos se generan en el flujo de
  trabajo y se sirven a través de GitHub.
* **Modo claro/oscuro**: cambie la apariencia con el interruptor
  ubicado en la esquina superior derecha.
* **Interfaz fácil de usar**: la aplicación se ejecuta en cualquier
  navegador moderno; las operaciones se realizan mediante formularios y
  no requieren conocimientos de programación.

## Estructura del repositorio

```
crypto_stock_watchlist/
├── .github/workflows/update_prices.yml   # Flujo de trabajo de GitHub Actions
├── scripts/update_prices.py              # Script de actualización de precios y alertas
├── watchlist.json                        # Lista de activos a seguir (modificada por la app)
├── alerts_log.json                       # Registro interno de alertas enviadas
├── historical_*.json                     # Archivos generados con datos históricos para cada activo
├── index.html                            # Interfaz web (GitHub Pages)
├── app.js                                # Lógica de la interfaz web
├── style.css                             # Estilos y temas
└── README.md                             # Este documento
```

## Configuración inicial

1. **Crear un repositorio**: cree un nuevo repositorio en GitHub (por
   ejemplo, `crypto_stock_watchlist`) y suba todos los archivos de esta
   solución.  Puede hacerlo clonando este repositorio localmente o
   utilizando la interfaz web para subir los archivos.

2. **Habilitar GitHub Pages**: en la pestaña **Settings > Pages** de su
   repositorio, seleccione la rama `main` y la raíz (`/`) como origen.
   Guarde los cambios.  Esto publicará la aplicación en
   `https://<su_usuario>.github.io/<nombre_del_repositorio>/`.

3. **Configurar secretos para el envío de correos**:

   - Vaya a **Settings > Secrets and variables > Actions** en su
     repositorio.
   - Cree un secreto llamado `SMTP_EMAIL` con su dirección de correo
     Gmail.
   - Cree un secreto llamado `SMTP_PASSWORD` con una [contraseña de
     aplicación](https://support.google.com/accounts/answer/185833) de
     Gmail (si utiliza autenticación en dos pasos).  Si no tiene 2FA
     activado debe habilitarlo para poder generar la contraseña de
     aplicación.
   - Opcionalmente, cree un secreto `ALERT_EMAIL` si desea que las
     alertas se envíen a una dirección distinta de `SMTP_EMAIL`.  También
     puede definir un campo `email` por activo desde la interfaz de la
     aplicación.

4. **Configurar la aplicación web**:

   - Abra la URL de GitHub Pages de su repositorio en el navegador.
   - Pulse en **Configuración** y rellene:
     - **Usuario de GitHub**: su nombre de usuario.
     - **Token de acceso personal**: cree un token en
       [github.com/settings/tokens](https://github.com/settings/tokens)
       con permisos **repo** y **workflow**.  Copie y pegue aquí el valor.
     - **Nombre del repositorio**: el nombre exacto del repositorio
       donde está alojada la aplicación.
     - **Rama**: normalmente `main`.
     - **Correo de alerta predeterminado**: si desea que todas las
       alertas vayan a un correo diferente del remitente.
   - Guarde la configuración.  Los datos se almacenan de forma local en
     su navegador.

5. **Agregar activos**: use el botón **Agregar Activo** para añadir
   criptomonedas o acciones.  Introduzca el símbolo tal como aparece
   en Yahoo Finance (por ejemplo `ETH-USD` o `TSLA`), un nombre
   descriptivo opcional y niveles de alerta.  Puede proporcionar un
   correo de alerta específico para ese activo si lo prefiere.

6. **Esperar la actualización automática**: el flujo de trabajo
   `update_prices.yml` se ejecuta cada 10 minutos.  Actualiza los
   precios, genera los archivos históricos y envía alertas según
   corresponda.  No es necesario realizar ninguna acción manual una vez
   configurada la aplicación.

## Notas importantes

* **Limitaciones de la API de Yahoo Finance**: aunque no requiere
  autenticación, la API de Yahoo puede imponer límites de tasa de
  consultas.  El flujo de trabajo está configurado para ejecutarse con
  moderación (cada 10 minutos) para minimizar estos impactos.  Si
  experimenta errores frecuentes, considere aumentar el intervalo.
* **Precauciones de seguridad**: nunca comparta sus tokens ni
  contraseñas de aplicación.  Almacénelos únicamente en GitHub
  Secrets y en el almacenamiento local de su navegador.  El token de
  GitHub se utiliza para actualizar `watchlist.json` cuando agrega o
  elimina activos desde la interfaz web.
* **Funcionamiento sin intervención**: la aplicación está diseñada para
  funcionar 24/7.  Una vez configurados los secretos y la página
  publicada, el flujo de trabajo se encargará de mantener los datos
  actualizados y las alertas serán enviadas automáticamente.

## Soporte

Si encuentra problemas o desea mejorar la aplicación, puede abrir un
_issue_ o una solicitud de _pull request_ en el repositorio.
