# CarreRAGs · página

Interfaz pública de consulta de ofertas educativas de Argentina, con aspecto
tipo ChatGPT. Este componente sirve la página con Flask y reenvía preguntas a
la API existente. Se despliega en el contenedor **`carrerags-pagina`**.

## Responsabilidad y alcance

- Consultas independientes; la API recibe solamente la pregunta actual.
- Los intercambios y accesos del lateral viven en memoria en la pestaña. No se
  guardan en localStorage ni en una base de datos; se pierden al recargar.
- Los ejemplos completan el cuadro de texto; el usuario pulsa el botón para enviar.
- El botón, el campo y «Nueva consulta» se deshabilitan durante la solicitud.
- Enter envía la pregunta mediante el mismo formulario y sus validaciones;
  Shift+Enter inserta un salto de línea. No se envía durante la composición
  de texto ni por repetición de una tecla mantenida pulsada.
- Indicador de espera y aviso adicional a los 45 segundos, sin simular etapas.
- Reintento manual y pregunta conservada ante fallos. No hay reintentos automáticos.
- Respuesta en Markdown con títulos, listas, tablas y enlaces institucionales.
- Markdown convertido en el servidor y saneado; no se admite HTML ejecutable,
  imágenes remotas ni enlaces con protocolos peligrosos.
- Copiar respuesta en Markdown (requiere un contexto seguro para el portapapeles,
  normalmente HTTPS o localhost).
- Vista de escritorio: la adaptación para celular y otros atajos/navegación de
  teclado específicos quedan para otra etapa. Se conservan controles HTML nativos.

La API pública todavía no devuelve ofertas estructuradas. Esta interfaz no
construye fichas ni comparadores, ni modifica ese contrato. Los criterios y
consumos de tokens no se muestran en la vista principal.

## Integración y selección de LLM

La página llama a [llm](../llm/README.md), que normaliza la pregunta, consulta
Qdrant mediante el servicio [embedding](../embedding/README.md) y redacta una
respuesta. [ingesta](../ingesta/README.md) publica previamente ese catálogo;
no se ejecuta por cada pregunta.

El router de la API selecciona actualmente Qwen/Ollama. OpenAI está disponible
como adaptador alternativo mediante un cambio explícito del import del router
y un nuevo despliegue de la API. Cambiar `URL_API` configura la dirección de la
API, no el modelo. **La página todavía no incluye selector Qwen/OpenAI** ni
envía una elección de conector en la solicitud. Esa posibilidad se conversó,
pero no está implementada. Las credenciales LLM pertenecen al servidor.

Las métricas de `rendimiento` y los consumos se conservan en el JSON del proxy,
sin mostrarse como contenido del chat. Ver [comparativas.md](../comparativas.md)
para tiempos y diferencias de calidad observadas; la interfaz presenta el
texto recibido y no verifica por sí sola los requisitos de las ofertas.

## Organización

| Archivo | Responsabilidad |
| --- | --- |
| `app.py` | Configuración, aplicación Flask, proxy HTTP y saneamiento de Markdown. |
| `wsgi.py` | Arranque real mediante Gunicorn o Flask; carga la configuración. |
| `templates/index.html` | Pantalla y estructura de los intercambios. |
| `static/styles.css` | Apariencia de escritorio. |
| `static/chat.mjs` | Interacción, bloqueo, historial de sesión, errores y reintento. |
| `static/api.mjs` | Cliente HTTP con timeout y validación de la respuesta. |
| `Dockerfile`, `compose.yaml` | Imagen y despliegue del contenedor. |
| `install.sh` | Construye, despliega y comprueba el contenedor `carrerags-pagina`. |
| `requirements.txt`, `requirements-docker.txt` | Dependencias locales y servidor exclusivo de Docker. |
| `tests/` | Verificaciones con API y configuración simuladas. |

## Configuración

Crear **`pagina/.env`** en la carpeta del componente con este nombre de variable:

```text
URL_API
```

El archivo debe existir en el equipo que despliega antes de ejecutar el instalador.

## Arranque con Docker

En el Mac o servidor Linux, con Docker iniciado, Compose v2, Bash 3.2 o posterior,
`curl`, `grep` y el `.env` configurado por el usuario, ejecutar desde `pagina`:

```bash
bash install.sh
```

El instalador valida Compose sin imprimir su configuración, construye la imagen,
crea o recrea el servicio y espera hasta 120 segundos por su healthcheck.
Comprueba que el nombre real del contenedor sea **`carrerags-pagina`** y consulta
`/health` mediante el puerto publicado. Funciona también si se invoca desde otro
directorio indicando la ruta del script; resuelve los archivos junto a él.
Los errores interrumpen el despliegue y muestran el comando para revisar los logs.

El script desactiva la lectura implícita del `.env` para interpolación de Compose;
el `env_file` explícito del servicio sigue inyectando `URL_API` al contenedor.
No imprime el contenido de ese archivo. El healthcheck verifica la página;
la conexión real con la API se comprueba enviando una consulta desde la interfaz.

Para seguir los logs:

```bash
docker logs -f carrerags-pagina
```

También se puede desplegar manualmente desde `pagina`:

```console
docker compose up -d --build
docker compose ps
docker compose logs -f pagina
```

- Página: `http://localhost:8080/`.
- Desde otro equipo de la red, si el servidor se llama `macmini`: `http://macmini:8080/`.
- Estado: `http://localhost:8080/health`.
- Contenedor: `carrerags-pagina`.
- Servidor: Gunicorn, dos procesos y cuatro hilos por proceso.

La imagen usa Python 3.12, se ejecuta como usuario sin privilegios y el contenedor
tiene el sistema de archivos de solo lectura con un directorio temporal separado.
El healthcheck solo verifica Flask; no llama a la API ni consume tokens.

Para cambiar el puerto público, modificar el lado izquierdo de `8080:8080`
en Compose; el instalador detecta ese puerto para la comprobación HTTP.
Después de cambiar código o configuración, volver a ejecutar `bash install.sh`
o recrear manualmente el servicio:

```console
docker compose up -d --build --force-recreate
```

El despliegue de dominio/HTTPS queda a cargo del proxy de la instalación. Este
componente no configura DNS ni certificados. La API y esta página no incorporan
autenticación ni un límite de consultas distribuido; los límites de uso público
deben definirse en la instalación. No hay una ruta que acepte destinos arbitrarios.

Después de subir los cambios al repositorio, actualizar en el Mac y desplegar:

```bash
cd ~/carrerags
git pull
bash pagina/install.sh
```

Si también cambió la API, ejecutar su propio `bash llm/install.sh`. Cada
instalador construye y recrea únicamente su componente.

## Desarrollo local

Requiere Python 3.10 o posterior. Desde `pagina`, en PowerShell:

```powershell
python -m venv .pagina
.\.pagina\Scripts\python.exe -m pip install -r requirements.txt
.\.pagina\Scripts\python.exe app.py
```

Si `.pagina` ya existe, omitir su creación. Usar su ejecutable explícitamente
evita instalar paquetes en el Python global y no requiere activar el entorno.
`requirements.txt` no instala Gunicorn; `requirements-docker.txt` lo agrega
solamente en la imagen Linux. El servidor de Flask del comando anterior es
exclusivamente para desarrollo. Arrancar la aplicación
real carga la configuración local; las pruebas usan la fábrica con datos inyectados.

## Interfaces y contratos

### `GET /`

Entrega la página. Recursos y bibliotecas se sirven localmente, sin CDN.

### `GET /health`

```json
{"resultado": true, "mensaje": "ok", "salida": {"nombre": "carrerags-pagina", "estado": "ok"}}
```

### `POST /api/consulta`

Recibe `{"pregunta": "Quiero estudiar diseño a distancia"}`. La pregunta debe
ser texto no vacío, con un máximo de 8000 caracteres; se eliminan espacios externos.
El cuerpo HTTP admite hasta 32 KiB. Se envía una única solicitud POST al endpoint
`/llmrag/armador` de `URL_API`.

La respuesta conserva el JSON y el estado HTTP de la API. Ante éxito agrega
`respuesta_html` al nivel superior, generado a partir de `salida.respuesta`.
El frontend comprueba tanto el estado HTTP como `resultado`: un HTTP 200 con
`resultado: false` también es un fallo.

La solicitud contiene solo la pregunta; no se envía el historial de la pestaña.
**Enter** usa el mismo envío y validaciones que el botón; **Shift+Enter** deja
escribir varias líneas. Los nuevos envíos se bloquean hasta terminar la petición.

| Estado | Comportamiento |
| --- | --- |
| 200 y `resultado: true` | Muestra respuesta y permite copiarla. |
| 404 | Muestra ausencia de resultados dentro del intercambio, sin modal. |
| 422 | Entrada inválida; aviso con posibilidad de corregirla. |
| 413 | Solicitud demasiado grande. |
| 401, 429, 500 y otros errores externos | Conserva el código y muestra aviso; admite reintento manual. |
| 502 local | Conexión fallida, JSON incorrecto o respuesta incompatible. |
| 504 local | Tiempo máximo de la llamada a la API agotado. |
| 500 local | Fallo interno o al preparar el contenido. |

El timeout de la llamada a la API es de **240 segundos**. El navegador espera
hasta **250 segundos**; Gunicorn usa 270. El proxy frontal de la instalación
debe permitir estos tiempos. Una desconexión o timeout no garantiza que la API
haya detenido su trabajo; repetir manualmente podría iniciar otra consulta.

Las funciones internas tienen parámetros tipados y retornan
`(resultado, mensaje, salida)`: éxito `(True, "ok", salida)` y error
`(False, mensaje, vacío_o_datos_http)`. Las funciones JavaScript documentan el
mismo contrato mediante JSDoc. Los adaptadores de Flask y los callbacks de las
bibliotecas cumplen las firmas públicas exigidas por esas interfaces.
Las excepciones se capturan y registran sin volcar preguntas, cuerpos completos
ni configuración. El access log no incluye cuerpos de las solicitudes.

La página no guarda consultas en disco. La API `llm` sí conserva sus salidas
completas según su propio contrato; este componente no cambia esa conducta.

## Problemas frecuentes

| Situación | Explicación y comprobación |
|---|---|
| `env file .../pagina/.env not found` al instalar | Crear `pagina/.env` en el equipo que despliega e incluir `URL_API`. |
| `No such container: carrerags-pagina` después de ese error | La validación de Compose se detuvo antes de crear el contenedor. Corregir el archivo faltante y repetir `bash install.sh`. |
| Aviso «Probemos con otra búsqueda» | La API devolvió 404: puede no haber criterios interpretados o no haber ofertas. La página muestra el mismo aviso en ambos casos; revisar `mensaje` y filtros en el JSON guardado por la API. |
| Un saludo como `holis` no devuelve opciones | Es esperado: no contiene carrera, nivel, institución, ubicación ni modalidad. |
| La página abre pero las consultas fallan | `/health` comprueba Flask. Revisar la API y la accesibilidad de `URL_API` desde el contenedor; `localhost` no apunta a otro contenedor. |
| Los cambios de Enter o recursos no aparecen | Subir y recibir el código actualizado, volver a desplegar `pagina` y recargar la página; si persisten recursos anteriores, realizar una recarga completa del navegador. |

## Verificaciones aisladas

Con las dependencias instaladas, desde `pagina`:

```console
.\.pagina\Scripts\python.exe -I -X utf8 tests/run_tests.py
node --input-type=module -e "const [ok,msg,data] = await (await import('./tests/check_frontend.mjs')).runChecks(); console.log(JSON.stringify({resultado:ok,mensaje:msg,salida:data},null,2)); process.exitCode = ok ? 0 : 1;"
```

La verificación JavaScript requiere Node.js 16 o posterior. La suite Python
importa `app.py`, nunca `wsgi.py`, e inyecta `Settings` ficticios. Bloquea la carga
de `.env` y las conexiones de red accidentales. La suite JavaScript inyecta
`fetch` simulado. No arrancan la aplicación real ni consultan servicios externos.

Cubren éxito, serialización, estados HTTP, formato de validación FastAPI,
ausencia de ofertas, HTTP 200 fallido, JSON incorrecto, respuestas incompletas,
timeout, desconexión, ausencia de reintentos, recursos y saneamiento de Markdown.
La conectividad con la API real y la construcción/ejecución del contenedor deben
comprobarse por el usuario con su configuración local.
