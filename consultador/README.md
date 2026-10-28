# Consultador de carreras

Interpreta condiciones de una pregunta mediante reglas, busca ofertas en Qdrant
y guarda sus siete campos originales en `respuesta.json` (`run.py`) o
`salidas/local/<pregunta>.json` (`run_e.py`). Usa embeddings locales
o el servicio HTTP compartido para ordenar, sin un LLM generativo ni una API de conversación.

## Arranque

Requiere Python 3.10 o superior y conservar `consultador` e `ingesta` como carpetas
hermanas de este repositorio: reutiliza los adaptadores de embeddings y búsqueda
de `ingesta`, sin ejecutar su arranque ni sus operaciones de publicación.

Desde `consultador`, con el entorno virtual elegido activado:

```console
python -m pip install -r reqs.txt
python run.py
```

Antes de ejecutar, crear o actualizar `config.json` con estos nombres de campos:

```text
PREGUNTA
VECTORIAL
VECTORIAL_NAMESPACE
LIMITE
```

`PREGUNTA` es el texto de búsqueda y `LIMITE` la cantidad máxima de resultados,
entre 1 y 100. La configuración y la salida se ubican junto a `run.py`, aunque se
ejecute desde otro directorio. No se leen archivos `.env` ni variables de entorno
para configurar la consulta con `run.py`. El cliente `run_e.py` usa el `.env`
local y `local_pregunta.json`, como se explica en la sección del Mac mini.

## Catálogo completo y filtros de la pregunta

`TOTAL.json` contiene las 574 ofertas de la hoja `Todas las carreras`, en una
lista con el objeto `original` y sus siete campos por oferta, conservando los
valores y el orden del Excel. Es la fuente para analizar el catálogo y comparar
las salidas: usar este JSON en lugar de abrir el Excel. La exportación es una
instantánea y no se actualiza automáticamente cuando cambia el origen.

La ingesta publica todas las ofertas activas del Excel. Con el archivo incluido
son 574 ofertas y 50 profesorados (38 títulos distintos). Una pregunta sin
condiciones consulta todas las modalidades, gestiones y requisitos de ingreso.
La salida conserva una entrada por oferta e institución; no agrupa títulos.
Configurar `LIMITE: 100` para consultas amplias. La búsqueda en todos los campos
encuentra ahora 51 ofertas para `profesorado`: 50 por título y una adicional
que lo menciona en otro campo.

| Pregunta | Condiciones aplicadas |
|---|---|
| `Dónde puedo estudiar profesorado` | Todas las ofertas de profesorado. |
| `profesorados online` | Modalidad a distancia, sin filtro de ingreso o gestión. |
| `profesorados públicos y online` | Gestión pública y modalidad a distancia. |
| `profesorado en una universidad privada` | Gestión privada. |
| `profesorado semipresencial` | Solo semipresencial. |
| `profesorado híbrido` | Solo híbrido. |
| `profesorado presencial` | Solo presencial. |
| `profesorado sin título previo` | Sin requisito de título superior, acceso restringido ni título intermedio sin ingreso independiente. |
| `profesorado, tengo solo secundario` | El mismo filtro de ingreso anterior. |
| `profesorado sin viajar` | Cursada a distancia y exámenes/prácticas remotos confirmados; prácticas no aplicables también se admiten. |
| `públicas y online` | Todas las carreras que cumplen ambas condiciones. |

También se reconocen `a distancia`, `virtual`, `no puedo viajar`, y los plurales
de tipos como `profesorados` e `ingenierías`. Las condiciones pueden combinarse;
las contradicciones se informan como error. Los conectores internos de títulos
como `Ciencias de la Educación` se conservan. `Administración Pública` y
`Contador Público` se interpretan como títulos, sin convertirlos en filtros de
gestión. Para una gestión inequívoca usar `en universidad pública/privada`.

`Online` no significa que los exámenes o prácticas sean remotos. `Sin título
previo` permite requisitos desconocidos y los conserva como pendientes; no
equivale a ingreso con secundario confirmado. Las reglas no interpretan lenguaje
libre arbitrario, sinónimos de carreras ni todas las negaciones. Las ubicaciones
se buscan en el campo de lugar, como se explica a continuación.

## Actualizar la colección anterior

Las colecciones publicadas con el criterio anterior contenían solo 318 ofertas.
Para migrarlas hay que reconstruirlas e incorporar las 574. Desde `consultador`, usando el
entorno que tiene instaladas las dependencias:

```console
python reindexar.py
python run.py
```

`reindexar.py` usa la conexión y el modelo de `config.json`, el único Excel de
`ingesta`, el estado `ingesta/.state` y el reporte `ingesta/.artifacts`. No carga
`.env`. Reemplaza la colección existente con el mecanismo de la ingesta; durante
esa reconstrucción el catálogo no está disponible. Los vectores se preparan
antes de eliminar la colección anterior y se reutiliza la caché compatible.
También se puede ejecutar el arranque habitual `ingesta/run.py` en el entorno
del usuario. El consultador detecta puntos del esquema anterior y pide actualizar
la ingesta cuando los encuentra.

## Modelo y conexión

Usa el mismo modelo, revisión, normalización y nombre de vector que la ingesta:
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revisión
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 dimensiones y CPU. La primera
ejecución puede descargar pesos públicos; no requiere OpenAI ni una API de LLM.

Si se cambió el modelo en la ingesta, configurar también `EMBEDDING_MODEL`,
`EMBEDDING_REVISION` y, opcionalmente, `EMBEDDING_DIMENSIONS` como textos en
`config.json`. `HTTP_TIMEOUT` también se admite como texto. Si el servidor
requiere autenticación, el adaptador admite el campo
`VECTORIAL_API_KEY`; no publicar configuraciones que contengan credenciales.
Un modelo incompatible con el índice produce un error y exige alinear la
configuración con la ingesta.

La consulta exige ofertas activas y aplica únicamente los filtros solicitados.
Además de la búsqueda vectorial, lee el catálogo filtrado con `points/scroll`,
sin descargar vectores y recorriendo todas las páginas. La selección se realiza
en todos los campos originales; conserva el orden vectorial de las ofertas que
aparecen en esa búsqueda y añade las restantes por identificador estable.

## Búsqueda en todos los campos y por lugar

Tanto `run.py` como `run_e.py` buscan en los siete campos originales: título,
lugar donde se cursa, nivel, descripción, tipo de cursada, gestión y URL.
Ignoran tildes, mayúsculas y signos; respetan palabras completas. Todos los
términos significativos deben aparecer en la misma oferta, aunque estén en
campos diferentes. Se omiten conectores como `de`, `en` y `la`.

| Pregunta | Comportamiento |
|---|---|
| `¿Qué puedo estudiar en Quilmes?` | Busca Quilmes en el lugar donde se cursa. |
| `¿Qué puedo estudiar en Quilmes online?` | Aplica también modalidad a distancia. |
| `ingeniería en informática en Quilmes` | Combina los términos de la carrera con el lugar reconocido en el catálogo filtrado. |
| `software` | Encuentra la palabra también en descripciones. |
| `UNQ` | Busca la sigla también en la institución. |
| `on line` | Aplica el mismo filtro que `online` y `a distancia`. |

El campo `Lugar donde se cursa` reúne institución y ubicación. Por eso Quilmes
también encuentra la Universidad Nacional de Quilmes, cuya ubicación declarada
es Bernal. No se hace geocodificación ni se confirma una sede física o vacantes.
En preguntas generales `qué puedo estudiar en ...`, una mención del lugar solo
en la descripción no alcanza. En consultas con carrera, se reconoce un
complemento final `en ...` cuando aparece en el lugar de alguna oferta del
catálogo filtrado. Nombres como `Ingeniería en Informática` siguen siendo
búsquedas por términos si no identifican un lugar.

Una búsqueda por título puede incluir ahora ofertas que mencionan ese término
en otro campo. Los términos de una consulta específica deben estar presentes:
no se eliminan para rellenar la lista con carreras afines. Sin coincidencias
se guarda `[]`; un fallo de lectura o de servicio se informa como error.

No se cambiaron el modelo ni el texto de los vectores existentes. Esta ampliación
textual no requiere reindexar ni usar un LLM. Los embeddings siguen aportando
el orden entre los resultados recuperados por Qdrant. No se introdujeron
sinónimos automáticos como `computación` = `informática` o `magisterio` =
`profesorado`, ni interpretación libre de cualquier pregunta o negación.
`LIMITE` sigue siendo un máximo entre 1 y 100, no la cantidad total disponible.

## Límites observados al analizar las salidas

Las comparaciones de `salidas/local` se realizan contra `TOTAL.json`. Los
archivos guardados pueden corresponder a distintas versiones del consultador:
no incluyen la pregunta, los puntajes, la fecha ni la versión del programa como
metadatos. El nombre del archivo sirve como referencia de la búsqueda, pero no
demuestra con qué configuración se ejecutó.

Buscar en todos los campos amplía la cobertura, pero una coincidencia textual
no garantiza que la oferta responda a la intención de la persona:

| Caso | Comportamiento actual y límite |
|---|---|
| `ingeniería` | Encuentra las seis ingenierías y otras ofertas que mencionan Ingeniería en una descripción o URL: 13 coincidencias en `TOTAL.json`. |
| `profesorado` | Encuentra 51 ofertas; una es Gestión Cultural porque la institución se llama Instituto Profesorado de Arte. |
| `computación` | Encuentra una carrera docente que contiene esa palabra; no amplía automáticamente a Informática o Sistemas. |
| `qué puedo estudiar para ser ingeniero` | No transforma la profesión deseada en una búsqueda de Ingeniería. Puede devolver `[]`. |
| `qué puedo estudiar para ser maestro` | No relaciona automáticamente maestro con las carreras docentes apropiadas. Puede devolver `[]`. |
| `ser lincenciado` | No corrige la escritura ni interpreta licenciado como un tipo de titulación. |

Una lista vacía puede deberse a una formulación no reconocida, además de la
ausencia de coincidencias. No demuestra por sí sola que el catálogo carezca de
ofertas relacionadas. Del mismo modo, una mención de Ingeniería en el nombre
de una facultad o en una URL no convierte una tecnicatura en una ingeniería.

`online` y `a distancia` aplican el mismo filtro, pero el embedding recibe la
pregunta original. Pueden cambiar el orden y, al limitar a 100, la selección de
ofertas. Con las reglas actuales, `TOTAL.json` contiene 491 ofertas clasificadas
como a distancia. `on line` ya se reconoce como equivalente: una salida anterior
vacía debe regenerarse para evaluar el comportamiento actualizado.

## Flujo con LLM implementado en la API

La interpretación y redacción generativas ya están implementadas en
[llm](../llm/README.md), con interfaz en [pagina](../pagina/README.md).
El consultador conserva sus reglas locales y sus clientes `run.py` y `run_e.py`;
no llama a esas LLM ni se necesita para ejecutar la API.

```text
Pregunta en pagina → API llm → LLM interpreta cinco filtros
                    → embeddings HTTP + Qdrant recuperan ofertas
                    → LLM redacta → pagina presenta Markdown
```

El contrato implementado de normalización tiene exactamente cinco campos:
`carrera`, `nivel_educativo`, `institucion`, `ubicacion` y `modalidad`, cada uno
como texto o `null`. La carrera incluye el tipo de titulación cuando se solicita.
La API conserva también la pregunta original. No publica campos separados de
gestión, título previo o ausencia de viajes en ese contrato; no asumir que todas
las condiciones que entiende el consultador están disponibles como filtros de
la API. Ver [contrato de llm](../llm/README.md#contrato-e-interpretación).

El router actual usa `helpers.llm_qewn` con `LLM_QWEN` y `LLM_QWEN_MODELO`.
OpenAI queda disponible mediante un cambio explícito a `helpers.llm_openai`,
usando `API_KEY_LLM` y `MODELO`. No hay fallback automático ni selector de LLM
implementado en la página. La selección generativa no cambia el modelo MiniLM
de los embeddings ni obliga por sí sola a reindexar.

El endpoint `POST /llmrag/armador` recibe `pregunta` y responde con
`resultado`, `pregunta`, `mensaje`, `rendimiento` y `salida`. Si todos los filtros
quedan en `null`, devuelve 404 sin buscar; si se ejecuta la búsqueda y no hay
ofertas, también devuelve 404 con otro mensaje. La página muestra el mismo aviso
de ausencia en ambos casos. Una lista vacía del consultador o un 404 de la API
no demuestran que una carrera no exista fuera del catálogo.

Las mediciones y los fallos de fidelidad observados se documentan en
[comparativas.md](../comparativas.md) y en el
[análisis de calidad](../llm/ANALISIS_LLM_20261027.md). Los JSON del consultador
conservan ofertas originales; no contienen las métricas de rendimiento de la API.
Una interpretación o redacción exitosa no garantiza precisión semántica.

Para todos los análisis se mantiene [TOTAL.json](TOTAL.json) como fuente. Es una
exportación y no se regenera automáticamente; exportar de nuevo desde Excel
requiere una solicitud explícita del usuario.

## Salida y contrato

`respuesta.json` y los archivos `salidas/local/<pregunta>.json` contienen una lista. Cada resultado conserva los valores de
Qdrant, sin generar ni abreviar textos y sin agregar puntajes ni metadatos:

```json
[
  {
    "original": {
      "Título": "Ejemplo de carrera",
      "Lugar donde se cursa": "Institución de ejemplo — Argentina",
      "Nivel": "Grado",
      "Descripción": "Descripción original completa",
      "Tipo de cursada": "Online",
      "Pública/Privada": "Privada",
      "URL": "https://example.org/carrera"
    }
  }
]
```

Una consulta sin coincidencias guarda `[]`. Un fallo de configuración, del modelo,
de Qdrant o de validación se informa como error; no se transforma en una lista
vacía exitosa. Si falla una ejecución, el archivo de una ejecución anterior se
conserva: revisar siempre el estado y el código de salida del proceso.

Las funciones devuelven `(resultado, mensaje, dato)`: éxito `(True, "ok", dato)`;
fallo `(False, mensaje, vacío)`. La consola publica JSON con `resultado`, `mensaje`
y `salida` (ruta y cantidad si tuvo éxito). El código de proceso es 0 en éxito y
1 en error. El archivo de salida se reemplaza mediante un archivo temporal completo.

## Pruebas

Desde la raíz del repositorio:

```console
python -I -S -X utf8 consultador/tests/run_tests.py
```

Desde `consultador` se puede usar `python -I -S -X utf8 tests/run_tests.py`.
Las pruebas usan configuración ficticia, un modelo simulado, respuestas HTTP
simuladas y carpetas temporales. No cargan archivos protegidos, descargan pesos
ni se conectan con Qdrant real. Cubren la regresión de Abogacía: siete títulos
correctos fuera de los primeros resultados vectoriales, exclusión de carreras
ajenas, tildes, mayúsculas, límites, paginación y errores de lectura del catálogo.
Verifican también la búsqueda general de Ingeniería con y sin tilde, sus seis
especialidades, búsquedas específicas y la exclusión de títulos de otro tipo.
También comprueban que una consulta de Medicina ausente reemplace la salida
anterior por `[]`, y que Medicina se recupere cuando sí exista aunque no aparezca
entre los primeros resultados vectoriales. Las preguntas sin título reconocido
tampoco producen ofertas ajenas. La ejecución real se hace con `python run.py`
en el entorno del usuario.

Las pruebas nuevas cubren condiciones individuales y combinadas, preguntas solo
con filtros, ausencia de filtros predeterminados, contradicciones, preservación
de títulos como Administración Pública, detección del catálogo anterior y el
arranque de reindexación con configuración ficticia. Usan `TOTAL.json`
contra un transporte simulado, sin abrir el Excel. Verifican los 51 resultados
de profesorado al buscar en todos los campos y el cambio de cantidad al pedir
modalidad e ingreso. También cubren coincidencias en cada uno de los siete
campos, términos repartidos entre campos, Quilmes, ubicaciones inexistentes y
la equivalencia entre `online`, `on line` y `a distancia`.

Referencias: [consulta de puntos en Qdrant](https://api.qdrant.tech/api-reference/search/query-points),
[lectura paginada del catálogo](https://api.qdrant.tech/api-reference/points/scroll-points)
y [Sentence Transformers](https://sbert.net/docs/package_reference/sentence_transformer/model.html).

## Embeddings mediante el Mac mini

El cliente `run_e.py` usa el [servicio Docker ARM64](../embedding/README.md)
del Mac mini. No descarga ni carga el modelo en el equipo cliente.

Desde `consultador`, instalar las dependencias:

```console
python -m pip install -r reqs_e.txt
```

Crear **`consultador/.env`**, junto a `run_e.py`, con estos nombres de variables:

```text
VECTORIAL
VECTORIAL_NAMESPACE
VECTORIAL_API_KEY
EMBEDDING_URL
HTTP_TIMEOUT
```

Este cliente lee la pregunta de `local_pregunta.json`, con los campos
`PREGUNTA` y `LIMITE` (entre 1 y 100; 100 si se omite):

```json
{
  "PREGUNTA": "¿Dónde puedo estudiar profesorado online?",
  "LIMITE": 100
}
```

Comprobar el servicio y ejecutar la consulta:

```console
curl --fail-with-body http://macmini:8081/health
python run_e.py
```

La salida se guarda en `salidas/local`, dentro de `consultador`, usando el texto
de `PREGUNTA` como nombre y la extensión `.json`. La carpeta se crea si no existe.
Por ejemplo, `¿qué puedo estudiar en Quilmes?` genera
`salidas/local/qué puedo estudiar en Quilmes.json`.

Se conservan espacios, tildes y mayúsculas. Se eliminan `¿`, los caracteres no
permitidos por Windows (`< > : " / \\ | ?`) y caracteres de control; se recortan
puntos y espacios en los extremos. Nombres reservados como `CON` se prefijan
con `_`; si no queda texto se usa `consulta.json`. Para preguntas largas se
recorta el nombre y se añade una huella estable de la pregunta.

Si el nombre resultante ya existe, se reemplaza sin pedir confirmación mediante
un archivo temporal completo. Dos preguntas que producen el mismo nombre
adaptado comparten el archivo; Windows también suele ignorar las diferencias
entre mayúsculas y minúsculas. Una consulta sin coincidencias reemplaza la salida
con `[]`; si falla la consulta o escritura, conserva la salida anterior y termina
con código 1. La consola informa la ruta y la cantidad de ofertas guardadas.
Cada oferta conserva los siete campos originales.
Reutiliza `ejecutar_configuracion` de `run.py`, sin cargar `config.json`.
Ambos scripts deben actualizarse juntos. Las pruebas anteriores incluyen el
arranque del cliente remoto con configuración y transporte simulados, sin
abrir archivos `.env` reales.

Para usar el [servicio Docker ARM64](../embedding/README.md), los nombres de
campos de integración en `config.json` son `EMBEDDING_PROVIDER`, `EMBEDDING_URL`
y `EMBEDDING_DIMENSIONS`. Conservar los demás campos existentes.

Con este proveedor el consultador no necesita instalar `reqs.txt`: usa solo
biblioteca estándar y los adaptadores compartidos del repositorio. Ni descarga
ni carga pesos en el cliente. `python run.py` y `python reindexar.py` seleccionan
el proveedor configurado. Ambos comprueban resultados y propagan fallos,
incluidos los estados HTTP, sin fallback ni éxito vacío ante errores.

El servicio usa el mismo espacio del modelo local, por lo que cambiar solo
de proveedor no requiere reindexar. `HTTP_TIMEOUT` también limita las llamadas
de embeddings. El adaptador local continúa disponible. Las pruebas de selección HTTP y
contrato se ejecutan desde la raíz con
`python -I -S -X utf8 embedding/tests/run_tests.py`, además de la suite habitual.
