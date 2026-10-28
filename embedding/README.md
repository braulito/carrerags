# Servicio de embeddings de carrerags

Servicio HTTP para un Mac mini M4 con 16 GB. Ejecuta en CPU Linux ARM64 el modelo
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revisión
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. Construye y verifica el modelo con
Sentence Transformers; carga una sola instancia al iniciar el proceso HTTP y la
mantiene en memoria. No modifica Qdrant ni publica catálogos.

## Papel dentro del proyecto

El flujo completo incluye [ingesta](../ingesta/README.md), este servicio
`embedding`, la API [llm](../llm/README.md) y la interfaz
[pagina](../pagina/README.md). Ingesta y API usan este mismo
servicio: `ingesta` vectoriza las ofertas antes de publicarlas en Qdrant, y
`llm` vectoriza los criterios de búsqueda para consultar ese catálogo.
El modelo, la revisión, la dimensión y la normalización deben coincidir en
ambos recorridos.

La página llama únicamente a la API, que usa este servicio para vectorizar los
criterios interpretados. Qwen/Ollama es el conector generativo actual de la API;
OpenAI es una alternativa explícita. Ninguno reemplaza a MiniLM ni modifica sus
vectores. Las velocidades de generación de [comparativas.md](../comparativas.md)
corresponden a esas LLM, no a este servicio de embeddings.

El servicio escucha en el puerto **8081**. La API de consultas escucha en
**8021** y Qdrant usa su API HTTP en **6333** en la configuración de ejemplo.
Levantar Qdrant y `embedding` antes de publicar con `ingesta`; después se puede
usar `llm`. La ingesta se ejecuta para publicar o actualizar el catálogo,
mientras que `embedding` debe permanecer disponible durante las consultas.

## Configuración del servicio

**Este componente no necesita un archivo `.env` ni claves de OpenAI.** La
identidad del modelo está fijada en el código y el despliegue se define en
`compose.yaml`, `Dockerfile` y `nginx.conf`. El script evita que Compose cargue
automáticamente archivos `.env`.

Cada cliente debe crear su archivo: `ingesta/.env` para publicar y `llm/.env`
para consultar. Los nombres de variables se enumeran en la sección de integración.

## Instalación y arranque en el Mac

Desde la raíz del repositorio, con Docker Desktop para Apple Silicon instalado
e iniciado, ejecutar el instalador:

```sh
bash embedding/install.sh
```

También se puede ejecutar `bash install.sh` desde `embedding`. El script resuelve
sus rutas respecto de su propia ubicación. Comprueba macOS y Docker Linux ARM64,
valida Compose y NGINX, prepara las imágenes que falten, inicia ambos contenedores
y comprueba el puerto publicado y `/health` desde el Mac. Si la imagen del modelo
ya está instalada, la reutiliza; no vuelve a descargar los pesos en cada ejecución.
Los errores terminan con código distinto de cero y no anuncian instalación exitosa.
El script no instala Docker Desktop, no modifica Qdrant y no carga archivos `.env`.

```sh
bash embedding/install.sh --rebuild  # Actualizar el código de la imagen del modelo.
bash embedding/install.sh --offline  # Usar únicamente las dos imágenes locales ARM64.
bash embedding/install.sh --help
```

La primera instalación necesita Internet. `--offline` no construye ni descarga
imágenes y falla si falta alguna. Los contenedores usan los pesos locales durante
la ejecución. La regla `.gitattributes` conserva finales de línea LF para el script
al clonar el repositorio desde Windows o macOS; invocarlo con `bash` evita depender
del permiso ejecutable en Git.

Para realizar los pasos manualmente:

Instalar Docker Desktop para Apple silicon, con Compose v2 y BuildKit. Reservar
al menos 6 GB para la VM de Docker si también corre Qdrant; el contenedor de
embeddings tiene un límite de 4 GB y 4 CPU. Estos valores son límites iniciales,
no una medición de rendimiento del M4. Mantener espacio para las capas de PyTorch,
el tokenizador y los pesos (~471 MB solo los pesos).

Los pasos manuales requieren preparar `COMPOSE_DISABLE_ENV_FILE` en el entorno
de la terminal. El instalador gestiona esa variable sin configuración manual.
Desde la raíz del repositorio, en una terminal nativa del Mac:

```sh
cd embedding
docker compose -f compose.yaml build
docker compose -f compose.yaml up -d --wait
docker compose -f compose.yaml ps
curl --fail-with-body http://localhost:8081/health
```

La construcción necesita Internet para la imagen base, PyPI, el índice oficial
CPU de PyTorch y Hugging Face. `download_model.py` descarga únicamente los archivos
necesarios de la revisión indicada y valida una inferencia local durante el build.
Los pesos quedan en `/opt/models/minilm` dentro de la imagen; no hay volúmenes de
modelos ni pesos dentro de Git. `requirements.txt` fija las dependencias directas
y transitivas de ejecución para Python 3.11/Linux ARM64; `pip check` valida el cierre.
La variante `torch==2.8.0+cpu` usa una rueda ARM64, sin CUDA.

`platform` y `build.platforms` seleccionan `linux/arm64`. El Dockerfile comprueba
`BUILDARCH` y `TARGETARCH` en una etapa nativa y rechaza constructores x86/amd64;
no usa emulación. Comprobar la imagen y el contenedor:

```sh
docker image inspect carrerags-embeddings:arm64 --format '{{.Os}}/{{.Architecture}}'
docker compose -f compose.yaml exec embeddings uname -m
```

Se espera `linux/arm64` y `aarch64`. Si falla el control de arquitectura, elegir
un constructor BuildKit ARM64 nativo. Para reiniciar con la imagen ya construida:
`docker compose -f compose.yaml up -d --no-build --pull never --wait`.
Para detener: `docker compose -f compose.yaml down`.

### Migrar el puerto publicado de la versión anterior

En algunos Docker Engine, un contenedor conectado únicamente a una red interna
no publica sus puertos aunque estén declarados. El síntoma es `healthy` con
`8081/tcp` en `ps`, pero sin una correspondencia de host y con conexión rechazada
desde el Mac. El healthcheck anterior solo probaba loopback dentro del contenedor.

Actualizar `embedding/compose.yaml` y el nuevo `embedding/nginx.conf` en el Mac.
Desde `embedding`, con `COMPOSE_DISABLE_ENV_FILE` preparada en el entorno, ejecutar:

```sh
docker compose -f compose.yaml up -d --no-build --force-recreate --wait
docker compose -f compose.yaml ps
curl --fail-with-body http://localhost:8081/health
python3 -I -S tests/verify_ports.py
```

Se reutiliza la imagen existente del modelo. La primera vez Docker descarga
únicamente la nueva imagen de NGINX si no está disponible. Después, para recrear
sin descargas usar también `--pull never`. `gateway` debe aparecer con
`0.0.0.0:8081->8081/tcp` (y eventualmente su equivalente IPv6). Es correcto que
`embeddings` no tenga un puerto publicado: permanece aislado detrás del gateway.
`verify_ports.py` comprueba la publicación real con una inspección limitada a
puertos y hace una solicitud HTTP desde el host. No carga configuración protegida.

Desde Windows, `curl.exe --fail-with-body http://macmini:8081/health` debe devolver
el mismo JSON antes de ejecutar `python run_e.py`. No hace falta cambiar URLs ni
volver a publicar datos en Qdrant.

## Ejecución local sin servicios externos

El runtime pasa una ruta absoluta a `SentenceTransformer`, con
`local_files_only=True`, `trust_remote_code=False`, `token=False` y safetensors.
Activa el modo sin conexión mediante `HF_HUB_OFFLINE` y `TRANSFORMERS_OFFLINE`,
y desactiva telemetría y tokens
implícitos antes de importar las bibliotecas. Si faltan pesos o su identidad no
coincide, el proceso termina con código 1 antes de abrir el puerto.

Compose mantiene el contenedor `embeddings` únicamente en la red `offline`,
marcada `internal`. Un segundo contenedor ligero, `gateway` (NGINX ARM64), conecta
esa red con la red de entrada y publica `8081:8081` en el Mac. El modelo conserva
el aislamiento de salida y una sola instancia en memoria. El gateway reenvía
únicamente al backend fijo `embeddings:8081`; no carga modelos. Ambos ejecutan
como usuarios sin privilegios, con sistemas de archivos de solo lectura y `/tmp`
temporal. Se monta únicamente `nginx.conf`, de solo lectura, en el gateway.
No consulta Hugging Face al arrancar ni durante las solicitudes. El healthcheck
solo conecta a loopback. No se utiliza Metal/MPS dentro de Docker.

El contexto de construcción es únicamente `embedding`; `.dockerignore` permite
solo el código y los requisitos necesarios y excluye explícitamente `.env`,
`.env.*` y `*.env` a cualquier profundidad. No hay `env_file`, montaje del
repositorio ni carga dotenv en el servicio. `COMPOSE_DISABLE_ENV_FILE` controla
la lectura automática del archivo por Compose; mantenerlo exportado para los
comandos indicados. No se necesitan claves para descargar este modelo público.

## API y contratos

`GET /health` devuelve HTTP 200 únicamente con el modelo disponible:

```json
{
  "resultado": true,
  "mensaje": "ok",
  "salida": {
    "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
    "dimensions": 384,
    "space": "sentence-transformers:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2:e8f8c211226b894fcb81acc59f3b34ba3efd5f42:normalized-v1:384"
  }
}
```

`POST /embeddings` recibe un objeto con una lista de textos:

```sh
curl --fail-with-body http://localhost:8081/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"texts":["Dónde estudiar ingeniería", "Profesorados de música"]}'
```

La respuesta HTTP 200 tiene `resultado: true`, `mensaje: "ok"` y
`salida: {"vectors": [[...], [...]], "dimensions": 384, "space": "..."}`.
Cada vector contiene 384 números finitos, con norma L2 igual a 1 (tolerancia
`1e-4`). Se preservan orden y duplicados. No se recortan espacios del texto;
se mantiene el tokenizador y el truncado original del modelo a 128 tokens.
No se aplican cuantización, instrucciones ni prefijos.

El espacio coincide exactamente con `ingesta/carrerags_ingesta/adapters/local.py`.
Por eso la caché y el índice existentes siguen siendo compatibles y cambiar
solo de proveedor no requiere reindexar. Puede haber pequeñas diferencias de
redondeo por versión de biblioteca, CPU o tamaño de lote.

Límites por solicitud: 1 MiB de JSON, 1–128 textos, hasta 16000 caracteres por
texto y 250000 en total. El modelo procesa sublotes de 16 textos. Se admite una
inferencia simultánea para acotar la memoria; otra solicitud de embeddings
recibe 503. No se acumula una cola de inferencias ni se duplican modelos en
workers. El healthcheck continúa atendiendo mientras se infiere.

| HTTP | Significado |
|---|---|
| 400 | JSON, longitud o transferencia inválidos. |
| 404 | Ruta inexistente. |
| 405 | Método incorrecto para las dos rutas. |
| 411 | Falta Content-Length. |
| 413 | Cuerpo mayor que 1 MiB. |
| 415 | Falta application/json. |
| 422 | Lista o textos fuera del contrato. |
| 500 | Fallo de inferencia o vector inválido. |
| 503 | Modelo no disponible o inferencia ocupada. |

Los fallos HTTP publican `{"resultado": false, "mensaje": "descripción", "salida": {}}`
y conservan el código HTTP. Las funciones propias devuelven siempre
`(resultado, mensaje, dato)`: éxito `(True, "ok", dato)`, fallo
`(False, mensaje, vacío)`, con tipos y excepciones registradas como `e`.
Los hooks de `http.server` conservan también la tupla interna; la biblioteca
ignora su retorno y envía la respuesta escrita por el adaptador.

## Integración con ingesta y llm

Para `ingesta`, el adaptador es
`ingesta/carrerags_ingesta/adapters/embeddings_http.py`. Crear `ingesta/.env`
con estos nombres de variables para el motor y el servicio:

```text
VECTORIAL
VECTORIAL_NAMESPACE
EMBEDDING_PROVIDER
EMBEDDING_URL
EMBEDDING_DIMENSIONS
HTTP_TIMEOUT
```

La lista completa de nombres está en el
[README de ingesta](../ingesta/README.md#configuración). No es necesario instalar
las bibliotecas ML en los clientes HTTP. Para una instalación de ingesta solo
HTTP: `python -m pip install -r reqs-http.txt` desde `ingesta`.

La API `llm` incluye su propio adaptador en
`llm/helpers/rag/embeddings_http.py`, derivado del mismo contrato. Usa HTTP como
proveedor de embeddings y no carga un modelo local. Crear `llm/.env` con los
nombres correspondientes:

| Grupo | Nombres de variables |
|---|---|
| Compartidas | `VECTORIAL`, `VECTORIAL_NAMESPACE`, `EMBEDDING_URL`, `HTTP_TIMEOUT`. |
| Qwen | `LLM_QWEN`, `LLM_QWEN_MODELO`. |
| Phi | `LLM_PHI`, `LLM_PHI_MODELO`. |
| OpenAI | `API_KEY_LLM`, `MODELO`. |

En `llm` no se configuran `EMBEDDING_PROVIDER` ni `EMBEDDING_DIMENSIONS`: el
flujo selecciona HTTP y verifica la identidad y las 384 dimensiones del servicio.
Cambiar el conector generativo no requiere reindexar si se conserva el espacio
MiniLM. Ver [configuración y despliegue de llm](../llm/README.md).

### Consultador como herramienta auxiliar

`consultador` conserva el cliente de pruebas original; no es necesario para
ejecutar la API `llm`. Los nombres de campos de integración en
`consultador/config.json` son:

```text
EMBEDDING_PROVIDER
EMBEDDING_URL
EMBEDDING_DIMENSIONS
```

Con el adaptador HTTP, el consultador usa únicamente biblioteca estándar, además
de los módulos del repositorio; no necesita instalar `consultador/reqs.txt`.
Mantener los demás campos existentes. `reindexar.py` reutiliza esta selección
cuando el usuario lo ejecuta. Desde cada componente, ejecutar `python run.py`
como siempre. El cliente debe poder alcanzar el servicio por la red local.

### Validación compartida por los clientes

Los adaptadores HTTP consultan `/health` y verifican modelo, revisión, espacio y dimensión.
El cliente divide entradas grandes en lotes de 15 textos, preserva su orden,
valida cada respuesta y su norma y descarta toda salida parcial si falla un lote.
Propaga el estado HTTP en el mensaje de error usando el transporte compartido;
no sustituye fallos por listas vacías exitosas ni inicia un modelo local.
`HTTP_TIMEOUT` se aplica por llamada. Ante 503, el
operador puede reintentar la operación; el adaptador no reintenta automáticamente.
El puerto está pensado para la red local, sin autenticación ni TLS incorporados.
El gateway conserva los códigos y cuerpos del backend. Sus propios errores de
longitud, conexión o timeout devuelven JSON con códigos 413, 502 y 504,
respectivamente. El nombre del backend se resuelve mediante DNS de Docker para
admitir recreaciones del contenedor.

## Pruebas y verificación

Desde la raíz, con Python 3.10 o superior, sin instalar dependencias:

```sh
python -I -S -X utf8 embedding/tests/run_tests.py
python -I -S -X utf8 ingesta/tests/run_tests.py
python -I -S -X utf8 consultador/tests/run_tests.py
```

Usan modelos y descargas simulados, configuración ficticia y un servidor efímero
en loopback. No abren archivos protegidos, no necesitan pesos ni conectan servicios
reales. Cubren carga local única, identidad fijada, normalización, orden y duplicados,
lotes, errores HTTP, fallos parciales, validación de entradas y selección en
ingesta y consultador. Las suites existentes cubren también la ingesta y
reindexación. Las verificaciones específicas de la API y su adaptador de búsqueda
se documentan en el [README de llm](../llm/README.md).

Tras construir la imagen en el Mac, verificar pesos reales y ausencia de red,
desde la raíz del repositorio:

```sh
docker run --rm -i --network none --read-only --tmpfs /tmp:size=128m \
  --memory 4g --cpus 4 --platform linux/arm64 \
  --entrypoint python carrerags-embeddings:arm64 - < embedding/tests/verify_image.py
```

La prueba confirma ARM64, carga local, 384 dimensiones, norma y orden con textos
reales, sin red Docker y bloqueando además conexiones Python. No descarga ni monta
modelos. Un resultado correcto imprime `resultado: true` y termina con código 0.
La construcción ya incluye otra inferencia local para detectar artefactos incompletos.
Desde otro equipo verificar también `curl --fail-with-body http://macmini:8081/health`
y repetir el POST anterior usando ese host. Para observar arranque y errores:
`docker compose -f compose.yaml logs --tail 100 embeddings` desde `embedding`.

Las pruebas simuladas no sustituyen la comprobación del modelo y los puertos
reales. Al instalar o actualizar en el Mac, usar el healthcheck y la verificación
de imagen indicados arriba.

## Referencias

- [Revisión exacta del modelo](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/tree/e8f8c211226b894fcb81acc59f3b34ba3efd5f42).
- [Carga local y normalización en Sentence Transformers](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html).
- [Modo offline de Hugging Face](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables).
- [Red interna de Compose](https://docs.docker.com/reference/compose-file/networks/#internal).
- [Publicación omitida en redes exclusivamente internas](https://github.com/moby/moby/discussions/53256).
- [Desactivar carga automática dotenv de Compose](https://docs.docker.com/compose/how-tos/environment-variables/envvars/#compose_disable_env_file).
- [Ruedas CPU oficiales de PyTorch](https://download.pytorch.org/whl/cpu/torch/).
