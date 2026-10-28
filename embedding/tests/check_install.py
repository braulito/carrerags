"""Verificar Bash y flujos del instalador sin Docker, descargas ni servicios reales."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

logger = logging.getLogger(__name__)


def find_bash() -> tuple[bool, str, str]:
    try:
        if sys.platform == "win32":
            git = shutil.which("git")
            if git:
                root = Path(git).resolve().parent.parent
                for candidate in [root / "usr/bin/bash.exe", root / "bin/bash.exe"]:
                    if candidate.is_file():
                        return True, "ok", str(candidate)
            raise ValueError("Las pruebas del instalador en Windows requieren Bash de Git")
        bash = shutil.which("bash")
        if not bash:
            raise ValueError("Las pruebas del instalador requieren Bash")
        return True, "ok", bash
    except Exception as e:
        logger.error("Error en find_bash: %s", e)
        return False, "No se encontró Bash para verificar install.sh", ""


def check_installer() -> tuple[bool, str, dict[str, Any]]:
    try:
        ok, message, bash = find_bash()
        if not ok:
            return False, message, {}
        source = Path(__file__).resolve().parents[1] / "install.sh"
        process_env = {**os.environ, "BASH_ENV": "", "ENV": ""}
        syntax = subprocess.run([bash, "--noprofile", "--norc", "-n", str(source)],
                                env=process_env, capture_output=True, text=True, timeout=15)
        assert syntax.returncode == 0, syntax.stderr
        assert b"\r" not in source.read_bytes(), "El instalador debe conservar finales LF"
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            component = root / "embedding con espacios"
            component.mkdir()
            script = component / "install.sh"
            script.write_bytes(source.read_bytes())
            for name in ["compose.yaml", "nginx.conf", "Dockerfile"]:
                (component / name).write_text("fixture: los comandos se simulan\n", encoding="utf-8")
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            docker = fake_bin / "docker"
            docker.write_text('''#!/usr/bin/env bash
set -eu
[[ "${COMPOSE_DISABLE_ENV_FILE:-}" == 1 ]] || exit 96
[[ "${COMPOSE_ENV_FILES+x}" != x ]] || exit 97
printf 'docker %s\n' "$*" >> "$EMBED_INSTALL_TEST_LOG"
case "$*" in
    'info') [[ "$EMBED_INSTALL_TEST_SCENARIO" != daemon_down ]] ;;
    'info --format '*)
        if [[ "$EMBED_INSTALL_TEST_SCENARIO" == wrong_arch ]]; then
            printf 'linux/x86_64\n'
        else
            printf 'linux/aarch64\n'
        fi ;;
    'compose version') printf '2.39.0\n' ;;
    'image inspect '*)
        [[ "$EMBED_INSTALL_TEST_SCENARIO" != missing ]] || exit 1
        printf 'linux/arm64\n' ;;
    *' config --quiet'|*' build embeddings'|*' pull gateway') exit 0 ;;
    *' run --rm --no-deps --pull never --entrypoint nginx gateway -t -c /etc/nginx/nginx.conf')
        [[ "$EMBED_INSTALL_TEST_SCENARIO" != bad_nginx ]] ;;
    *' up -d --no-build --pull never --wait --wait-timeout 240') exit 0 ;;
    *' ps') printf 'gateway healthy 0.0.0.0:8081->8081/tcp\n' ;;
    *' port gateway 8081') printf '0.0.0.0:8081\n' ;;
    *) printf 'Comando Docker simulado no esperado\n' >&2; exit 95 ;;
esac
''', encoding="utf-8", newline="\n")
            uname = fake_bin / "uname"
            uname.write_text('''#!/usr/bin/env bash
case "$1" in
    -s) printf 'Darwin\n' ;;
    -m) printf 'arm64\n' ;;
    *) exit 1 ;;
esac
''', encoding="utf-8", newline="\n")
            curl = fake_bin / "curl"
            curl.write_text('''#!/usr/bin/env bash
[[ "$EMBED_INSTALL_TEST_SCENARIO" != health_failed ]] || exit 7
if [[ "$EMBED_INSTALL_TEST_SCENARIO" == wrong_health ]]; then
    printf '{"resultado":true,"salida":{"dimensions":128}}\n'
else
    printf '{"resultado":true,"salida":{"dimensions":384}}\n'
fi
''', encoding="utf-8", newline="\n")
            for command in [docker, uname, curl]:
                command.chmod(0o755)
            wrapper = '''export PATH="/usr/bin:/bin:$PATH"
if command -v cygpath >/dev/null 2>&1; then
    EMBED_TEST_BIN="$(cygpath -u "$1")"
    EMBED_TEST_LOG="$(cygpath -u "$2")"
    EMBED_TEST_SCRIPT="$(cygpath -u "$3")"
else
    EMBED_TEST_BIN="$1"
    EMBED_TEST_LOG="$2"
    EMBED_TEST_SCRIPT="$3"
fi
export PATH="$EMBED_TEST_BIN:$PATH"
export EMBED_INSTALL_TEST_LOG="$EMBED_TEST_LOG"
bash --noprofile --norc "$EMBED_TEST_SCRIPT" "${@:4}"
'''
            cases = [("cached", [], True), ("missing", [], True), ("cached", ["--rebuild"], True),
                     ("cached", ["--offline"], True), ("missing", ["--offline"], False),
                     ("wrong_arch", [], False), ("daemon_down", [], False), ("bad_nginx", [], False),
                     ("health_failed", [], False), ("wrong_health", [], False)]
            for number, (scenario, options, expected) in enumerate(cases):
                log = root / ("commands-" + str(number) + ".txt")
                result = subprocess.run([bash, "--noprofile", "--norc", "-c", wrapper, "fixture",
                                         str(fake_bin), str(log), str(script), *options], cwd=root,
                                        env={**process_env, "EMBED_INSTALL_TEST_SCENARIO": scenario,
                                             "COMPOSE_ENV_FILES": "ficticio_no_abrir"},
                                        capture_output=True, text=True, encoding="utf-8", timeout=30)
                assert (result.returncode == 0) is expected, (scenario, options, result.stdout, result.stderr)
                commands = log.read_text(encoding="utf-8") if log.exists() else ""
                assert ("Instalación completada" in result.stdout) is expected
                if expected:
                    assert "--no-build --pull never --wait" in commands
                    assert "--no-deps --pull never --entrypoint nginx" in commands
                    assert " port gateway 8081" in commands
                if options == ["--offline"]:
                    assert " build embeddings" not in commands and " pull gateway" not in commands
                if scenario == "cached" and not options:
                    assert " build embeddings" not in commands and " pull gateway" not in commands
                if scenario == "missing" and not options:
                    assert " build embeddings" in commands and " pull gateway" in commands
                if options == ["--rebuild"]:
                    assert " build embeddings" in commands
                if scenario in {"wrong_arch", "daemon_down", "bad_nginx"}:
                    assert " up -d" not in commands
        return True, "ok", {"scenarios": len(cases), "bash_syntax": True}
    except Exception as e:
        logger.error("Error en check_installer: %s", e)
        return False, "Falló el instalador simulado: " + str(e), {}
