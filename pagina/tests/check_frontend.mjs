import {requestQuestion} from "../static/api.mjs";
import assert from "node:assert/strict";

/** @type {Response|Error|null} */
let simulated = null;
let calls = [];

/** @param {unknown} body @param {number} status @returns {[boolean,string,object|null]} */
function makeResponse(body, status = 200) {
  try {
    const text = typeof body === "string" ? body : JSON.stringify(body);
    return [true, "ok", {status, ok: status >= 200 && status < 300, json: async () => JSON.parse(text)}];
  } catch (e) {
    console.error("Error en makeResponse:", e);
    return [false, "No se pudo preparar la respuesta simulada", null];
  }
}

/** Adaptador de fetch simulado. @type {typeof fetch} */
async function fakeFetch(url, options) {
  calls.push({url, options});
  if (simulated instanceof Error) throw simulated;
  return simulated;
}

/** Adaptador de fetch que solo termina al abortar. @type {typeof fetch} */
async function hangingFetch(url, options) {
  calls.push({url, options});
  return new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => {
      const error = new Error("Timeout simulado");
      error.name = "AbortError";
      reject(error);
    }, {once: true});
  });
}

/** @returns {Promise<[boolean,string,string[]]>} */
export async function runChecks() {
  try {
    const checks = [];
    simulated = makeResponse({resultado: true, respuesta_html: "<p>Opciones</p>", salida: {respuesta: "Opciones"}})[2];
    calls = [];
    let [ok, message, data] = await requestQuestion('Diseño "a distancia"', 1000, fakeFetch);
    assert(ok && data.html === "<p>Opciones</p>", "Respuesta correcta");
    assert(calls.length === 1 && calls[0].url === "/api/consulta", "Una llamada al proxy local");
    assert(JSON.parse(calls[0].options.body).pregunta === 'Diseño "a distancia"', "Serialización JSON");
    checks.push("éxito, URL local, JSON y llamada única");

    for (const status of [401, 404, 422, 429, 500, 502, 504]) {
      simulated = makeResponse({resultado: false, detail: [{msg: "Fallo simulado"}]}, status)[2];
      calls = [];
      [ok, message, data] = await requestQuestion("Diseño", 1000, fakeFetch);
      assert(!ok && data.status === status && message.length > 0, `Error HTTP ${status}`);
      assert((data.kind === "empty") === (status === 404), "Ausencia de resultados diferenciada");
      assert(calls.length === 1, "Sin reintento automático");
    }
    checks.push("estados HTTP, ausencia de resultados y formato FastAPI");

    for (const body of [{resultado: false}, {resultado: true}, {resultado: true, respuesta_html: "", salida: {respuesta: ""}}]) {
      simulated = makeResponse(body)[2];
      [ok] = await requestQuestion("Diseño", 1000, fakeFetch);
      assert(!ok, "No aceptar HTTP 200 fallido o incompleto");
    }
    simulated = makeResponse("<html>Error</html>", 502)[2];
    [ok] = await requestQuestion("Diseño", 1000, fakeFetch);
    assert(!ok, "No aceptar contenido que no sea JSON");
    checks.push("HTTP 200 con resultado false, contrato incompleto y JSON inválido");

    simulated = new TypeError("Conexión simulada");
    calls = [];
    [ok, message] = await requestQuestion("Diseño", 1000, fakeFetch);
    assert(!ok && message.includes("conectarnos") && calls.length === 1, "Fallo de conexión");
    calls = [];
    [ok, message] = await requestQuestion("Diseño", 5, hangingFetch);
    assert(!ok && message.includes("tiempo de espera") && calls.length === 1, "Timeout sin reintento");
    checks.push("desconexión y aborto por tiempo máximo sin reintentos");
    return [true, "ok", checks];
  } catch (e) {
    console.error("Error en runChecks:", e);
    return [false, String(e), []];
  }
}
