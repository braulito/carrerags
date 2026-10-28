# Motores y módulos de embeddings

Este módulo contiene los adaptadores intercambiables definidos en
[contracts.py](../contracts.py):

- `local.py`: modelo de embeddings de Sentence Transformers que corre en CPU.
- `embeddings_http.py`: cliente del servicio propio de embeddings, con identidad y vectores validados.
- `qdrant.py`: motor vectorial persistente inicial.
- `memory.py`: referencia no persistente para pruebas.
- `http.py`: transporte JSON para el motor y embeddings HTTP, sin redirecciones.
- `factories.py`: factorías de los motores incluidos.

## Alcance e integración

Estos adaptadores publican o recuperan vectores; no son conectores de una LLM
generativa. Qwen/Ollama y OpenAI pertenecen a la API
[llm](../../../llm/README.md), y la interfaz está en
[pagina](../../../pagina/README.md). Cambiar el conector generativo no cambia
automáticamente `EMBEDDING_PROVIDER`, `space` ni la dimensión del índice.

El arranque [ingesta](../../README.md) prepara `Settings` y lo entrega a las
factorías. No se necesita crear un `.env` adicional para este paquete.
Crear `ingesta/.env` con los nombres enumerados en el
[README de ingesta](../../README.md#configuración). Modelo, revisión,
normalización y dimensiones deben seguir siendo
compatibles entre ingesta, API y consultador.

## Modelo local incluido

Su variable de selección es `EMBEDDING_PROVIDER`.
El modelo público es
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Su revisión está
fijada en código. La primera ejecución puede descargar pesos; después se mantienen
en la caché local. No usa un servicio adicional ni requiere API key.

Instalar desde `ingesta`: `python -m pip install -r reqs.txt`.
El adaptador se importa solo al publicar; analizar el Excel no requiere sus
dependencias. El modelo desactiva código remoto y autenticación implícita, genera
vectores normalizados y comprueba dimensión, cantidad y valores finitos.

Cambiar el modelo o su revisión modifica `space`, por lo que los vectores
incompatibles no se reutilizan. Al configurar otros modelos conviene fijar
`EMBEDDING_REVISION` para evitar que pesos distintos se identifiquen como el
mismo espacio.

## Agregar otro módulo de embeddings

El paquete debe exportar una factoría tipada que reciba `Settings` y devuelva
`tuple[bool, str, Embedder | None]`. La variable de selección es
`EMBEDDING_PROVIDER`.

La factoría devuelve `(True, "ok", adaptador)` o
`(False, mensaje_descriptivo, None)`. El adaptador expone:

- `space: str`: identificador estable de implementación, modelo, revisión,
  dimensión y transformaciones relevantes para la compatibilidad.
- `dimensions: int`: dimensión positiva de sus vectores.
- `embed(texts: list[str]) -> tuple[bool, str, list[list[float]]]`: un vector finito
  no nulo por texto, en el mismo orden.

`Settings.embedding_model`, `Settings.embedding_revision` y
`Settings.dimensions` contienen las opciones genéricas. Si se configura una
dimensión, el registro exige que coincida con la declarada por el adaptador.

La ingesta no inventa vectores si el módulo falla. Cada módulo adicional
documenta sus dependencias, configuración y límites, sin registrar secretos ni
buscar archivos de configuración por su cuenta.

## Agregar un motor

Crear un paquete con una factoría `Settings -> tuple[bool, str, VectorStore | None]`
y seleccionarla mediante `VECTORIAL_PROVIDER`. La dirección llega
mediante `Settings.vectorial`, procedente de `VECTORIAL`. La autenticación del motor
se recibe separada en `Settings.vector_key`.

La selección importa la factoría y comprueba los métodos obligatorios. Los
módulos configurados son código de confianza instalado por el operador, nunca
valores obtenidos del Excel.

| Operación | Responsabilidad |
|---|---|
| `health()` | Comprobar disponibilidad y propagar errores. |
| `replace(points, space, dimensions)` | Sustituir el catálogo completo, sin acumular versiones, e informar fallos. |
| `search(vector, constraints, limit, space)` | Recuperación con filtros aplicados antes del límite. |
| `fetch(ids)` | Recuperar fichas por identificador. |

La ingesta usa `health` y `replace`. Las otras operaciones completan el contrato
intercambiable del motor y permiten reutilizarlo desde otros componentes.

`replace` retira las ofertas ausentes y mantiene un único catálogo en el motor.
En Qdrant elimina la colección anterior, crea la colección física con el nombre
configurado, carga los puntos inactivos y los habilita después de validar la cantidad.
Durante la reconstrucción no se garantiza disponibilidad. Si se pierde la confirmación
de habilitación, debe informar estado indeterminado. Los fallos no son éxitos vacíos.

`search` exige estado activo. La modalidad, gestión, acceso y restricciones de
presencialidad se aplican solo cuando `Constraints` las solicita. La elegibilidad
del perfil original se conserva como metadato y no excluye puntos de publicación
ni de las búsquedas generales. Si no puede
garantizar algún filtro, devuelve error. No filtrar después de una búsqueda ya
limitada. Rechazar espacios y dimensiones incompatibles.

`domain.query_filter` construye el filtro compartido por Qdrant, la lectura
paginada y la validación local. `Constraints.modality` admite `distancia`,
`semipresencial`, `hibrida`, `presencial` y `desconocida`. `secondary_only`
excluye títulos previos, accesos restringidos y títulos sin ingreso independiente;
no convierte los requisitos desconocidos en ingreso confirmado. `no_travel`
exige modalidad a distancia, exámenes remotos y prácticas remotas o no aplicables.

Los tipos específicos del motor se convierten dentro de su adaptador a `Point`,
`Hit` y diccionarios propios. Todas las funciones tienen parámetros tipados,
retorno de tres valores y excepciones capturadas como `e`, con contexto y detalle
en el log sin credenciales. El adaptador Qdrant requiere vectores con nombre,
índices de payload, consulta de puntos y eliminación de colecciones. La API de alias
solo se utiliza para retirar el alias que creó la versión anterior del componente.

## Dependencias, arranque y pruebas

Los motores incluidos usan biblioteca estándar. El adaptador local usa las dependencias de `reqs.txt`. El motor de memoria no conserva
datos entre ejecuciones y se usa desde Python o en pruebas.

Instalar las dependencias externas en el entorno elegido por el usuario y
ejecutar `python run.py` desde `ingesta`, sin argumentos adicionales.
Los indicadores `-I -S` se reservan para las pruebas aisladas, que preparan
explícitamente sus rutas de importación; no se usan en el arranque normal.

Desde la raíz: `python -I -S -X utf8 ingesta/tests/run_tests.py`.
Las pruebas están en `ingesta/tests/`; no necesitan cuentas ni servicios.
La factoría ficticia de `tests/support.py` se usa solamente en pruebas. El modelo local
y su carga se prueban con bibliotecas simuladas, sin descargar pesos ni abrir
archivos de configuración.

Cada módulo adicional debe documentar sus responsabilidades, configuración,
dependencias, contratos, límites y pruebas en su propio README. La validación
real se ejecuta por separado en el entorno del usuario.

## Servicio de embeddings HTTP incluido

`embeddings_http.py` implementa el contrato `Embedder` mediante los endpoints
`GET /health` y `POST /embeddings` de [embedding](../../../embedding/README.md).
Las variables son `EMBEDDING_PROVIDER` y `EMBEDDING_URL`. Solo requiere
biblioteca estándar y reutiliza `HttpTransport` con `Settings.timeout`.

La factoría exige el modelo y la revisión predeterminados y 384 dimensiones;
verifica su identidad en `/health`. Cada lote de hasta 15 textos se valida
contra el espacio y la norma L2 antes de entregar los vectores en orden.
En fallo devuelve una lista vacía con resultado falso, sin vectores parciales,
sin fallback local y conservando el estado HTTP en el mensaje del transporte.
Es el mismo adaptador para ingesta, consultador y reindexación.

La API mantiene su adaptación en `llm/helpers/rag/embeddings_http.py`, con el
mismo contrato e identidad. Los conteos de tokens y velocidades de Ollama u
OpenAI se calculan en `llm/helpers/rendimiento.py`; no describen el rendimiento
de estos adaptadores de vectores. Ver [comparativas.md](../../../comparativas.md)
para las mediciones del flujo de consulta.

Pruebas desde la raíz: `python -I -S -X utf8 embedding/tests/run_tests.py`.
La instalación de ingesta solo HTTP usa `ingesta/reqs-http.txt`.
