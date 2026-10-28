# Comparación de respuestas: OpenAI y Qwen/Ollama

Fecha del análisis: 27 de octubre de 2026.

## Dictamen

Qwen completa el circuito local y produce filtros y respuestas con el contrato
esperado. Sin embargo, esta muestra contiene errores de interpretación y de
fidelidad que impiden considerarlo equivalente al comportamiento observado con
OpenAI. El problema principal es la calidad del contenido: una respuesta con
`resultado: true` puede ser incorrecta.

Mantendría Qwen como conector para continuar las pruebas, con prioridad en
validar la intención y presentar las ofertas desde sus campos originales.
No usaría todavía la redacción libre de este modelo como única fuente para
requisitos, títulos o condiciones de cursada en una página pública.

## Fuentes y alcance

- [JSON/OPENAI](JSON/OPENAI): seis archivos, con seis preguntas diferentes.
- [JSON/QEWN](JSON/QEWN): ocho archivos, con esas mismas seis preguntas;
  una pregunta de Abogacía aparece tres veces.
- [TOTAL.json](../consultador/TOTAL.json): 574 ofertas, única fuente utilizada
  para comprobar títulos, instituciones, modalidades y requisitos.
- [Router](routers/llmrag.py), [adaptador Qwen](helpers/llm_qewn.py),
  [prompt de filtros](helpers/prompt.md),
  [prompt de respuesta](helpers/prompt_respuesta_usuario.md) y
  [reglas de relevancia](helpers/rag/relevancia.py).

Las carpetas encontradas se llaman `OPENAI` y `QEWN`, no `OLLAMA` y `QWEN`.
Los nombres de carpeta identifican los grupos de esta comparación; los JSON
no registran por sí mismos el proveedor ni el modelo exacto que los produjo.

La [respuesta posterior de Abogacía](JSON/QEWN/20261027-213039.json) estaba
inicialmente fuera de las carpetas y fue trasladada a `QEWN` durante el análisis.
Se incluye en el recuento final de catorce archivos. Repite literalmente la
respuesta anterior, con otros conteos de caché; no añade una pregunta distinta.

Se hizo una comprobación local de las reglas de relevancia sobre `TOTAL.json`,
con carga de dotenv y conexiones por `urlopen` bloqueadas. No se abrió ningún
archivo de secretos ni se ejecutó una consulta a modelos, Qdrant o embeddings.
No se modificaron conectores, prompts ni respuestas guardadas.

## Comparación de las seis preguntas

Para la pregunta repetida de Abogacía se toma el primer archivo de Qwen.

| Pregunta | OpenAI | Qwen | Evaluación |
|---|---|---|---|
| `dime la hora` | Todos los filtros en `null`; 404 | Igual | Rechazo correcto de una consulta ajena al catálogo. |
| `dime donde puedo estudiar para ser docente` | `Profesorado` | `Profesorado` | Coinciden los filtros; la respuesta de Qwen altera información. |
| `dime donde puedo estudiar para ser abogado` | `Abogacía` | `Abogacía` | Coinciden los filtros y aparecen las ocho instituciones; Qwen pierde advertencias y añade una precisión geográfica no respaldada. |
| `morite` | Todos los filtros en `null`; 404 | Ubicación `Morón, Buenos Aires`; respuesta exitosa | Falso positivo de interpretación en Qwen. |
| `donde puedo estudiar sistemas` | `Sistemas` | `Sistemas de Información` | Qwen estrecha una consulta amplia y después altera títulos. |
| `donde estudiar para ser abogado?` | `Abogacía` | `Abogacía` | Coinciden los filtros y los ocho enlaces; hay contradicciones en el cierre de Qwen. |

Cuatro de las seis preguntas tienen los cinco filtros idénticos. Esto mide
coincidencia entre estas salidas, no una tasa general de exactitud. En las dos
preguntas sin intención educativa, OpenAI rechaza ambas y Qwen rechaza una.
El tamaño de la muestra no permite extrapolar esos porcentajes a producción.

## Hallazgos de mayor impacto

### 1. Una palabra ajena a la búsqueda activa todo el circuito

En [QEWN/20261027-212108.json](JSON/QEWN/20261027-212108.json), `morite`
se transforma en `ubicacion: "Morón, Buenos Aires"`. El sistema busca ofertas
de esa localidad y redacta diez opciones, consumiendo 11.307 tokens en total.
El archivo equivalente de OpenAI termina en la normalización, con 7.949 tokens.

La ubicación no fue solicitada. El esquema JSON valida que sea un texto, pero
no comprueba que esté respaldado por la pregunta. Buscar una localidad válida
en el catálogo no demuestra que esa haya sido la intención del usuario.

### 2. Sistemas pierde alcance y cambia títulos oficiales

En [QEWN/20261027-212132.json](JSON/QEWN/20261027-212132.json), Qwen agrega
`de Información` al tema solicitado. Esto contradice la instrucción de no
elegir una formación específica para un tema amplio.

Al aplicar la función actual `priorizar_carrera` al catálogo exportado,
sin filtros adicionales ni orden vectorial, `Sistemas` admite 27 candidatos
léxicos y `Sistemas de Información` admite tres. Son candidatos de la regla
actual, no una evaluación de que los 27 sean igualmente pertinentes. El límite
normal de respuesta es diez. No se reconstruyó el orden del Qdrant real.

Además, la respuesta de Qwen presenta:

- En UNTREF, `Licenciatura en Sistemas de Información`, cuando el registro
  dice **Licenciatura en Sistemas de Información Geográfica**.
- En UBP, `Licenciatura en Sistemas`, cuando el registro dice
  **Licenciatura en Sistemas de Información**.
- Tres opciones sin ningún enlace, pese a la instrucción de incluir uno por oferta.

Quitar `Geográfica` modifica la especialidad. Este es un error de redacción
independiente del estrechamiento previo de los filtros.

### 3. Docencia mezcla ofertas e inventa condiciones

En [QEWN/20261027-211902.json](JSON/QEWN/20261027-211902.json):

- Combina Historia y Lengua y Literatura de CEDSa en un título que no figura
  así en el catálogo. Geografía, presente en la respuesta de OpenAI, desaparece.
- Afirma que CEDSa requiere título previo. Los registros correspondientes no
  contienen ese requisito.
- Para el Profesorado para Profesionales de UCH, convierte la necesidad de
  **comprobar presencialidad de prácticas** en una afirmación de que las
  prácticas se comprueban presencialmente.
- Para UDE, menciona el ciclo para graduados, pero omite destacar el requisito
  explícito de título universitario previo y la duración de un año y medio.
- Presenta ocho apartados y ningún enlace. La salida de OpenAI presenta diez
  ofertas separadas y diez enlaces.

Los JSON no conservan las ofertas originales enviadas a cada redacción.
Por eso, la comparación de ocho contra diez apartados no prueba por sí sola
cuántas ofertas recibió Qwen. Los títulos combinados y los requisitos no
respaldados sí pueden contrastarse directamente con `TOTAL.json`.

### 4. Abogacía es el mejor caso, pero conserva errores

En las cuatro respuestas de Abogacía de Qwen aparecen las ocho instituciones
del catálogo y los ocho enlaces correspondientes. La pregunta repetida produce
exactamente el mismo texto en las tres ejecuciones guardadas dentro de `QEWN`.
Eso muestra repetibilidad para ese caso, incluyendo sus errores.

En [QEWN/20261027-211801.json](JSON/QEWN/20261027-211801.json) y sus repeticiones:

- Cada oferta está marcada como privada, pero el cierre afirma que no puede
  confirmarse si son públicas o privadas. El dato sí está en el catálogo.
- El cierre introduce requisitos de presencia en salud, ajenos a esta consulta
  y a los ocho registros de Abogacía.
- No conserva junto a UCES la advertencia de que la oferta se identificó en
  un informe de autoevaluación y hay que consultar la inscripción vigente.

En [QEWN/20261027-211954.json](JSON/QEWN/20261027-211954.json), el cierre habla
de concurrir a un CAU **en Córdoba**. El registro de Siglo 21 distingue la
ubicación institucional en Córdoba de los CAU en Argentina; no establece que
el estudiante deba rendir en Córdoba. También se omiten los niveles de las
ofertas y la advertencia particular de UCES.

En esta muestra, las respuestas de OpenAI conservan mejor esos matices. Esto
no constituye una garantía de que OpenAI los respete en cualquier otra consulta.

## Contratos y consumo

Los catorce archivos son JSON válidos. Se verificaron los conteos enteros no
negativos, `total = entrada + salida` y las sumas por etapa, respetando los
desgloses desconocidos en `null`. No se encontraron inconsistencias aritméticas.
Todos los enlaces presentes en las respuestas pertenecen al catálogo exportado;
no se comprobó la disponibilidad actual de esos sitios.

| Pregunta abreviada | Total OpenAI | Total Qwen | Salida de redacción OpenAI | Salida de redacción Qwen |
|---|---:|---:|---:|---:|
| Hora | 7.970 | 7.899 | No corresponde | No corresponde |
| Docente | 11.414 | 10.839 | 1.226 | 741 |
| Abogado, primera formulación | 10.504 | 10.471 | 827 | 781 |
| `morite` | 7.949 | 11.307 | No corresponde | 1.419 |
| Sistemas | 10.963 | 9.187 | 1.050 | 175 |
| Abogado, segunda formulación | 10.732 | 10.482 | 1.083 | 794 |

Los tokenizadores son distintos y OpenAI incluye razonamiento dentro de sus
conteos de salida. Qwen registra `razonamiento: null`: no permite comparar
ese desglose como si fuera cero. Menos tokens no demuestran mayor eficiencia:
en Sistemas también se redujo indebidamente la búsqueda y se omitieron enlaces.

La normalización recibe aproximadamente 7.900 tokens por consulta. En una
ejecución de Qwen aparecen 6.845 tokens de entrada en caché sobre 7.868,
aproximadamente un 87 %. Es un dato favorable de reutilización registrado,
pero sin tiempos no permite cuantificar cuánto aceleró la llamada.

## Límites de la medición

- Los JSON no guardan duración de las etapas, carga del modelo, tokens por
  segundo, proveedor, modelo exacto, versión del servidor ni versión del prompt.
- La fecha del nombre de archivo corresponde al guardado; los intervalos entre
  archivos incluyen pausas del usuario y no son tiempos de respuesta.
- El router elimina `ofertas` y `cantidad` del cuerpo que se guarda. No se puede
  reconstruir exactamente la entrada de la redacción ni garantizar que ambos
  proveedores recibieran los mismos registros y en el mismo orden.
- `TOTAL.json` es una exportación: no demuestra que la colección real tuviera
  exactamente ese contenido en las fechas de las consultas.
- Las catorce muestras contienen solo seis preguntas distintas. No cubren
  sistemáticamente negaciones, ubicaciones, CCC, requisitos, idiomas ni inyección.
- La captura previa del monitor no permite atribuir sus 13,4 GB al modelo ni
  determinar qué parte de una consulta estaba ejecutándose.

## Mejoras propuestas, por prioridad

1. **Presentar ofertas a partir de datos originales.** Generar las tarjetas o
   listas con código, conservando título, institución, lugar, nivel, modalidad,
   descripción y URL. Restringir la LLM a una introducción breve si se necesita.
   Así, los campos críticos dejan de depender de una reescritura libre.
2. **Comprobar el respaldo de los filtros en la pregunta.** Evaluar por separado
   intención, equivalencias y criterios inventados. Mantener búsquedas legítimas
   como una localidad aislada y sinónimos como abogado/Abogacía; una lista negra
   de palabras o exigir siempre el verbo estudiar no resolverían el problema.
3. **Evaluar las dos etapas por separado.** Incorporar casos de regresión para
   consultas ajenas, temas amplios, títulos con especialidades, CCC, condiciones
   por confirmar y los fallos concretos encontrados aquí. Para comparar modelos,
   usar las mismas ofertas congeladas en la etapa de redacción.
4. **Registrar evidencia para la próxima comparación.** Guardar identificador de
   consulta, conector, modelo, versión del prompt, filtros, ofertas e IDs en su
   orden, tiempos por etapa y métricas disponibles de Ollama. No registrar claves
   ni configuración sensible. Esto separará calidad, recuperación y rendimiento.
5. **Revisar la relevancia de temas amplios.** La búsqueda actual acepta términos
   en cualquier campo, incluidas descripciones genéricas. En Sistemas hay títulos
   geográficos descritos con texto informático general; cambiar de LLM por sí
   solo no resuelve esa ambigüedad del catálogo y de la selección.

El objetivo de la siguiente evaluación debe ser que las respuestas exitosas
conserven la intención y los datos, además de cumplir el esquema JSON.
