import {requestQuestion} from "./api.mjs";

/** @type {{busy:boolean, count:number, waitTimer:ReturnType<typeof setTimeout>|null}} */
const state = {busy: false, count: 0, waitTimer: null};
const dom = {
  form: document.querySelector("#query-form"),
  question: document.querySelector("#question"),
  send: document.querySelector("#send-button"),
  fresh: document.querySelector("#new-query"),
  status: document.querySelector("#composer-status"),
  fieldError: document.querySelector("#field-error"),
  welcome: document.querySelector("#welcome"),
  conversation: document.querySelector("#conversation"),
  scroller: document.querySelector("#scroll-area"),
  history: document.querySelector("#history"),
  historyEmpty: document.querySelector("#history-empty"),
  dialog: document.querySelector("#error-dialog"),
  errorMessage: document.querySelector("#error-message"),
  closeDialog: document.querySelector("#close-dialog"),
  template: document.querySelector("#exchange-template"),
};

/** @param {boolean} busy @returns {[boolean,string,null]} */
function setBusy(busy) {
  try {
    state.busy = busy;
    dom.send.disabled = busy;
    dom.fresh.disabled = busy;
    dom.question.disabled = busy;
    dom.form.setAttribute("aria-busy", String(busy));
    for (const button of document.querySelectorAll(".suggestion, .retry-button")) button.disabled = busy;
    dom.status.textContent = busy ? "Consultando las ofertas educativas…" : "Cada pregunta abre una posibilidad.";
    return [true, "ok", null];
  } catch (e) {
    console.error("Error en setBusy:", e);
    return [false, "No se pudo actualizar el estado", null];
  }
}

/** @param {string} message @returns {[boolean,string,null]} */
function showError(message) {
  try {
    dom.errorMessage.textContent = message;
    if (!dom.dialog.open) dom.dialog.showModal();
    return [true, "ok", null];
  } catch (e) {
    console.error("Error en showError:", e);
    dom.fieldError.textContent = message;
    return [false, "No se pudo abrir el aviso", null];
  }
}

/** @param {string} pregunta @returns {[boolean,string,HTMLElement|null]} */
function addExchange(pregunta) {
  try {
    const exchange = dom.template.content.firstElementChild.cloneNode(true);
    exchange.id = `consulta-${++state.count}`;
    exchange.querySelector(".user-message p").textContent = pregunta;
    const content = exchange.querySelector(".answer-content");
    const pending = document.createElement("div");
    pending.className = "pending-status";
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    const text = document.createElement("span");
    text.textContent = "Buscando opciones para vos…";
    pending.append(spinner, text);
    content.append(pending);
    dom.conversation.append(exchange);
    dom.welcome.hidden = true;
    dom.historyEmpty.hidden = true;
    for (const button of dom.history.children) button.classList.remove("active");
    const historyButton = document.createElement("button");
    historyButton.type = "button";
    historyButton.textContent = pregunta;
    historyButton.title = pregunta;
    historyButton.className = "active";
    historyButton.addEventListener("click", () => exchange.scrollIntoView({block: "start", behavior: "smooth"}));
    dom.history.prepend(historyButton);
    state.waitTimer = setTimeout(() => {
      text.textContent = "La consulta está demorando un poco más. Seguimos esperando la respuesta…";
    }, 45000);
    exchange.scrollIntoView({block: "start", behavior: "smooth"});
    return [true, "ok", exchange];
  } catch (e) {
    console.error("Error en addExchange:", e);
    return [false, "No se pudo preparar la consulta", null];
  }
}

/** @param {HTMLElement} exchange @param {string} markdown @returns {[boolean,string,null]} */
function addCopyAction(exchange, markdown) {
  try {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "text-button copy-button";
    button.innerHTML = '<svg aria-hidden="true"><use href="#icon-copy"></use></svg><span>Copiar respuesta</span>';
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(markdown);
        button.querySelector("span").textContent = "Copiada";
      } catch (e) {
        console.error("Error en copiar_respuesta:", e);
        button.querySelector("span").textContent = "No se pudo copiar";
      }
    });
    exchange.querySelector(".answer-actions").append(button);
    return [true, "ok", null];
  } catch (e) {
    console.error("Error en addCopyAction:", e);
    return [false, "No se pudo agregar la acción de copiar", null];
  }
}

/** @param {HTMLElement} exchange @param {string} pregunta @returns {[boolean,string,null]} */
function addRetryAction(exchange, pregunta) {
  try {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "text-button retry-button";
    button.textContent = "Volver a intentar";
    button.addEventListener("click", () => {
      if (!state.busy) {
        dom.question.value = pregunta;
        dom.form.requestSubmit();
      }
    });
    exchange.querySelector(".answer-actions").append(button);
    return [true, "ok", null];
  } catch (e) {
    console.error("Error en addRetryAction:", e);
    return [false, "No se pudo agregar el reintento", null];
  }
}

/** @param {SubmitEvent} event @returns {Promise<[boolean,string,null]>} */
async function submitQuestion(event) {
  event.preventDefault();
  if (state.busy) return [false, "Ya hay una consulta en curso", null];
  let exchange = null;
  let ownsRequest = false;
  try {
    const pregunta = dom.question.value.trim();
    dom.fieldError.textContent = "";
    if (!pregunta) {
      dom.fieldError.textContent = "Escribí qué te gustaría estudiar.";
      dom.question.focus();
      return [false, "La pregunta está vacía", null];
    }
    const [prepared, preparationMessage, preparedExchange] = addExchange(pregunta);
    if (!prepared || !preparedExchange) {
      showError(preparationMessage);
      return [false, preparationMessage, null];
    }
    exchange = preparedExchange;
    ownsRequest = true;
    const [busySet, busyMessage] = setBusy(true);
    if (!busySet) throw new Error(busyMessage);
    const [resultado, mensaje, data] = await requestQuestion(pregunta, Number(document.body.dataset.timeoutMs));
    const content = exchange.querySelector(".answer-content");
    content.replaceChildren();
    if (resultado) {
      // Únicamente el proxy local genera este HTML, con Markdown + saneamiento.
      content.innerHTML = data.html;
      for (const link of content.querySelectorAll("a[href]")) {
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
      addCopyAction(exchange, data.markdown);
      dom.question.value = "";
      return [true, "ok", null];
    }
    if (data.kind === "empty") {
      const box = document.createElement("div");
      box.className = "empty-answer";
      const title = document.createElement("strong");
      title.textContent = "Probemos con otra búsqueda";
      const text = document.createElement("p");
      text.textContent = mensaje;
      box.append(title, text);
      content.append(box);
    } else {
      const text = document.createElement("p");
      text.className = "error-answer";
      text.textContent = mensaje;
      content.append(text);
      addRetryAction(exchange, pregunta);
      showError(mensaje);
    }
    return [false, mensaje, null];
  } catch (e) {
    console.error("Error en submitQuestion:", e);
    if (exchange) {
      exchange.querySelector(".answer-content").textContent = "No pudimos completar la consulta. Volvé a intentar.";
    }
    showError("No pudimos completar la consulta. Volvé a intentar.");
    return [false, "No se pudo completar la consulta", null];
  } finally {
    if (ownsRequest) {
      clearTimeout(state.waitTimer);
      setBusy(false);
      if (!dom.dialog.open) dom.question.focus();
    }
  }
}

/** @returns {[boolean,string,null]} */
function newQuery() {
  try {
    if (state.busy) return [false, "Ya hay una consulta en curso", null];
    dom.question.value = "";
    dom.fieldError.textContent = "";
    dom.question.focus();
    dom.scroller.scrollTo({top: dom.scroller.scrollHeight, behavior: "smooth"});
    return [true, "ok", null];
  } catch (e) {
    console.error("Error en newQuery:", e);
    return [false, "No se pudo iniciar una nueva consulta", null];
  }
}

/** @param {KeyboardEvent} event @returns {[boolean,string,null]} */
function handleQuestionKeydown(event) {
  try {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) {
      return [true, "ok", null];
    }
    event.preventDefault();
    if (state.busy || event.repeat) return [false, "Envío no disponible", null];
    dom.form.requestSubmit();
    return [true, "ok", null];
  } catch (e) {
    console.error("Error en handleQuestionKeydown:", e);
    return [false, "No se pudo enviar la consulta con Enter", null];
  }
}

/** @returns {[boolean,string,null]} */
function initialize() {
  try {
    dom.form.addEventListener("submit", submitQuestion);
    dom.question.addEventListener("keydown", handleQuestionKeydown);
    dom.fresh.addEventListener("click", newQuery);
    dom.closeDialog.addEventListener("click", () => dom.dialog.close());
    dom.dialog.addEventListener("close", () => dom.question.focus());
    for (const button of document.querySelectorAll(".suggestion")) {
      button.addEventListener("click", () => {
        dom.question.value = button.dataset.question;
        dom.question.focus();
      });
    }
    return [true, "ok", null];
  } catch (e) {
    console.error("Error en initialize:", e);
    return [false, "No se pudo iniciar la interfaz", null];
  }
}

const [initialized, initializationMessage] = initialize();
if (!initialized) showError(initializationMessage);
