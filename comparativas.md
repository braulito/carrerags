# Comparativa de modelos LLM en CarreRAGs

Fecha del informe: 27 de octubre de 2026.

## Resultado principal

Para la misma pregunta sobre Abogacía, **OpenAI completó el flujo en 11,28
segundos y Qwen/Ollama en 26,50 segundos**. Qwen tardó 2,35 veces lo que tardó
OpenAI, con una diferencia de 15,22 segundos.

Qwen generó aproximadamente 57 tokens por segundo durante la generación pura.
Sin embargo, procesar el prompt inicial consumió otros 8,20 segundos. La
búsqueda RAG demoró menos de medio segundo en ambas ejecuciones y no explica
la diferencia principal.

Las respuestas también presentan diferencias de calidad: en el caso medido,
OpenAI conserva mejor las advertencias del catálogo. Qwen incluye las ocho
instituciones, pero introduce una contradicción sobre su gestión pública o
privada y omite una advertencia específica de inscripción.

Estas conclusiones describen las muestras disponibles. **Una consulta medida
por proveedor no constituye un benchmark general de los modelos.**

## Fuentes y condiciones

| Elemento | Fuente o valor |
|---|---|
| Medición OpenAI | [llm/JSON/openai.json](llm/JSON/openai.json) |
| Medición Qwen | [llm/JSON/qwen.json](llm/JSON/qwen.json) |
| Modelo registrado por OpenAI | `gpt-6-luna` |
| Modelo registrado por Ollama | `qwen3.5:2b-q4_K_M` |
| Pregunta en ambos archivos | `donde estudiar para ser abogado?` |
| Resultado en ambos archivos | `resultado: true`, `mensaje: "ok"` |
| Filtro interpretado en ambos | `carrera: "Abogacía"`; los otros cuatro filtros en `null` |
| Catálogo usado para comprobar contenido | [consultador/TOTAL.json](consultador/TOTAL.json), exportación de 574 ofertas |
| Definición de las métricas | [Rendimiento y tiempos de la API](llm/README.md#rendimiento-y-tiempos) |
| Evaluación anterior de calidad | [Análisis de los JSON anteriores](llm/ANALISIS_LLM_20261027.md) |

Las cifras se obtuvieron de los JSON guardados. Para este informe no se
realizaron nuevas llamadas a proveedores ni se inspeccionaron archivos de
secretos. Los nombres de modelo son los registrados por el adaptador como
modelo solicitado, no una verificación independiente del despliegue del servidor.

## Tiempo total y etapas del flujo

| Etapa | OpenAI | Qwen/Ollama | Diferencia Qwen − OpenAI |
|---|---:|---:|---:|
| Normalización de la pregunta | 3,552 s | 10,298 s | +6,746 s |
| Búsqueda RAG | 0,384 s | 0,346 s | −0,039 s |
| Redacción de la respuesta | 7,343 s | 15,858 s | +8,515 s |
| **Total del flujo** | **11,279 s** | **26,502 s** | **+15,223 s** |

El tiempo total de OpenAI fue un 57,44 % menor que el de Qwen en esta consulta.
La pequeña diferencia en RAG, unos 39 milisegundos, no permite atribuir una
ventaja de recuperación a un modelo: se trata de servicios y variaciones de
ejecución compartidos por ambos flujos.

El tiempo de normalización incluye preparar el prompt y recuperar sus
referencias; no corresponde exclusivamente a inferencia. El tiempo total
registrado corresponde al flujo del endpoint antes del guardado y la
serialización, no al tiempo completo observado por un navegador.

## Duración de las solicitudes a los proveedores

| Llamada | OpenAI: solicitud completa | OpenAI: procesamiento del servidor | Qwen: solicitud completa | Qwen: tiempo del servidor |
|---|---:|---:|---:|---:|
| Normalización | 3,029 s | 1,977 s | 9,696 s | 9,659 s |
| Redacción | 7,335 s | 6,954 s | 15,851 s | 15,839 s |
| Suma de ambas llamadas | 10,364 s | 8,931 s | 25,547 s | 25,498 s |

La solicitud completa incluye apertura de conexión, espera, transferencia y
lectura/decodificación del JSON. El tiempo del servidor procede del header
`openai-processing-ms` en OpenAI y de `total_duration` en Ollama.

La diferencia entre solicitud y tiempo del servidor suma aproximadamente
1,43 segundos para OpenAI y 0,05 segundos para Ollama. Es una diferencia
orientativa entre mediciones con límites distintos, no una medición aislada
de latencia de red. En Qwen, casi toda la espera registrada sucede en el servidor.

## Tokens y velocidades

| Métrica | OpenAI | Qwen/Ollama |
|---|---:|---:|
| Tokens de entrada, ambas llamadas | 9.582 | 9.655 |
| Tokens de salida, ambas llamadas | 924 | 827 |
| Total de tokens | 10.506 | 10.482 |
| Tokens de entrada reutilizados de caché | 0 | 0 |
| Tokens de razonamiento informados | 225 | No informados (`null`) |

Los totales de entrada y salida son aritméticamente consistentes. Los
tokenizadores son diferentes: un token de un proveedor no representa
necesariamente la misma cantidad de texto que un token del otro.

### Velocidad sobre la solicitud completa

Esta métrica divide los tokens de salida por la duración completa de cada
solicitud. Permite observar el rendimiento experimentado por la API, con red,
espera y procesamiento de entrada incluidos.

| Llamada | Salida OpenAI | Salida Qwen | OpenAI | Qwen |
|---|---:|---:|---:|---:|
| Normalización | 75 tokens | 33 tokens | 24,76 tokens/s | 3,40 tokens/s |
| Redacción | 849 tokens | 794 tokens | 115,75 tokens/s | 50,09 tokens/s |

En la redacción, la tasa de solicitud de OpenAI fue 2,31 veces la de Qwen.
Esto no mide exclusivamente la velocidad del motor de generación. OpenAI
incluye 193 tokens de razonamiento en los 849 tokens de esa llamada; sus
conteos de salida no equivalen solo al texto visible.

### Velocidad interna de generación de Qwen

Ollama informa `eval_count` y `eval_duration`, por lo que se puede calcular:

```text
tokens_por_segundo_generacion = eval_count × 1.000.000.000 / eval_duration
```

`eval_duration` está expresado en nanosegundos.

| Llamada | `eval_count` | `eval_duration` | Duración de generación | Velocidad |
|---|---:|---:|---:|---:|
| Normalización | 33 | 587.537.000 ns | 0,588 s | 56,17 tokens/s |
| Redacción | 794 | 13.939.980.000 ns | 13,940 s | 56,96 tokens/s |

Las dos tasas son próximas, aunque corresponden a salidas de longitudes muy
diferentes. El adaptador de OpenAI no dispone de un tiempo exclusivo de
generación equivalente; ese campo queda `null`.

**No corresponde comparar 115,75 tokens/s de solicitud de OpenAI con 56,96
tokens/s de generación de Qwen.** Las bases temporales son distintas.

## Dónde se consume el tiempo de Qwen

| Trabajo interno informado por Ollama | Normalización | Redacción | Suma | Porcentaje del total del flujo |
|---|---:|---:|---:|---:|
| Carga del modelo | 0,828 s | 0,002 s | 0,830 s | 3,13 % |
| Procesamiento del prompt | 8,205 s | 1,819 s | 10,024 s | 37,82 % |
| Generación de salida | 0,588 s | 13,940 s | 14,528 s | 54,82 % |

Los porcentajes no suman el 100 % porque quedan RAG, preparación, transferencia
y otras tareas no incluidas en esos tres tiempos internos.

En la normalización, Qwen recibe 7.868 tokens de entrada para producir un JSON
de 33 tokens. La mayor parte de esa llamada se dedica a procesar el prompt,
no a generar los filtros. En la redacción recibe 1.787 tokens de entrada y
genera 794 tokens; allí domina la generación de la respuesta.

La carga del modelo explica una fracción pequeña del total. Mantenerlo cargado
puede reducir ese costo, pero por sí solo no elimina la diferencia observada.
Ambos JSON registran caché de entrada en cero: no hubo reutilización informada
en estas ejecuciones. Esto no significa que la caché esté deshabilitada.

## Calidad del contenido

### Consulta medida de Abogacía

Ambas respuestas presentan ocho instituciones y ocho enlaces correspondientes
a las ofertas de Abogacía del catálogo. Los filtros interpretados coinciden.

| Aspecto | OpenAI | Qwen/Ollama |
|---|---|---|
| Instituciones y enlaces | Presenta las ocho opciones. | Presenta las ocho opciones. |
| Gestión pública o privada | Indica que las opciones recuperadas son privadas. | Marca cada oferta como privada, pero al final afirma que no puede confirmarse su gestión. |
| Advertencia particular de UCES | Conserva que la inscripción vigente no está confirmada. | Omite esa advertencia junto a la oferta. |
| Modalidad de UCASAL | Aclara que no se confirma que Abogacía sea 100 % online. | Repite la referencia general a algunas modalidades 100 % online sin esa aclaración específica. |
| Información ajena a la consulta | No se observó la referencia ajena encontrada en Qwen. | Introduce en el cierre requisitos de presencia en salud, sin respaldo en estas ofertas de Abogacía. |

En este caso, la respuesta más rápida también conserva mejor las limitaciones
del catálogo. Obtener un JSON válido y `resultado: true` no demuestra que el
contenido sea correcto.

### Contexto de las pruebas anteriores

El [informe previo](llm/ANALISIS_LLM_20261027.md) evaluó catorce archivos
agrupados en seis preguntas distintas, sin métricas temporales. Registró:

- Coincidencia de los cinco filtros en cuatro de las seis preguntas comparadas.
- Qwen convirtió `morite` en una búsqueda en `Morón, Buenos Aires`.
- Para Sistemas, Qwen estrechó el tema a Sistemas de Información y después
  modificó los títulos oficiales de dos ofertas.
- Para docencia, Qwen mezcló títulos, añadió un requisito no respaldado y
  omitió los enlaces.

Esos resultados aportan contexto de calidad, pero no se mezclan con los tiempos
de la consulta actual. Los archivos anteriores tampoco registran el modelo
exacto: su atribución procede de las carpetas y del contexto de las pruebas.

## Límites de la comparación

1. Hay una sola medición temporal por proveedor. No se calcularon medianas,
   percentiles ni variabilidad entre ejecuciones.
2. Los modelos, tamaños, tokenizadores e infraestructuras son diferentes. La
   comparación representa estas dos configuraciones completas de CarreRAGs.
3. Los JSON no conservan las ofertas originales enviadas a la redacción ni
   sus identificadores y orden. La misma pregunta y los mismos filtros no
   prueban que las entradas de redacción fueran idénticas.
4. No se registraron simultáneamente carga del equipo, CPU/GPU, memoria,
   concurrencia ni versión del prompt. No puede atribuirse una causa de hardware
   específica a la diferencia.
5. No se dispone de una medición equivalente de la instalación anterior en
   Docker. Este informe no cuantifica cuánto mejoró Ollama al ejecutarse nativo.
6. No hay datos de precio facturado, energía o costo operativo. Menos tokens
   no permiten afirmar cuál alternativa resulta económicamente más conveniente.
7. `TOTAL.json` es una exportación; no certifica el contenido exacto de la
   colección real en el instante de cada consulta ni la vigencia de las ofertas.

## Recomendaciones

1. **Conservar los datos de las ofertas al presentarlos.** Generar títulos,
   requisitos, modalidades y enlaces mediante plantillas desde los originales.
   Esto reduce la dependencia de la redacción libre y podría reducir la cantidad
   de texto que debe generar la LLM; la mejora temporal debe medirse.
2. **Revisar el volumen de entrada de la normalización.** En Qwen, el prompt
   inicial consume 8,20 segundos de procesamiento. Evaluar una representación
   más compacta del catálogo preservando sinónimos, especialidades y alcance.
3. **Medir repetidamente con y sin reutilización de contexto.** Registrar carga
   inicial y modelo ya cargado, junto con los conteos reales de caché. Comparar
   medianas y dispersión con las mismas preguntas y entradas congeladas.
4. **Evaluar precisión además de velocidad.** Incluir consultas ajenas al catálogo,
   temas amplios, localidades, ciclos de complementación y condiciones inciertas.
   Una optimización que omita ofertas o invente filtros no debe considerarse mejora.
5. **Comparar nativo y Docker en condiciones equivalentes.** Mantener modelo,
   cuantización, contexto, opciones, hardware y aceleración comparables. Sin esa
   medición anterior no corresponde atribuir una mejora porcentual al cambio.

La evidencia actual favorece a OpenAI en tiempo total y fidelidad para la
consulta medida. Qwen completa el flujo local con una generación cercana a
57 tokens/s; sus prioridades de mejora son la fidelidad y el costo de procesar
la entrada y redactar las ofertas.
