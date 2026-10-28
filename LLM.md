
# Ollama - LLM local en Mac mini M4

## Configuración

- Hardware: Apple Mac mini M4 - 16 GB RAM
- Sistema operativo: macOS
- Instalación: Homebrew (nativa, sin Docker)
- Versión comprobada: Ollama 0.40.11
- Modelo: Qwen 3.5 2B (Q4_K_M)
- API local: http://localhost:11434
- API desde Windows: http://macmini:11434
- Inicio: MANUAL
- Aceleración: GPU Apple Silicon (Metal)
- Memoria del modelo cargado: 1,6 GB aprox.
- Motor de inferencia: llama.cpp

## Instalación de Ollama

```bash
brew install ollama
```

Verificar instalación:

```bash
ollama --version
```

## Encender Ollama manualmente

```bash
brew services run ollama
```

Inicia Ollama sin configurar arranque automático.

## Verificar estado

```bash
brew services list
```

Comprobar que responde la API:

```bash
curl http://localhost:11434/api/version
```

## Descargar Qwen (solo la primera vez)

```bash
ollama pull qwen3.5:2b-q4_K_M
```

## Listar modelos instalados

```bash
ollama list
```

## Ejecutar Qwen interactivamente

```bash
ollama run qwen3.5:2b-q4_K_M
```

Para salir del chat:

```text
/bye
```

## Ver modelos cargados en memoria

```bash
ollama ps
```

## Descargar Qwen de RAM/GPU sin apagar Ollama

```bash
ollama stop qwen3.5:2b-q4_K_M
```

El servidor continúa funcionando.

## Apagar completamente Ollama

```bash
brew services stop ollama
```

- Detiene el servidor.
- Descarga los modelos de RAM/GPU.
- Libera los recursos utilizados.
- NO elimina los modelos descargados.

## Verificar que Ollama está apagado

```bash
curl http://localhost:11434/api/version
```

Resultado esperado: error de conexión.

## Acceso desde la red local

Dirección del servidor:

```text
http://macmini:11434
```

Endpoints principales:

| Endpoint | Método | Función |
|----------|--------|---------|
| /api/version | GET | Versión de Ollama |
| /api/tags | GET | Modelos instalados |
| /api/ps | GET | Modelos cargados |
| /api/chat | POST | Chat con el modelo |
| /api/generate | POST | Generación de texto |

### Configuración en carreRAGs

```env
OLLAMA_BASE_URL=http://macmini:11434
OLLAMA_MODEL=qwen3.5:2b-q4_K_M
```

Desde Docker Desktop también puede utilizarse:

```text
http://host.docker.internal:11434
```

La conectividad debe comprobarse desde el contenedor.

### Seguridad

Ollama escucha conexiones de red cuando se configura:

```text
OLLAMA_HOST=0.0.0.0:11434
```

La API no exige autenticación por defecto.

- Restringir acceso a equipos de confianza.
- No exponer el puerto 11434 a Internet.
- Mantener el control del servicio manualmente.

## Notas importantes

- Ollama utiliza la GPU del M4 mediante Metal.
- No se ejecuta dentro de Docker.
- Los modelos se almacenan en ~/.ollama/models.
- Apagar Ollama NO elimina los modelos.
- No es necesario ejecutar `ollama stop` antes de apagar el servicio.
- `brew services run` no configura arranque automático.
- Los modelos se descargan automáticamente de RAM tras un período de inactividad.
- Una nueva consulta vuelve a cargar el modelo.
- El acceso HTTP desde Windows fue comprobado correctamente.

## Comandos habituales

ENCENDER:
```bash
brew services run ollama
```

VER ESTADO:
```bash
brew services list
```

VER MODELOS ACTIVOS:
```bash
ollama ps
```

APAGAR:
```bash
brew services stop ollama
```
