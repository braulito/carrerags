/** @typedef {{status:number, kind:string, html:string, markdown:string}} ApiData */

/** @param {number} status @returns {[boolean, string, string]} */
export function messageForStatus(status) {
  try {
    const messages = {
      400: "Revisá tu pregunta y volvé a intentar.",
      404: "No encontramos opciones para esta búsqueda. Probá con otra carrera, ubicación o modalidad.",
      413: "La pregunta es demasiado larga. Acortala y volvé a intentar.",
      422: "No pudimos interpretar la pregunta. Revisala y volvé a intentar.",
      429: "Hay demasiadas consultas en este momento. Esperá un poco antes de volver a intentar.",
      504: "El servicio superó el tiempo de espera. Podés volver a intentar en unos momentos.",
    };
    return [true, "ok", messages[status] ?? "El servicio no pudo completar la consulta. Volvé a intentar en unos momentos."];
  } catch (e) {
    console.error("Error en messageForStatus:", e);
    return [false, "No se pudo preparar el mensaje", "No pudimos completar la consulta."];
  }
}

/**
 * Una solicitud por acción; fetchImpl permite pruebas sin conexiones reales.
 * @param {string} pregunta
 * @param {number} timeoutMs
 * @param {typeof fetch} fetchImpl
 * @returns {Promise<[boolean, string, ApiData]>}
 */
export async function requestQuestion(pregunta, timeoutMs, fetchImpl = globalThis.fetch) {
  let timer;
  const empty = {status: 0, kind: "error", html: "", markdown: ""};
  try {
    const controller = new AbortController();
    timer = setTimeout(() => controller.abort(), timeoutMs);
    const response = await fetchImpl("/api/consulta", {
      method: "POST",
      headers: {"Content-Type": "application/json", Accept: "application/json"},
      body: JSON.stringify({pregunta}),
      signal: controller.signal,
      cache: "no-store",
    });
    const result = {...empty, status: response.status};
    let data;
    try {
      data = await response.json();
    } catch (e) {
      console.error("Error en requestQuestion al decodificar JSON:", e);
      return [false, messageForStatus(response.ok ? 502 : response.status)[2], result];
    }
    if (response.status === 404) {
      return [false, messageForStatus(404)[2], {...result, kind: "empty"}];
    }
    if (!response.ok || data?.resultado !== true) {
      return [false, messageForStatus(response.ok ? 502 : response.status)[2], result];
    }
    if (typeof data.respuesta_html !== "string" || !data.respuesta_html.trim()
        || typeof data.salida?.respuesta !== "string") {
      return [false, "El servicio devolvió una respuesta incompleta. Volvé a intentar.", result];
    }
    return [true, "ok", {
      status: response.status, kind: "success", html: data.respuesta_html,
      markdown: data.salida.respuesta,
    }];
  } catch (e) {
    console.error("Error en requestQuestion:", e);
    const message = e?.name === "AbortError"
      ? "La consulta superó el tiempo de espera. Podés volver a intentar en unos momentos."
      : "No pudimos conectarnos. Revisá tu conexión y volvé a intentar.";
    return [false, message, empty];
  } finally {
    clearTimeout(timer);
  }
}
