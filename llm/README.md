# llm

API FastAPI que interpreta preguntas sobre ofertas educativas de Argentina,
busca ofertas en Qdrant con el servicio propio de embeddings y genera una
respuesta en castellano rioplatense con formato Markdown. El código actual del
endpoint selecciona Qwen mediante Ollama con `helpers/llm_qewn.py`. Phi está
disponible en `helpers/llm_phi.py` y OpenAI en `helpers/llm_openai.py`, con las
mismas funciones públicas.

## Organización

| Archivo | Responsabilidad |
|---|---|
| `main.py` | Crea la aplicación `llm` y registra sus routers. |
| `routers/estado.py` | Endpoint de estado `GET /`. |
| `routers/llmrag.py` | Endpoint `POST /llmrag/armador` y adaptación de resultados a HTTP. |
| `helpers/prerag.py` | Lee las referencias de Qdrant y construye el prompt. |
| `helpers/prompt.md` | Reglas, ejemplos y marcadores del prompt. |
| `helpers/llm_openai.py` | Normaliza la pregunta y genera la respuesta humana mediante dos llamadas a OpenAI. |
| `helpers/llm_qewn.py` | Adaptador seleccionado en el router: normalización y redacción mediante la API nativa de Ollama. |
| `helpers/llm_phi.py` | Adaptador Phi con la misma interfaz de Qwen y configuración independiente mediante `LLM_PHI` y `LLM_PHI_MODELO`. |
| `helpers/buscador_rag.py` | Busca ofertas usando Qdrant y el servicio HTTP de embeddings. |
| `helpers/rag/` | Adaptación del flujo de búsqueda de `consultador`, sin dependencia de ese proyecto en ejecución. |
| `helpers/prompt_respuesta_usuario.md` | Reglas para redactar la respuesta a partir de las ofertas recuperadas. |
| `helpers/respuesta_json.py` | Guarda la respuesta completa en `JSON/AAAAMMDD-HHMMSS.json`. |
| `helpers/rendimiento.py` | Adapta tiempos y velocidades de ambos proveedores, distinguiendo solicitud y generación. |
| `helpers/configuracion_logs.py` y `log_config.json` | Configuran los logs con fecha y hora. |
| `helpers/contratos_llm.py` | Modelos Pydantic comunes a OpenAI y Qwen/Ollama. |
| `archivos/contrato.json` | Ejemplo del JSON de filtros y consumos; sus conteos son ilustrativos. |
| `Dockerfile`, `compose.yaml` e `install.sh` | Construcción y despliegue del contenedor `carrerags-api`. |
| `healthcheck.py` | Comprueba que la API responde, sin consultar servicios externos. |
| `tests/` | Verificaciones aisladas con datos y servicios simulados. |

Cada grupo nuevo de endpoints debe tener su módulo en `routers/` y registrarse
mediante `app.include_router` en `main.py`.

## Entorno e instalación

Requiere Python 3.10 o posterior. Usar el entorno virtual existente `.llmprerag`.
Desde el directorio `llm`, en PowerShell:

```powershell
.\.llmprerag\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En cmd.exe:

```bat
.llmprerag\Scripts\activate.bat
python -m pip install -r requirements.txt
```

Las dependencias son FastAPI, Uvicorn, python-dotenv y Pydantic 2.
Las llamadas a Ollama, OpenAI y Qdrant usan HTTP con la biblioteca estándar de
Python; no requieren SDK de los proveedores ni el cliente de Qdrant.

## Configuración

Crear **`llm/.env`**, junto a `main.py` y al `Dockerfile`, con los nombres de
variables correspondientes al flujo y al conector seleccionado.

| Grupo | Nombres de variables |
|---|---|
| Compartidas | `VECTORIAL`, `VECTORIAL_NAMESPACE`, `EMBEDDING_URL`, `HTTP_TIMEOUT`. |
| Qwen | `LLM_QWEN`, `LLM_QWEN_MODELO`. |
| Phi | `LLM_PHI`, `LLM_PHI_MODELO`. |
| OpenAI | `API_KEY_LLM`, `MODELO`. |

Crear el archivo antes del arranque o de construir la imagen Docker. Después
de modificar la configuración, reconstruir la imagen y recrear el contenedor.

## Arranque

Con el entorno activado y desde `llm`:

```console
uvicorn main:app --host 127.0.0.1 --port 8021 --reload --log-config log_config.json
```

También se puede ejecutar con `python -m uvicorn` y los mismos argumentos.
El puerto se establece mediante `--port 8021`. Omitir `--reload` para ejecutar
sin recarga de desarrollo.

- API: http://127.0.0.1:8021/
- Swagger: http://127.0.0.1:8021/docs
- ReDoc: http://127.0.0.1:8021/redoc
- OpenAPI: http://127.0.0.1:8021/openapi.json

Crear la carpeta `JSON` dentro de `llm` si no existe y asegurar permisos de
escritura: allí se guarda la salida completa de cada consulta gestionada por el
endpoint. Los nombres usan fecha y hora argentina, con precisión de segundos;
dos respuestas guardadas en el mismo segundo pueden sobrescribir el archivo.

## Despliegue con Docker

En el Mac mini o servidor, disponer de Docker con contenedores Linux, Docker
Compose v2 o posterior, Bash 3.2 o posterior y `curl`. Copiar o actualizar la
carpeta `llm` y disponer allí del `.env` de la instalación antes de construir.

Desde esa carpeta:

```bash
bash install.sh
```

El script valida Compose, construye la imagen `carrerags-api:latest`, recrea el
contenedor **`carrerags-api`**, espera su healthcheck y comprueba el puerto
**8021**. La API escucha dentro del contenedor en `0.0.0.0:8021` y el puerto se
publica en el host. El arranque usa Uvicorn sin recarga de desarrollo.

Las respuestas quedan en `/app/JSON`, montado sobre la carpeta `JSON` del host
si existe, o `json` en caso contrario. El script crea la carpeta cuando hace
falta. El `.env` queda copiado en la imagen; no se monta como volumen.

Para ver los logs:

```bash
docker logs -f carrerags-api
```

Después de cambiar código o el `.env`, volver a ejecutar `bash install.sh` para
reconstruir y recrear el servicio. El healthcheck comprueba solo la API; no
valida las credenciales ni la conexión a Qdrant, embeddings o al proveedor LLM.

## Ollama: LLM local en Mac mini M4

Esta guía incorpora la instalación y operación descritas en [LLM.md](../LLM.md).
El router actual ya importa las funciones de `helpers/llm_qewn.py`. Según las
notas actualizadas, el acceso HTTP desde Windows a `http://macmini:11434` fue
comprobado. La conectividad desde Docker y el flujo completo de interpretación,
búsqueda y redacción deben comprobarse en cada instalación.

### Entorno documentado

| Elemento | Configuración |
|---|---|
| Hardware | Apple Mac mini M4, 16 GB de RAM. |
| Sistema operativo | macOS. |
| Instalación | Homebrew, nativa en el Mac, fuera de Docker. |
| Versión comprobada en `LLM.md` | Ollama 0.40.11. |
| Modelo Qwen | Qwen 3.5 2B, cuantización Q4_K_M; etiqueta `qwen3.5:2b-q4_K_M`. |
| Modelo Phi de la comparación | Phi-4-mini; etiqueta `phi4-mini:latest`. |
| API local | `http://localhost:11434`. |
| API desde Windows | `http://macmini:11434`; acceso HTTP comprobado según las notas. |
| Inicio | Manual mediante `brew services run ollama`, sin registrar inicio automático. |
| Aceleración | GPU Apple Silicon mediante Metal. |
| Motor registrado en las notas | llama.cpp. |
| Memoria de Qwen cargado | Aproximadamente 1,6 GB en la observación de `LLM.md`; no es un límite de consumo para otros contextos o consultas. |
| Modelos en disco | `~/.ollama/models`, salvo configuración de otra ubicación. |

La [documentación de macOS de Ollama](https://docs.ollama.com/macos) describe
el soporte de CPU y GPU en Apple Silicon. La etiqueta se publica en el
[catálogo de Qwen 3.5](https://ollama.com/library/qwen3.5/tags).

### Instalar y encender

En una terminal del Mac, instalar Ollama:

```bash
brew install ollama
ollama --version
```

Encenderlo manualmente y consultar el estado del servicio:

```bash
brew services run ollama
brew services list
```

Comprobar que la API local responde:

```bash
curl --connect-timeout 5 http://localhost:11434/api/version
```

`run` inicia el servicio sin registrarlo para el inicio de sesión o arranque.
Para conservar este esquema manual, usar `run` al volver a encenderlo, también
después de reiniciar macOS. `brew services start` y `restart` sí registran el
arranque automático, según la [documentación de Homebrew](https://docs.brew.sh/Manpage.html#services-subcommand).

### Descargar y usar Qwen

Descargar el modelo la primera vez y listar los modelos instalados:

```bash
ollama pull qwen3.5:2b-q4_K_M
ollama list
```

Abrir una sesión interactiva:

```bash
ollama run qwen3.5:2b-q4_K_M
```

Para salir del chat, escribir `/bye`. Salir del chat no apaga el servidor.

### Descargar y usar Phi-4-mini

Phi se instala como otro modelo del mismo servidor Ollama; no requiere otro
servicio ni otro puerto. En el Mac mini M4 de 16 GB, con Ollama instalado y
encendido según los pasos anteriores:

```bash
ollama pull phi4-mini
ollama list
```

La etiqueta utilizada en la comparación es **`phi4-mini:latest`**. Para abrir un chat:

```bash
ollama run phi4-mini
```

Escribir `/bye` para salir; el servidor permanece disponible. Comprobar el
modelo cargado y liberar su memoria cuando termine la prueba:

```bash
ollama ps
ollama stop phi4-mini
```

Para usar Phi desde la API, crear `llm/.env` con estos nombres de variables:

```text
LLM_PHI
LLM_PHI_MODELO
```

La conectividad entre la API y Ollama debe comprobarse desde el proceso o
contenedor que ejecuta CarreRAGs.

Seleccionar el import de `helpers.llm_phi` según
[Selección del conector LLM](#selección-del-conector-llm) y reiniciar la API.
En Docker, desde la raíz del repositorio, ejecutar `bash llm/install.sh` para
reconstruir y recrear el servicio. Crear las variables no cambia el import
activo; Qwen sigue seleccionado en el router del repositorio.

Los contratos, parámetros y límites están en el
[adaptador Phi](#adaptador-phi-mediante-ollama). En particular, el flujo RAG
mantiene un contexto de 32768 tokens: el rendimiento de un chat corto no
predice el tiempo de procesar las referencias del catálogo. Ver
[Phi-4-mini en Ollama](https://ollama.com/library/phi4-mini).

### Ver y liberar memoria

Consultar los modelos cargados en RAM/GPU:

```bash
ollama ps
```

La columna `PROCESSOR` permite comprobar el uso de CPU/GPU. Tras un período de
inactividad, los modelos se descargan de memoria según la política de permanencia
de Ollama; una nueva consulta vuelve a cargarlos. Para descargar
Qwen de memoria manteniendo el servidor disponible:

```bash
ollama stop qwen3.5:2b-q4_K_M
```

### Apagar y comprobar

Apagar el servicio completo:

```bash
brew services stop ollama
```

Esto detiene el servidor y libera los modelos cargados. No elimina los modelos
descargados del disco y no requiere ejecutar antes `ollama stop`.

Comprobar que ya no responde:

```bash
curl --connect-timeout 3 http://localhost:11434/api/version
```

El resultado esperado es un error de conexión. Si responde, hay que comprobar
si otra instancia de Ollama sigue escuchando en ese puerto. Para volver a
utilizarlo, ejecutar `brew services run ollama`.

### Acceso desde Windows y endpoints de Ollama

Las notas registran la dirección **`http://macmini:11434`** como accesible desde
Windows. Estos endpoints pertenecen al servidor Ollama:

| Endpoint | Método | Función |
|---|---|---|
| `/api/version` | GET | Consultar la versión del servidor. |
| `/api/tags` | GET | Listar modelos instalados en disco. |
| `/api/ps` | GET | Listar modelos cargados en memoria. |
| `/api/chat` | POST | Generar una respuesta de chat; lo usan `llm_qewn` y `llm_phi`. |
| `/api/generate` | POST | Generar texto a partir de un prompt. |

Desde Windows, consultar servidor, modelos instalados y modelos cargados:

```bat
curl.exe --connect-timeout 5 http://macmini:11434/api/version
curl.exe --connect-timeout 5 http://macmini:11434/api/tags
curl.exe --connect-timeout 5 http://macmini:11434/api/ps
```

La versión confirma el acceso al servidor. La lista de modelos debe incluir
`qwen3.5:2b-q4_K_M` o `phi4-mini:latest`, según el modelo que se quiera usar.
Que no aparezca en `/api/ps` puede significar que está descargado de memoria,
aunque siga instalado.

Para comprobar además que el modelo genera texto, ejecutar manualmente en
**CMD** (las continuaciones `^` y las comillas son para esa consola):

```bat
curl.exe --connect-timeout 5 --max-time 120 http://macmini:11434/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"qwen3.5:2b-q4_K_M\",\"messages\":[{\"role\":\"user\",\"content\":\"Responde solamente OK\"}],\"stream\":false,\"think\":false}"
```

Para probar Phi con el mismo comando, cambiar el valor de `model` a
`phi4-mini:latest`.

Una respuesta final incluye texto en `message.content` y `done: true`. Esta es
una prueba de inferencia básica; no verifica el catálogo ni el flujo RAG completo.

### Conexión desde Docker

Ollama se ejecuta de forma nativa en el Mac. Si `carrerags-api` se ejecuta en
Docker Desktop en ese mismo Mac, puede usar **`http://host.docker.internal:11434`**.
Si Docker corre en otro equipo, debe usar una dirección del Mac accesible desde
ese contenedor, como `http://macmini:11434` si allí resuelve el nombre.
`localhost` dentro del contenedor apunta al propio contenedor.

Los registros de la instalación desplegada del 27 de octubre de 2026 muestran
una llamada a Qwen y una respuesta normalizada. Cada instalación debe comprobar
su propia conectividad desde Docker; el healthcheck de la API por sí solo no
comprueba Ollama, Qdrant ni embeddings.
La interfaz de escucha de Ollama se configura mediante `OLLAMA_HOST`.
La dirección anterior por sí sola no garantiza
acceso desde el contenedor. Ver la [FAQ de Ollama](https://docs.ollama.com/faq)
para la configuración de escucha, memoria y almacenamiento de modelos.

El acceso HTTP comprobado desde Windows no demuestra la conectividad desde el
contenedor; esta debe verificarse por separado.

### Escucha de red y acceso

La variable `OLLAMA_HOST` corresponde al proceso Ollama. La API no exige
autenticación por defecto: según las pautas de `LLM.md`, restringir el acceso a
equipos de confianza, mantener el servicio bajo control manual y no exponer el
puerto 11434 a Internet.

`OLLAMA_HOST` configura el servidor. Las variables que usa CarreRAGs para
conectarse son `LLM_QWEN` y `LLM_QWEN_MODELO` para Qwen, o `LLM_PHI` y
`LLM_PHI_MODELO` para Phi, detalladas a continuación.

## Selección del conector LLM

Se selecciona en [routers/llmrag.py](routers/llmrag.py), mediante el import de las
dos funciones públicas. El código actual selecciona Qwen:

```python
from helpers.llm_qewn import crea_prompt_pre_rag, genera_respuesta_usuario
```

Para seleccionar Phi, sustituir ese import por:

```python
from helpers.llm_phi import crea_prompt_pre_rag, genera_respuesta_usuario
```

Para seleccionar OpenAI, sustituir ese import por:

```python
from helpers.llm_openai import crea_prompt_pre_rag, genera_respuesta_usuario
```

Debe quedar activo un único import para las dos funciones. El cambio afecta
tanto la normalización de filtros como la redacción posterior. No hay selección
automática mediante variables ni fallback entre proveedores. Después de cambiar
el código, reiniciar la API; en Docker, reconstruir la imagen y recrear el
contenedor. Configurar `MODELO` no cambia el conector seleccionado.

La interfaz [pagina](../pagina/README.md) no tiene todavía selector de modelo.
La petición actual contiene solo `pregunta`; no hay un parámetro implementado
para seleccionar el conector por consulta. El selector de conector se conversó
como una ampliación posible y sigue pendiente. Las credenciales pertenecen al
servidor, independientemente de la futura presentación de esa selección.

## Endpoints

### GET /

Comprueba únicamente que la aplicación responde, sin consultar servicios externos.

```json
{
  "resultado": true,
  "mensaje": "ok",
  "salida": {"nombre": "llm", "estado": "ok"}
}
```

### POST /llmrag/armador

Recibe un objeto JSON con `pregunta` de tipo string:

```json
{
  "pregunta": "Quiero estudiar Informática online en Quilmes"
}
```

Recorre las referencias de Qdrant y consulta al proveedor seleccionado para normalizar la
pregunta. Luego busca ofertas con el servicio HTTP de embeddings y Qdrant, y
realiza una segunda llamada al mismo proveedor para redactar la respuesta usando esas
ofertas y la pregunta original.
La respuesta HTTP 200 tiene esta estructura; los filtros, consumos y tiempos son
ilustrativos y representan un ejemplo con el conector OpenAI:

```json
{
  "resultado": true,
  "pregunta": "Quiero estudiar Informática online en Quilmes",
  "mensaje": "ok",
  "rendimiento": {
    "tiempo_total_segundos": 6.1,
    "tiempos_etapas_segundos": {
      "normalizacion": 3.0,
      "rag": 0.5,
      "respuesta_usuario": 2.5
    },
    "llamadas_llm": {
      "normalizacion": {
        "proveedor": "openai",
        "modelo": "modelo-ficticio",
        "tiempo_solicitud_segundos": 3.0,
        "tiempo_servidor_segundos": 2.7,
        "tiempo_carga_segundos": null,
        "tiempo_prompt_segundos": null,
        "tiempo_generacion_segundos": null,
        "tokens_salida": 60,
        "tokens_por_segundo_generacion": null,
        "tokens_por_segundo_solicitud": 20.0,
        "metricas_proveedor": {"openai_processing_ms": 2700.0, "output_tokens": 60}
      },
      "respuesta_usuario": {
        "proveedor": "openai",
        "modelo": "modelo-ficticio",
        "tiempo_solicitud_segundos": 2.5,
        "tiempo_servidor_segundos": 2.1,
        "tiempo_carga_segundos": null,
        "tiempo_prompt_segundos": null,
        "tiempo_generacion_segundos": null,
        "tokens_salida": 200,
        "tokens_por_segundo_generacion": null,
        "tokens_por_segundo_solicitud": 80.0,
        "metricas_proveedor": {"openai_processing_ms": 2100.0, "output_tokens": 200}
      }
    }
  },
  "salida": {
    "carrera": "Informática",
    "nivel_educativo": null,
    "institucion": null,
    "ubicacion": "Quilmes",
    "modalidad": "distancia",
    "respuesta": "Estas son las opciones recuperadas:…",
    "consumo_tokens": {
      "entrada": 3000,
      "salida": 260,
      "total": 3260,
      "entrada_cache": 2800,
      "razonamiento": 40
    },
    "consumos_llm": {
      "normalizacion": {
        "entrada": 2000,
        "salida": 60,
        "total": 2060,
        "entrada_cache": 1900,
        "razonamiento": 20
      },
      "respuesta_usuario": {
        "entrada": 1000,
        "salida": 200,
        "total": 1200,
        "entrada_cache": 900,
        "razonamiento": 20
      }
    }
  }
}
```

`respuesta` contiene Markdown. En el JSON transmitido, los saltos de línea se
representan como `\n`; el cliente debe decodificar el JSON y renderizar ese campo.
La salida pública no incluye `ofertas` ni `cantidad`. `consumo_tokens` suma las
llamadas con consumo conocido y `consumos_llm` conserva el detalle por etapa.
La respuesta completa se guarda en `JSON/AAAAMMDD-HHMMSS.json`, también cuando
el flujo devuelve un error gestionado. Si falla ese guardado, se responde 500.

Se usa POST para recibir JSON en el body. El cliente debe serializar correctamente
el JSON, incluidas las comillas internas de la pregunta. FastAPI rechaza un body
malformado antes de ejecutar el endpoint.

### Estados HTTP y errores

| Estado | Situación |
|---|---|
| 200 | Se normalizó la pregunta, se recuperaron ofertas y se generó la respuesta humana. |
| 404 | No se identificaron criterios de búsqueda o no se encontraron ofertas. |
| 422 | Body inválido, pregunta ausente, tipo incorrecto o pregunta vacía. |
| 500 | Configuración local incompleta, error al preparar el prompt o recuperar referencias, fallo al guardar el JSON o excepción inesperada. |
| 502 | Fallo de conexión o timeout de servicios externos, respuesta incompleta, rechazo o datos incompatibles con el contrato. |
| Otros códigos de servicios externos | Se conserva el código cuando está disponible, por ejemplo 401 o 429. |

El 404 por filtros nulos detiene el flujo antes de buscar en el RAG. El 404 por
ausencia de ofertas ocurre después de la búsqueda. Los códigos recibidos de
servicios externos también pueden propagarse, con un mensaje que indica el fallo.

En respuestas gestionadas por la aplicación, los errores incluyen `resultado: false`
y un mensaje descriptivo. El helper conserva `http_status` en `salida` para que
el router lo adapte al estado HTTP. Las validaciones iniciales de FastAPI usan
su formato `detail`; no se convierten al envoltorio de la aplicación.

Si falla la validación después de recibir consumos válidos, estos se conservan.
Si no se recibió el consumo, no se inventan valores cero: un corte de conexión
puede impedir conocer desde la respuesta si el proveedor consumió tokens.

### Diagnóstico de un 404 después de consultar Qwen

| `mensaje` del JSON | Interpretación |
|---|---|
| `No se identificaron criterios de búsqueda en la pregunta` | Los cinco filtros quedaron en `null`; no se ejecutan RAG ni redacción. Un saludo como `holis` es un caso esperado. |
| `No se encontraron ofertas para los criterios indicados` | Se interpretaron filtros y se buscó, pero no se recuperaron ofertas compatibles. |

El registro `POST /llmrag/armador ... 404 Not Found` no significa por sí solo
que falte la ruta. Revisar `pregunta`, `mensaje`, filtros y tiempos de etapas
en la respuesta guardada. Una etapa no ejecutada tiene tiempo `null`.
La ausencia de ofertas no acredita que esa carrera no exista fuera del catálogo.

En el servidor, reemplazar el nombre por el archivo indicado en los logs:

```bash
docker exec carrerags-api cat /app/JSON/AAAAMMDD-HHMMSS.json
```

## Rendimiento y tiempos

`POST /llmrag/armador` publica y guarda `rendimiento` en la raíz del JSON,
inmediatamente después de `mensaje` y antes de `salida`. Incluye las mediciones
disponibles también cuando el flujo falla; no cambia los códigos HTTP.

- `tiempo_total_segundos`: tiempo transcurrido dentro del flujo del endpoint,
  desde antes de la normalización hasta preparar la respuesta. Excluye validación
  inicial de FastAPI, espera anterior al endpoint, guardado en disco, serialización
  y entrega HTTP al cliente.
- `tiempos_etapas_segundos`: tiempos de `normalizacion`, `rag` y
  `respuesta_usuario`. La normalización incluye preparar el prompt y obtener sus
  referencias. RAG incluye embeddings y Qdrant. Una etapa no ejecutada queda `null`.
- `llamadas_llm`: detalle de cada solicitud efectuada al proveedor, separado en
  `normalizacion` y `respuesta_usuario`. Una llamada no efectuada no aparece.

Los tiempos locales usan `time.perf_counter_ns()`, un reloj monotónico; se
publican en segundos. `tiempo_solicitud_segundos` mide desde antes de abrir la
conexión hasta leer y decodificar el JSON completo, incluyendo red y espera.
No incluye la preparación del prompt ni equivale al tiempo hasta el primer token.
En un timeout se conserva el tiempo transcurrido sin inventar conteos de tokens.

Cada llamada identifica `proveedor` (`ollama` u `openai`) y el `modelo`
solicitado. Tiene dos velocidades diferentes:

| Campo | Cálculo y alcance |
|---|---|
| `tokens_por_segundo_generacion` | Solo si hay duración interna de generación: `eval_count × 1.000.000.000 / eval_duration`. |
| `tokens_por_segundo_solicitud` | Tokens de salida divididos por el tiempo completo medido de la solicitud; disponible en ambos proveedores cuando se conocen los tokens. |

**Qwen y Phi/Ollama:** `metricas_proveedor` conserva `eval_count`, `eval_duration`,
`total_duration`, `load_duration` y `prompt_eval_duration`. Los cuatro tiempos
originales están en **nanosegundos**. Se convierten respectivamente en
`tiempo_generacion_segundos`, `tiempo_servidor_segundos`,
`tiempo_carga_segundos` y `tiempo_prompt_segundos`. El tiempo de prompt cubre
los tokens no cacheados. Ver la [API de chat de Ollama](https://docs.ollama.com/api/chat).

Por ejemplo, `eval_count: 100` y `eval_duration: 2000000000` significan
**50 tokens/segundo de generación**. Si la solicitud completa demoró cuatro
segundos, la velocidad de solicitud será **25 tokens/segundo**.

**OpenAI:** los tokens se toman de `usage.output_tokens`, incluidos los de
razonamiento. Cuando existe el header `openai-processing-ms`, su valor se
conserva en `metricas_proveedor.openai_processing_ms` y se convierte a segundos
en `tiempo_servidor_segundos`. Es el procesamiento de la petición completa,
**no** el tiempo exclusivo de generación. Este conector no dispone del desglose
equivalente a `eval_duration`: carga, prompt, generación y velocidad de generación
quedan `null`. Ver los [headers oficiales de OpenAI](https://developers.openai.com/api/reference/overview#debugging-requests).

Los tiempos opcionales ausentes o inválidos quedan `null`; una duración cero
no produce divisiones por cero. No se suman ni promedian velocidades de etapas.
Para comparar instalación nativa y Docker, usar la misma métrica, modelo,
pregunta, contexto y condiciones de carga/caché. Entre proveedores cambian
también el tokenizador y el trabajo realizado: tokens/segundo por sí solo no
evalúa calidad. Los JSON anteriores no se completan con tiempos estimados.

Ver [comparativas.md](../comparativas.md) para la medición de Abogacía y el
[análisis de calidad previo](ANALISIS_LLM_20261027.md). Los tiempos registrados
no sustituyen una revisión de fidelidad: un texto válido puede modificar
requisitos, títulos o advertencias. Las ofertas originales no se guardan en la
salida pública, lo que limita la reconstrucción de las entradas de redacción.

## Comparación de OpenAI, Qwen y Phi

Revisión del **28 de octubre de 2026** sobre tres salidas guardadas para la
misma pregunta: **«donde estudiar para ser abogado?»**. La fecha corresponde
al análisis; los JSON no incluyen una fecha de ejecución.

| Salida analizada | Proveedor | Modelo registrado |
|---|---|---|
| [openai.json](json/openai.json) | OpenAI | `gpt-6-luna` |
| [qwen.json](json/qwen.json) | Ollama | `qwen3.5:2b-q4_K_M` |
| [phi.json](json/phi.json) | Ollama | `phi4-mini:latest` |

El archivo de Qwen se llama `qwen.json`; el módulo conserva el nombre
`llm_qewn.py`. La referencia para contrastar las ofertas es
[consultador/TOTAL.json](../consultador/TOTAL.json), sin consultar el Excel ni
verificar los sitios de las universidades.

### Filtros y ofertas presentadas

Los tres devolvieron `resultado: true`, `mensaje: "ok"`, `carrera: "Abogacía"`
y `null` en `nivel_educativo`, `institucion`, `ubicacion` y `modalidad`.

Las tres respuestas presentan las mismas ocho universidades, en el mismo
orden: Morón, Palermo, UCES, Siglo 21, UADE, UCASAL, FASTA y Blas Pascal. Los
ocho enlaces coinciden entre las salidas y con sus ofertas de Abogacía en
`TOTAL.json`, todas de grado y privadas. No se observan omisiones de ofertas
respecto de esas ocho entradas del catálogo.

Los JSON no publican las ofertas originales enviadas a la segunda llamada;
la coincidencia anterior se comprueba sobre las respuestas finales y el
catálogo exportado, sin reconstruir exactamente las entradas de redacción.

### Tiempos y consumos

| Métrica | OpenAI | Qwen | Phi |
|---|---:|---:|---:|
| Tiempo total del flujo | **11,28 s** | **26,50 s** | **47,48 s** |
| Etapa de normalización | 3,55 s | 10,30 s | 24,38 s |
| Etapa de búsqueda RAG | 0,38 s | 0,35 s | 0,15 s |
| Etapa de redacción | 7,34 s | 15,86 s | 22,95 s |
| Tokens de entrada, ambas llamadas | 9.582 | 9.655 | 9.412 |
| Tokens de salida, ambas llamadas | 924 | 827 | 666 |
| Tokens totales | 10.506 | 10.482 | 10.078 |
| Subconjunto de entrada desde caché | 0 | 0 | 2 |
| Subconjunto de salida de razonamiento | 225 | `null` | `null` |
| Generación interna en la redacción | No informada | 56,96 tokens/s | 33,23 tokens/s |

Son los tiempos por etapa del endpoint, que incluyen trabajo adicional al
transporte HTTP de la LLM. El total excluye el guardado y entrega HTTP según
[Rendimiento y tiempos](#rendimiento-y-tiempos). Los consumos no son importes
monetarios. Caché y razonamiento son subconjuntos: no sumarlos otra vez a los
tokens totales. `null` significa desglose desconocido, no cero.

Phi tardó **1,79 veces** el tiempo total de Qwen en esta consulta. La mayor
diferencia está en procesar el prompt de normalización: **20,49 s** en Phi
frente a **8,20 s** en Qwen, con 7.729 y 7.868 tokens de entrada respectivamente.
En Phi, ese procesamiento representa aproximadamente el **84 %** de la etapa
de normalización; generar los 32 tokens de filtros llevó solo **1,14 s**.

La carga inicial de la normalización fue de **2,57 s** en Phi y **0,83 s** en
Qwen; por sí sola no explica la diferencia total. Un chat corto puede sentirse
rápido y tardar más al procesar las referencias extensas del catálogo. La
búsqueda RAG se mantuvo por debajo de 0,4 s en las tres salidas.

### Fidelidad de las respuestas

La revisión usa las reglas de `helpers/prompt_respuesta_usuario.md` y los
datos de `TOTAL.json`; no compara solamente si el flujo terminó sin errores.

| Aspecto | OpenAI | Qwen | Phi |
|---|---|---|---|
| Idioma solicitado | Usa voseo rioplatense. | Redacción neutral, sin tuteo explícito. | Usa tuteo: «puedes», «tienes», «Visita». |
| Nivel y modalidad | Indica grado y conserva las principales condiciones. | Indica grado y modalidad por oferta. | Omite el nivel de grado y el carácter asincrónico de FASTA. |
| Inscripción vigente de UCES | Aclara que no está confirmada. | Omite la advertencia de consultar inscripción vigente. | Menciona el informe institucional, pero no conserva claramente la advertencia de inscripción. |
| Gestión pública o privada | Presenta las opciones como privadas. | Marca las ocho como privadas y después dice que no puede confirmarlo: contradicción. | Presenta las opciones como privadas. |
| Presencialidad y redacción | Explica el CAU de Siglo 21 y evita garantizar que Abogacía en UCASAL sea 100 % online; es compacto. | Conserva condiciones en las entradas, pero agrega un cierre confuso. | Repite la descripción jurídica casi completa y resume con menos detalle las condiciones del CAU. |

Hay un dato de origen que debe revisarse por separado: la descripción de
Abogacía en UADE incluye una referencia a requisitos de presencia «en particular
en salud». Phi la reproduce y Qwen la generaliza en el cierre. La mención ya
está en el catálogo, por lo que no corresponde atribuirla a una invención de
los modelos. Este análisis no modifica el catálogo.

### Lectura y límites de esta prueba

OpenAI produjo la respuesta más rápida y más fiel a las advertencias en esta
muestra. Entre los locales, Qwen fue más rápido que Phi; ambos necesitan mejorar
la conservación de advertencias y la redacción. Para esta consulta, los datos
respaldan mantener Qwen como opción local y usar OpenAI como referencia de
calidad, sin afirmar que ese orden se repita en todo el catálogo.

Es **una ejecución por modelo**, sin repeticiones controladas ni igualdad
acreditada de carga, caché o presión de memoria. No mide memoria consumida ni
compara Ollama nativo con Docker. Las diferencias de tokenizador y los tokens
de razonamiento de OpenAI impiden tratar los conteos como una medida idéntica
de trabajo o de longitud visible. OpenAI no informa el tiempo exclusivo de
generación: su velocidad de solicitud no equivale a los tokens/s internos de
Ollama. Las ofertas originales y los prompts completos no están en estos JSON.

Ver [comparativas.md](../comparativas.md) y el
[análisis previo](ANALISIS_LLM_20261027.md) para los antecedentes.

## Contrato e interpretación

Las funciones internas devuelven siempre `(resultado, mensaje, dato_salida)`.
En éxito, el mensaje es `"ok"`. Ante errores se registra la excepción y se devuelve
un dato vacío o la información necesaria para conservar estado HTTP y consumos.
Los endpoints adaptan ese contrato a JSON.

El objeto interpretado contiene exactamente cinco filtros, cada uno string no vacío
o `null`:

| Filtro | Significado |
|---|---|
| `carrera` | Carrera, disciplina, tema o denominación de formación solicitada. |
| `nivel_educativo` | Grado o nivel educativo explícito. Reemplaza a `tipo_titulo`. |
| `institucion` | Institución educativa. |
| `ubicacion` | Localidad, provincia o lugar de cursada, separado de la institución. |
| `modalidad` | Modalidad solicitada y normalizada. |

Los valores del catálogo sirven para normalizar equivalencias claras. Si no hay
equivalencia, se conserva lo solicitado; no se cambian condiciones para conseguir
resultados ni se deducen relaciones entre las listas. Un dato no especificado
queda en `null`. Licenciatura, Ingeniería o Profesorado se conservan en `carrera`;
no permiten deducir automáticamente `nivel_educativo`.

Las reglas completas están en `helpers/prompt.md`. Incluyen negaciones, alternativas,
profesiones y condiciones que el esquema no representa. La pregunta original
debe conservarse para las siguientes etapas de búsqueda; no se agrega como sexto filtro.

## Referencias de Qdrant y generación del prompt

| Función de `helpers.prerag` | Campo Qdrant |
|---|---|
| `titulos()` | `title` |
| `niveles()` | `level` |
| `instituciones()` | `institution` |
| `locaciones()` | `location` |
| `modalidades()` | `modality` |

Devuelven `tuple[bool, str, list[str]]`. Usan `scroll` con páginas de 256 puntos
y timeout de 30 segundos por solicitud. Solo recuperan el campo correspondiente,
sin vectores. Eliminan espacios externos y duplicados exactos; ordenan sin
distinguir mayúsculas. No filtran por modalidad, estado o elegibilidad.
Una colección vacía devuelve éxito con lista vacía. Un punto sin un valor string
no vacío en el campo consultado hace fallar la operación, sin resultados parciales.

`crea_prompt_rag(pregunta: str)` devuelve `(True, "ok", prompt)` o
`(False, mensaje, "")`. Ejecuta los cinco helpers y reemplaza estos seis marcadores:

```text
{{TITULOS}}
{{NIVELES}}
{{INSTITUCIONES}}
{{LOCACIONES}}
{{MODALIDADES}}
{{PREGUNTA_USUARIO}}
```

Listas y pregunta se serializan como JSON. La sustitución se hace en una pasada
para no reinterpretar marcadores incluidos en los datos. Se rechazan preguntas
vacías y marcadores faltantes, duplicados o desconocidos.

Para inspeccionar el prompt manualmente, con el entorno activado:

```console
python -m helpers.prerag
```

También admite `python helpers/prerag.py`. El bloque `if __name__ == "__main__"`
llama directamente a `crea_prompt_rag(pregunta)`, sin argumentos de consola.
La variable `pregunta` contiene un ejemplo editable. Si tiene éxito, escribe
`helpers/salida.md` en UTF-8, reemplazando el contenido anterior. Si falla, no
lo escribe y finaliza con código 1. La función por sí misma no escribe archivos.

## Búsqueda RAG

`helpers.buscador_rag.buscar_ofertas(consulta, limite=10)` recibe los cinco filtros
normalizados y devuelve la tupla común con las ofertas y su cantidad para uso
interno. Admite límites entre 1 y 100. Usa el flujo adaptado de `consultador`:
verifica el servicio de embeddings y la dimensión del índice, genera el vector,
consulta Qdrant y prioriza coincidencias de carrera del catálogo activo.
Aplica los filtros de institución, ubicación, nivel y modalidad.

No carga modelos locales ni recurre a Hugging Face remoto. El servicio propio
de embeddings debe ser compatible con el espacio y dimensión usados al indexar
la colección. La búsqueda no modifica Qdrant y conserva los siete campos
originales de cada oferta para la segunda llamada a la LLM.

## Adaptador OpenAI, tokens y caché

`helpers.llm_openai.crea_prompt_pre_rag(pregunta: str)` construye el prompt,
llama a `https://api.openai.com/v1/responses` y devuelve un diccionario con
los filtros, `consumo_tokens` y `rendimiento` de la llamada. Su firma es
`tuple[bool, str, dict[str, Any]]`, para mantener la misma interfaz en futuros
módulos de otros proveedores.

`helpers.llm_openai.genera_respuesta_usuario(pregunta, ofertas)` conserva ese
mismo contrato y devuelve `respuesta`, `consumo_tokens` y `rendimiento`. El router
extrae ese último campo para publicarlo en el objeto raíz. Usa las reglas de
`helpers/prompt_respuesta_usuario.md`: redacta en castellano rioplatense y
Markdown, utiliza únicamente las ofertas recibidas y sus enlaces, y conserva
las condiciones de presencialidad y requisitos de los ciclos de complementación.

Usa JSON Schema estricto y valida la respuesta con los contratos comunes de
Pydantic para la normalización; la segunda llamada genera texto Markdown.
Cada solicitud tiene timeout de 60 segundos, límite de 4096 tokens de
salida, `store: false`, ninguna herramienta y ningún reintento automático.

Los consumos se leen de `usage`, nunca de estimaciones generadas por la LLM:

- `entrada`: todos los tokens de entrada.
- `salida`: todos los tokens de salida, incluidos los de razonamiento.
- `total`: entrada más salida.
- `entrada_cache`: subconjunto de la entrada recuperado de caché.
- `razonamiento`: subconjunto de la salida usado para razonamiento.

No sumar caché o razonamiento nuevamente al total. Estos campos son conteos,
no importes monetarios, y no desglosan por separado las escrituras de caché.

Para nombres de modelo que comienzan con `gpt-6` o `gpt-5.6`, el código configura
caché explícita después del catálogo: el prefijo incluye reglas y referencias,
y la pregunta variable queda después. Para otros modelos se omite esa configuración.
El aprovechamiento real se observa en `entrada_cache`; no se garantiza un acierto
en todas las llamadas.

Se registran mensajes INFO de inicio y fin de la llamada a OpenAI mediante
`uvicorn.error`; el fin también se registra si falla. Los errores llevan contexto
sin registrar headers de autorización, claves ni el contenido completo de la respuesta.
También se registra el inicio y fin de la consulta al RAG. Los logs propios y
los de Uvicorn incluyen fecha y hora, por ejemplo:

```text
2026-10-26 16:08:02 | INFO:     Waiting for application startup.
```

## Adaptador Qwen mediante Ollama

El módulo se llama **`helpers/llm_qewn.py`**, conservando el nombre solicitado.
Expone las mismas funciones que `llm_openai`, ambas con retorno
`tuple[bool, str, dict[str, Any]]`:

- `crea_prompt_pre_rag(pregunta: str)`: devuelve los cinco filtros y consumos.
- `genera_respuesta_usuario(pregunta: str, ofertas: list[dict[str, Any]])`:
  devuelve `respuesta` en Markdown y consumos.

Crear `llm/.env` con estos nombres de variables para Qwen:

```text
LLM_QWEN
LLM_QWEN_MODELO
```

El apunte `LLM.md` menciona `OLLAMA_BASE_URL` y `OLLAMA_MODEL`; el adaptador
no los usa como alias. La configuración se carga al invocar las funciones,
nunca al importar el módulo.

El transporte usa `POST /api/chat`, sin SDK adicional. Envía `stream: false`,
`think: false`, temperatura 0, contexto de 32768 tokens y un máximo de 4096
tokens generados. Cada llamada tiene timeout de 60 segundos, sin reintentos.
El modelo y la versión de Ollama deben admitir las opciones utilizadas.
Ver la [API de chat de Ollama](https://docs.ollama.com/api/chat).

La normalización reutiliza `prompt.md`, el catálogo preparado por `crea_prompt_rag`
y `ConsultaPreRag.model_json_schema()` en `format`. La redacción reutiliza
`prompt_respuesta_usuario.md` y valida los siete campos de cada oferta.
Las instrucciones locales van en `system`; catálogo, ofertas y pregunta van
en mensajes `user` separados. No se envían herramientas ni opciones de caché
propias de OpenAI. Ver [salidas estructuradas de Ollama](https://docs.ollama.com/capabilities/structured-outputs).

Solo se acepta una respuesta final con `done: true`, `done_reason: "stop"` y
texto no vacío de `message.content`. El campo `thinking` no se publica. Una
respuesta truncada o incompatible devuelve 502 y conserva los consumos válidos
recibidos. Los códigos HTTP de Ollama se conservan; timeout y conexión fallida
devuelven 502. Entradas inválidas devuelven 422, ausencia de ofertas o de filtros
404 y errores de configuración/preparación 500.

Los consumos se adaptan al contrato común sin estimarlos:

| Campo común | Fuente Ollama |
|---|---|
| `entrada` | `prompt_eval_count`. |
| `salida` | `eval_count`. |
| `total` | Suma de los dos conteos anteriores. |
| `entrada_cache` | `prompt_eval_cached_count`, si está presente; si no, `null`. |
| `razonamiento` | `null`: no hay un conteo separado informado en esta respuesta. |

Un desglose desconocido no se convierte en cero. Si cualquiera de las llamadas
tiene `null` en un desglose, el total de ese desglose también queda `null`.
Los demás conteos y el detalle por llamada se conservan. OpenAI sigue exigiendo
sus propios conteos de caché y razonamiento, con el comportamiento anterior.

**Qwen está seleccionado en el código del router.** Los adaptadores Phi y
OpenAI quedan disponibles para cambiarlo explícitamente según la sección de
selección del conector. Las variables por sí solas no cambian esa selección.

## Adaptador Phi mediante Ollama

El módulo **`helpers/llm_phi.py`** toma como base `llm_qewn.py` y expone las
mismas funciones `crea_prompt_pre_rag` y `genera_respuesta_usuario`, con retorno
`tuple[bool, str, dict[str, Any]]`. Reutiliza los contratos, prompts y métricas
compartidos; conserva JSON Schema para los filtros, Markdown para la respuesta,
consumos informados por Ollama y los mismos códigos HTTP.

Crear `llm/.env` con estos nombres de variables para Phi:

```text
LLM_PHI
LLM_PHI_MODELO
```

El adaptador usa sus propias variables, sin fallback a `LLM_QWEN` ni
`LLM_QWEN_MODELO`. La configuración se carga al invocar las funciones; importar
el módulo no carga archivos.

Conserva los parámetros de Qwen: `stream: false`, `think: false`, temperatura 0,
contexto de 32768 tokens, hasta 4096 tokens de salida y timeout de 60 segundos,
sin reintentos. El consumo de memoria y la latencia deben comprobarse con el
catálogo y el Mac de destino. La variante prevista es `phi4-mini`; otros modelos
deben admitir las opciones enviadas.
Ver [Phi-4-mini en Ollama](https://ollama.com/library/phi4-mini) y la
[API de chat](https://docs.ollama.com/api/chat).

Crear estas variables no activa el adaptador: cambiar el import según
[Selección del conector LLM](#selección-del-conector-llm) y reiniciar o
reconstruir/recrear el servicio. Qwen continúa seleccionado en el router.

## Idioma y protección frente a prompt injection

El prompt exige castellano rioplatense e ignora pedidos de cambiar el idioma.
Conserva nombres oficiales y siglas del catálogo, incluso en otros idiomas.

Las instrucciones locales se envían como `developer` en OpenAI y como `system`
en Ollama. Catálogo y pregunta se
envían en mensajes `user`, sin autoridad para modificar las reglas. La separación
se calcula sobre la plantilla local, antes de usar el contenido externo.
El encabezado `## Catálogo de referencia (listas JSON)` es parte de ese contrato:
si se cambia su estructura, debe ajustarse también el adaptador.

El prompt indica ignorar roles simulados, pedidos de revelar instrucciones o
secretos y órdenes para alterar la tarea. El esquema estricto y la validación
limitan el formato de salida. Estas medidas reducen el riesgo; no garantizan
inmunidad absoluta ni que toda interpretación semántica sea correcta.

## Pruebas

Desde `llm`, con el entorno activado:

```console
python -m tests.check_llm_openai
python -m tests.check_llm_qewn
python -m tests.check_llm_phi
python -m tests.check_buscador_rag
python -m tests.check_respuesta_usuario
python -m tests.check_router_llmrag
python -m tests.check_rendimiento
```

Son verificaciones aisladas: sustituyen la carga del `.env`, la configuración,
las respuestas del modelo y las conexiones. No llaman a OpenAI, Ollama, Qdrant ni al
servicio de embeddings reales, ni inspeccionan archivos de secretos.
Devuelven un resumen JSON y código de salida 0 en éxito o 1 en error.

Cubren contrato, consumos, separación de instrucciones y datos maliciosos simulados,
404 con filtros nulos, respuestas incompletas, rechazos, JSON inválido, errores HTTP,
fallos de preparación y excepciones del router. No son una evaluación de resistencia
del modelo real a ataques ni una prueba de conectividad con los servicios.
Las suites Qwen y Phi comprueban sus dos variables exactas de configuración,
salidas estructuradas, redacción, consumos desconocidos y errores de Ollama.
Phi también comprueba que no se usen las variables de Qwen como fallback. El router
verifica la suma con desgloses `null`, incluso cuando falla la segunda llamada.
La suite de rendimiento usa relojes y transportes simulados para verificar las
fórmulas, unidades, header de OpenAI, datos ausentes, duración cero, errores,
tiempos por etapa y posición de `rendimiento` en el JSON guardado y publicado.

Para verificar manualmente el estado del servidor:

```console
curl.exe http://127.0.0.1:8021/
```

Las pruebas reales del prompt y de `POST /llmrag/armador` deben ejecutarse localmente
por el usuario con su configuración. La API aún no tiene autenticación propia
ni persistencia de conversaciones. El router actual selecciona Qwen/Ollama;
las notas registran el acceso HTTP desde Windows, pero no sustituyen la prueba
de inferencia y del endpoint RAG completo ni la conectividad desde Docker.
