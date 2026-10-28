# Ingesta de carreras desde Excel

Este componente lee el Excel, normaliza datos, clasifica ofertas, conserva historial,
genera embeddings con un modelo local o el servicio HTTP compartido y publica
el catálogo en un motor vectorial intercambiable.

**Se publican todas las ofertas activas del Excel**, incluidas las presenciales,
híbridas, semipresenciales y las que requieren estudios previos. La clasificación
de elegibilidad del perfil original se conserva como información; las condiciones
de búsqueda se aplican al consultar desde la API `llm`.

## Papel dentro del proyecto

En el flujo completo, [embedding](../embedding/README.md) genera los vectores,
`ingesta` publica el catálogo en Qdrant, [llm](../llm/README.md) atiende las
preguntas y [pagina](../pagina/README.md) ofrece la interfaz de consulta.
En el despliegue compartido, esta ingesta usa el servicio HTTP de `embedding`,
igual que `llm`, para mantener compatible el espacio vectorial.

Qdrant y `embedding` deben estar disponibles antes de publicar. Ejecutar la
ingesta al cargar o actualizar el catálogo; no necesita permanecer ejecutándose
para atender consultas. La API usa directamente la colección publicada y no
depende de importar este componente ni de ejecutar `consultador`.

Para migrar una colección publicada con un criterio anterior, ejecutar
nuevamente `python run.py`. La herramienta auxiliar `consultador` conserva su
flujo de reindexación para pruebas; no forma parte del arranque de la API.

El contenido procede exclusivamente del Excel. No visita fuentes institucionales,
no completa información y no implementa un chatbot ni un proveedor de conversación.

La API selecciona actualmente Qwen/Ollama y conserva OpenAI como alternativa.
Esa selección no cambia el modelo de embeddings ni requiere reindexar por sí
sola. La ingesta no recibe una elección de LLM y no genera respuestas de chat.
Los tiempos y consumos de la LLM pertenecen al JSON de la API; ver
[comparativas.md](../comparativas.md) y el [README general](../README.md).

## Arranque: python run.py

Se necesita Python 3.10 o superior. Abrir una terminal en la carpeta `ingesta`
y activar el entorno virtual en el que se ejecutará el programa.

Si el entorno se llama `venv` y está dentro de `ingesta`, en PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

En macOS o Linux, para esa misma estructura:

```sh
source venv/bin/activate
```

Si el entorno tiene otro nombre o ubicación, usar su ruta de activación.
Para usar el servicio `embedding` del proyecto, instalar las dependencias del
cliente HTTP dentro del entorno activado:

```console
python -m pip install -r reqs-http.txt
```

Crear **`ingesta/.env`**, junto a `run.py`, con estos nombres de variables para
la publicación y el servicio compartido de embeddings:

```text
VECTORIAL
VECTORIAL_NAMESPACE
EMBEDDING_PROVIDER
EMBEDDING_URL
EMBEDDING_DIMENSIONS
HTTP_TIMEOUT
```

La lista completa de nombres está en [Configuración](#configuración).

Después ejecutar:

```console
python run.py
```

Este es el comando de uso normal: no necesita subcomandos ni argumentos.
La instalación y la ejecución deben usar el Python del mismo entorno virtual.

Sin argumentos, el programa carga la configuración de ese archivo, selecciona el
único Excel de la carpeta, valida el catálogo, genera embeddings y publica el
catálogo completo en el motor. El reporte queda en
`.artifacts/revision_catalogo.json` y el historial en `.state/`.

El servicio HTTP compartido utiliza
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, multilingüe y con
salida de 384 dimensiones y ejecución en CPU. Sus pesos se descargan al construir
la imagen de `embedding`; el cliente HTTP de ingesta no los descarga ni ejecuta
Sentence Transformers o PyTorch.

También se conserva el adaptador local como alternativa: instalar
`python -m pip install -r reqs.txt`. La selección corresponde a
`EMBEDDING_PROVIDER`. En modo local, la primera ejecución descarga los pesos públicos
y los conserva en la caché del equipo. Ambos adaptadores fijan la misma revisión
del modelo predeterminado; cambiar solo el proveedor conserva el espacio.

## Dependencias y conexión al motor

`reqs-http.txt` instala únicamente `python-dotenv` para el cliente HTTP.
`reqs.txt` incluye además el modelo local con estas dependencias directas:

```text
python-dotenv>=1.1,<2
sentence-transformers>=5.1,<7
```

| Pieza | Responsabilidad |
|---|---|
| `python-dotenv` | Leer la configuración del archivo `.env` al arrancar. |
| `sentence-transformers` | Ejecutar el modelo local y convertir los textos de las carreras en vectores numéricos. Instala sus dependencias, como PyTorch, mediante pip. |
| `http.client` | Comunicarse con Qdrant y con el servicio de embeddings. Viene incluido en Python. |

La conexión HTTP se implementa en `carrerags_ingesta/adapters/http.py`; las
operaciones de Qdrant están en `carrerags_ingesta/adapters/qdrant.py`.
Esta implementación no requiere instalar `requests` ni `qdrant-client`.
Tampoco usa OpenAI ni necesita una clave de ese proveedor.


## Preparación de Qdrant

Qdrant debe estar iniciado, ser accesible desde el equipo de ingesta y permitir
crear, escribir y eliminar colecciones. Los nombres de variables del motor son
`VECTORIAL` y `VECTORIAL_NAMESPACE`.

**Al terminar una publicación queda una sola colección de este catálogo,
llamada `carrerags`.** No se crean generaciones nuevas ni se conserva la versión
anterior en Qdrant. Las consultas usan directamente ese nombre.

No hace falta crear colecciones ni índices desde el panel. La aplicación genera
los vectores con el proveedor configurado y, al publicar:

1. Retira el alias del esquema anterior si existe.
2. Elimina la colección anterior y las antiguas colecciones administradas con
   nombres `carrerags_g_<32 caracteres hexadecimales>`.
3. Crea la colección física `carrerags` e inserta todos los puntos inactivos.
4. Comprueba la cantidad cargada y que no queden generaciones del catálogo.
5. Habilita los puntos para las consultas.

La siguiente ejecución de `python run.py` migra automáticamente el esquema
anterior. La limpieza se limita al catálogo configurado y al patrón de nombres
que generaba este componente; no borra colecciones de otros proyectos.

Para mantener una sola colección física, se reemplaza directamente la anterior.
Durante la reconstrucción el catálogo no está disponible para consultas. Si
falla la carga, no se conserva la versión anterior en el motor: se informa el
fallo y se debe reejecutar la ingesta. El Excel y el estado local permiten
reconstruirla.

Si el servidor requiere autenticación, definir `VECTORIAL_API_KEY` con la clave
correspondiente. La clave se mantiene separada de la dirección.

## Configuración

Crear **`ingesta/.env`** en la carpeta del componente. Nombres de variables:

```text
VECTORIAL
VECTORIAL_PROVIDER
VECTORIAL_NAMESPACE
VECTORIAL_API_KEY
EXCEL
INGESTA_MODO
INGESTA_ESTADO
EMBEDDING_PROVIDER
EMBEDDING_URL
EMBEDDING_MODEL
EMBEDDING_REVISION
EMBEDDING_DIMENSIONS
HTTP_TIMEOUT
```

Las variables se aplican al iniciar `python run.py`. Los módulos adicionales
documentan su configuración en sus propios README.

## Revisión y pruebas

La selección del modo de revisión corresponde a `INGESTA_MODO`. Para ejecutar
la ingesta desde su carpeta:

```console
python run.py
```

El arranque carga la configuración para elegir el modo. En el modo de revisión no se
instancian adaptadores ni se llama al modelo o al motor. El reporte se guarda en
`.artifacts/revision_catalogo.json`. La publicación también se selecciona mediante
`INGESTA_MODO`.

`run.py` no procesa argumentos de consola. La selección del Excel, el modo y las
rutas se controlan mediante las variables documentadas. El arranque actual
imprime JSON con `resultado` y `mensaje`; los errores terminan con código de
proceso 1. Las funciones internas conservan la tupla con el dato de salida,
y el reporte detallado se escribe en `.artifacts/revision_catalogo.json`.

Para ejecutar las pruebas desde `ingesta`:

```console
python tests/run_tests.py
```

Para ejecutar las pruebas desde la raíz en un intérprete aislado:

```console
python -I -S -X utf8 ingesta/tests/run_tests.py
```

## Fuente y reglas

Se requiere la hoja **Todas las carreras**, con estas siete columnas y este orden:

`Título`, `Lugar donde se cursa`, `Nivel`, `Descripción`, `Tipo de cursada`,
`Pública/Privada`, `URL`.

Se aceptan XLSX con texto directo, texto compartido y texto inline. Se rechazan
fórmulas, errores de celda, campos vacíos, encabezados distintos, duplicados y un
catálogo vacío. No se ejecutan macros ni se siguen enlaces. Límites: 25 MB de
archivo, 100 MB descomprimidos y 64 columnas por fila.

`Altas verificadas` es opcional: sus filas deben coincidir con filas de la
principal y solo añaden procedencia. Los demás registros se marcan como heredados.
Las otras hojas documentan alcance y decisiones; no se indexan como carreras.

Clasificación del perfil original, versionada en `domain.RULES_VERSION`. Estas
reglas determinan metadatos, no qué filas se publican:

- Admitir cursada a distancia, aunque tenga evaluaciones o prácticas presenciales.
- Excluir clases híbridas, semipresenciales y presenciales con componente virtual.
- No confundir sincronía mixta online con clases presenciales. Una alternativa
  semipresencial adicional no invalida una opción a distancia diferenciada.
- Excluir CCC y otros ciclos que requieren formación superior previa, accesos
  restringidos y títulos intermedios sin ingreso independiente acreditado.
- Conservar las incertidumbres; no inferir ausencia de prácticas ni acceso
  confirmado desde secundario por falta de información.

El informe separa candidatas y ofertas fuera del perfil original en
`eligible`/`excluded`, pero ambas se vectorizan y publican. El campo
`report.indexed` informa la cantidad de puntos preparados para el motor.
Consultar el reporte de cada ejecución para conocer las cantidades vigentes.
La falta de datos sobre exámenes, prácticas o ingreso debe conservarse como
desconocimiento; no acredita que una oferta cumpla esas condiciones.

Para análisis del catálogo y comparaciones con respuestas, usar
`consultador/TOTAL.json`. Es una exportación que no se actualiza automáticamente:
regenerarla desde un Excel modificado requiere una solicitud explícita.
El Excel sigue siendo la entrada de publicación de esta ingesta.
Una consulta sin resultados en la página no autoriza a regenerar esa exportación
ni a reconstruir la colección: primero distinguir filtros no interpretados,
ausencia de coincidencias y fallos de servicios en el JSON de `llm`.

## Datos y contratos

| Dato | Contenido |
|---|---|
| `id` | UUID estable de título, institución, ubicación y nivel normalizados. No depende de fila ni URL. |
| `title`, `institution`, `location`, `level` | Datos separados sin inventar localidad o provincia ausentes. La ubicación institucional no acredita cobertura ni lugar de examen. |
| `management` | `Pública` o `Privada`; no implica gratuidad. |
| `modality` | `distancia`, `semipresencial`, `hibrida`, `presencial` o `desconocida`. |
| `exams`, `practices` | `remoto`, `presencial` o `desconocido`. El contrato también contempla prácticas `no_aplica` cuando exista evidencia. |
| `admission` | Estudios previos, restricción o desconocido. El contrato contempla `secundario_confirmado` para reglas respaldadas por datos explícitos. |
| `eligible`, `exclusion_reasons`, `pending` | Clasificación del perfil original y aspectos pendientes; no impiden publicar o consultar una oferta. |
| `independent_entry` | Falso para títulos intermedios sin ingreso independiente identificado. |
| `catalog_scope` | `all_active_offers` en todos los puntos de la publicación completa. |
| `source`, `original` | Archivo, hash, hoja, fila, URL, grupo de revisión y siete valores originales. `verified_at` permanece nulo: importar no equivale a auditar. |
| `text` | Título, institución, nivel y descripción que se entregan al módulo configurado para vectorizar. |

Las funciones implementadas tienen parámetros tipados, manejo de excepciones y
retorno `(resultado, mensaje, dato)`: éxito `(True, "ok", dato)`, error
`(False, mensaje_descriptivo, vacío_correspondiente)`. Los protocolos declaran
las mismas firmas. Cada llamada comprueba el resultado y propaga los fallos.

El módulo de embeddings debe declarar `space` y `dimensions`, y devolver un vector finito
no nulo por texto, en el orden recibido. El núcleo valida cantidad, dimensión y
valores antes de publicar. `space` identifica la compatibilidad de los vectores.

## Fragmentación y solapamiento (overlap)

El solapamiento conserva contexto al dividir un texto largo en fragmentos
(*chunks*): cada fragmento repite una parte del anterior. Por ejemplo:

- Fragmento 1: palabras 1 a 100.
- Fragmento 2: palabras 81 a 180.
- Fragmento 3: palabras 161 a 260.

En este ejemplo se repiten 20 palabras entre fragmentos consecutivos. Esto ayuda
a conservar una explicación que atraviesa el corte, a cambio de almacenar
contenido repetido. Se prepara durante la ingesta, antes de generar los
embeddings. Qdrant busca los vectores más similares a la consulta; no agrega
solapamiento automáticamente al buscar.

**La ingesta actual no divide las carreras ni aplica solapamiento:** cada oferta
activa se guarda completa como un punto con su vector. Las descripciones del
Excel son cortas y cada carrera es una unidad independiente; no se mezcla el
final de una carrera con el comienzo de otra.

Si se incorporan planes de estudio o documentos largos, se puede evaluar dividir
el contenido y aplicar solapamiento dentro de cada carrera. Su tamaño y utilidad
deben comprobarse con consultas representativas: repetir texto no garantiza
mejores resultados y puede producir recuperaciones redundantes.

Referencia: [estrategias de fragmentación de Qdrant](https://qdrant.tech/course/beginners/module-2/chunking-strategies/).

## Actualizaciones e historial

Cada Excel es un catálogo completo. Se identifican altas, modificaciones, ofertas
sin cambios y retiradas. Las retiradas permanecen en el historial local y
desaparecen del índice publicado. Si cambia título, institución, ubicación o
nivel, se interpreta como baja y alta: este Excel no trae un ID externo para
distinguir automáticamente correcciones de identidad.

La carpeta de estado se configura mediante `INGESTA_ESTADO`.
`catalog.json` conserva el catálogo canónico y la caché de vectores.
`snapshots/` conserva versiones completas. Solo se reutilizan vectores cuando
coinciden espacio, texto y dimensión. Cambios de metadatos no obligan a vectorizar
otra vez; cambios de modelo o transformaciones incompatibles sí.

Se valida el libro completo antes de publicar. Un bloqueo local evita importaciones
simultáneas con el mismo estado. Si una interrupción deja `ingest.lock`, comprobar
que no hay una ingesta activa antes de retirar el bloqueo. Usar un solo escritor
por catálogo lógico: el bloqueo no coordina distintas máquinas o estados locales.

En Qdrant se usa una única colección física, configurada mediante
`VECTORIAL_NAMESPACE`. Los vectores y un snapshot local preparado
se generan antes de eliminar el catálogo remoto anterior. Después se reconstruye
la colección, se comprueba la cantidad y se habilitan los puntos.

No hay cambio de alias ni colecciones de respaldo en el flujo nuevo. La primera
ejecución con este flujo retira las generaciones y el alias del esquema anterior.
Una publicación fallida puede dejar la colección ausente o incompleta; el programa
no la presenta como un éxito. Un timeout durante la habilitación puede dejar el
resultado indeterminado y se informa como tal.

El catálogo local se confirma después de publicar. Si falla esa escritura final,
el error informa que el índice pudo publicarse; reejecutar la ingesta vuelve a
reconstruir la misma colección. El historial de archivos en `.state/` permanece
local y no crea colecciones adicionales en Qdrant.

## Extensión y límites

Ver [contratos y extensión](carrerags_ingesta/adapters/README.md).
El motor y el módulo de embeddings son independientes. Cambiar de motor
requiere reconstruir su índice desde el catálogo, sin exportar el motor anterior.
Cambiar el módulo de embeddings obliga a regenerar vectores si cambia su espacio.

Este componente ofrece revisión y publicación con un único arranque. La
interpretación de preguntas y la redacción mediante LLM pertenecen a
[llm](../llm/README.md). La ingesta no expone un servidor HTTP ni MCP.

El componente que consulte este catálogo debe generar los vectores de búsqueda
con el mismo modelo, revisión y normalización compatibles con el espacio usado
en la ingesta. El LLM que redacte las respuestas puede elegirse por separado.

## Problemas frecuentes

| Situación | Qué revisar |
|---|---|
| `No module named 'dotenv'` | Activar el venv correcto e instalar `reqs-http.txt` para HTTP o `reqs.txt` para el proveedor local. El paquete se llama `python-dotenv`, aunque se importa como `dotenv`. |
| Falta `sentence_transformers` o alguna de sus dependencias | Revisar si se está seleccionando el proveedor local. Revisar `EMBEDDING_PROVIDER`; para el adaptador local, completar la instalación de `reqs.txt` en el mismo Python. |
| La primera ejecución tarda durante la carga del modelo local | Puede estar descargando los pesos. Esa primera descarga necesita acceso a Internet; los pesos se guardan en la caché local. En modo HTTP, el modelo se carga en el servicio `embedding`. |
| No se puede conectar con el servicio de embeddings | Verificar `EMBEDDING_PROVIDER`, `EMBEDDING_URL` y que `/health` responda desde el equipo de ingesta. |
| No se puede conectar con Qdrant | Comprobar que el servidor esté iniciado y que host, puerto, red y permisos correspondan a la configuración del usuario. |
| Hay cero o varios Excel en la carpeta | Definir `EXCEL` con la ruta del archivo que debe procesarse. |
| Existe una colección del catálogo o generaciones del esquema anterior | La publicación las reemplaza automáticamente. Si falla la eliminación, revisar los permisos de escritura y borrado del motor. |

La salida final es JSON. `resultado: true` y `mensaje: "ok"` indican que el
comando terminó correctamente. El reporte escrito en `.artifacts/` informa
las filas, candidatas y exclusiones; durante una publicación también informa
los vectores generados y reutilizados.

## Pruebas

```console
python -I -S -X utf8 ingesta/tests/run_tests.py
```

La suite está en `tests/`. Usa libros sintéticos en carpetas temporales, configuración
ficticia y transportes/modelos simulados; no lee configuración protegida, no descarga
pesos ni conecta servicios o bases reales. Comprueba lectura XLSX, entradas inválidas, elegibilidad, identidad,
caché, bajas, publicación, filtros del contrato del motor, fallos y extensión por
factoría. Verifica que el procesamiento de revisión no crea adaptadores ni convierte configuración,
y que publicar utiliza el módulo de embeddings configurado. También comprueba
el arranque sin argumentos, la configuración simulada y el adaptador local con
un modelo simulado; además procesa el Excel incluido.

Las comprobaciones automatizadas usan configuración, modelo y servicios
simulados. La ejecución del modelo real o del servicio HTTP, junto con la
conexión al Qdrant del usuario, requieren una validación separada en su entorno.
Una prueba recorre todas las variables configurables hasta la publicación en un
motor simulado, comprueba la prioridad del archivo y verifica que el modo de
análisis no utilice el modelo ni el motor. No abre un archivo `.env` real.
Las reglas son textuales y conservadoras: los cambios deben añadir casos de
prueba y actualizar `RULES_VERSION`.

Referencias del adaptador inicial: [puntos de Qdrant](https://api.qdrant.tech/api-reference/points/upsert-points),
[consultas de Qdrant](https://api.qdrant.tech/api-reference/search/query-points) y
[eliminación de colecciones](https://api.qdrant.tech/api-reference/collections/delete-collection).

Referencias del modelo y el arranque: [ficha del modelo](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), [Sentence Transformers](https://sbert.net/docs/package_reference/sentence_transformer/model.html) y [python-dotenv](https://bbc2.github.io/python-dotenv/reference/).

## Usar el servicio de embeddings HTTP

Además del adaptador local, se incluye el adaptador HTTP. Construir y arrancar
[embedding](../embedding/README.md) en el Mac mini. Crear `ingesta/.env` con
`EMBEDDING_PROVIDER`, `EMBEDDING_URL`, `EMBEDDING_DIMENSIONS` y `HTTP_TIMEOUT`,
además de las variables del motor enumeradas en [Configuración](#configuración).
Para un cliente exclusivamente HTTP basta `python -m pip install -r reqs-http.txt`
desde esta carpeta: no instala Sentence Transformers ni PyTorch.

El adaptador valida disponibilidad e identidad al crearse, divide el catálogo
en lotes de 15 textos, conserva su orden y comprueba dimensión, valores finitos
y normalización. Usa exactamente el espacio del modelo local fijado, por lo
que cambiar solo de proveedor no exige reindexar ni invalida la caché. Un fallo
de red, HTTP o respuesta se propaga; no se cambia automáticamente al modelo
local ni se conserva una salida parcial como éxito. El proveedor local sigue
disponible y su selección predeterminada permanece igual.

Las pruebas nuevas de integración HTTP están en `embedding/tests/`; ejecutar
`python -I -S -X utf8 embedding/tests/run_tests.py` desde la raíz. Usan un modelo
simulado y un servidor loopback efímero, sin leer archivos protegidos ni usar
servicios reales.
