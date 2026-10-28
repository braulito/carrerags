"""Identidad compatible con carrerags_ingesta.adapters.local."""

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
DIMENSIONS = 384
SPACE = f"sentence-transformers:{MODEL_ID}:{REVISION}:normalized-v1:{DIMENSIONS}"
MODEL_PATH = "/opt/models/minilm"
MAX_TEXTS = 128
MAX_TEXT_LENGTH = 16000
MAX_TOTAL_CHARS = 250000
MAX_BODY_BYTES = 1048576
