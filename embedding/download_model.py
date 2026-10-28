"""Solo se ejecuta durante docker build; pesos públicos de una revisión inmutable."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from carrerags_embeddings.constants import DIMENSIONS, MODEL_ID, MODEL_PATH, REVISION, SPACE

logger = logging.getLogger(__name__)


def download(destination: Path = Path(MODEL_PATH)) -> tuple[bool, str, str]:
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=MODEL_ID, revision=REVISION, local_dir=str(destination), token=False,
                          allow_patterns=["*.json", "*.txt", "*.model", "model.safetensors", "1_Pooling/*"],
                          ignore_patterns=["onnx/*", "openvino/*", ".env", ".env.*", "*.env",
                                           "**/.env", "**/.env.*", "**/*.env"])
        (destination / "carrerags-model.json").write_text(json.dumps({
            "model": MODEL_ID, "revision": REVISION, "space": SPACE, "dimensions": DIMENSIONS,
        }), encoding="utf-8")
        # Verificación local del artefacto: falla la construcción si faltan archivos.
        from carrerags_embeddings.model import load_model

        ok, message, model = load_model(destination)
        if not ok or model is None:
            return False, message, ""
        ok, message, vectors = model.encode(["Verificación local de embeddings"])
        if not ok or len(vectors) != 1:
            return False, message, ""
        return True, "ok", str(destination)
    except Exception as e:
        logger.error("Error en download: %s", e)
        return False, "No se pudo preparar el modelo fijado", ""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success, message, _ = download()
    if not success:
        logger.error("%s", message)
    raise SystemExit(0 if success else 1)
