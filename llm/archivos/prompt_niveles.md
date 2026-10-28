# Niveles educativos del catálogo

Fuente: `TOTAL.json`. Este listado conserva los valores originales únicos del
campo `Nivel`. Es una instantánea del catálogo; no se actualiza automáticamente.

## Uso para interpretar preguntas

Usá estos niveles como referencia para traducir la pregunta del usuario al
campo `tipo_titulo`. En el contrato acordado, ese campo representa el nivel
educativo y admite Grado, Pregrado, Posgrado o Superior no universitario.
Si la persona no pide un nivel, devolvé null. No lo deduzcas de la profesión
que quiere ejercer.

Ingeniería, Licenciatura, Profesorado, Tecnicatura, Especialización, Maestría
y Doctorado se representan en `carrera`, junto con disciplinas y nombres
específicos. No los uses como valores de `tipo_titulo`.

Para buscar por nivel general, Grado abarca tanto el valor original Grado
como sus variantes entre paréntesis. Superior no universitario abarca también
sus variantes Profesorado y Tecnicatura. La recuperación debe comparar estas
familias de valores; una igualdad literal con el nivel general excluiría las
variantes del catálogo.

Los calificadores originales no deben perderse en las ofertas devueltas:
Grado (CCC), ciclo para graduados y ciclo para profesionales distinguen
propuestas que pueden requerir formación previa. Una consulta por Grado no
significa automáticamente ingreso con secundario. Si la persona pide una
variante específica como CCC, conservar la pregunta original para tratar esa
restricción: el campo general `tipo_titulo` no la representa por sí solo.

Posgrado es un valor admitido por el contrato, pero no aparece en esta
instantánea. Si se solicita explícitamente, conservá Posgrado; no lo cambies
por otro nivel para conseguir resultados. El buscador deberá informar si no
encuentra ofertas en el catálogo.

Ejemplos de interpretación:

- «Carreras de grado» → tipo_titulo: Grado.
- «Qué carreras tienen nivel Superior no universitario» → tipo_titulo: Superior no universitario.
- «Tecnicaturas de pregrado» → carrera: Tecnicatura; tipo_titulo: Pregrado.
- «Quiero estudiar un posgrado» → tipo_titulo: Posgrado.
- «Quiero ser gerontólogo» → carrera: Gerontología; tipo_titulo: null.

## Valores originales

- Grado
- Grado (CCC)
- Grado (ciclo para graduados)
- Grado (ciclo para profesionales)
- Grado (profesorado universitario)
- Pregrado
- Superior no universitario
- Superior no universitario (Profesorado)
- Superior no universitario (Tecnicatura)
