"""API base del componente llm."""

from fastapi import FastAPI

from helpers.configuracion_logs import configurar_logs
from routers.estado import router as estado_router
from routers.llmrag import router as llmrag_router

resultado_logs, mensaje_logs, _ = configurar_logs()
if not resultado_logs:
    raise RuntimeError(mensaje_logs)

app = FastAPI(title="llm", version="0.1.0", description="API de servicios LLM.")


app.include_router(estado_router)
app.include_router(llmrag_router)
