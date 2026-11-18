"""Prepare the workspace-local binaries used by coordinated frontend checks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from hydra_orch.bridge.agent_executable import resolve_npm_node_script, run_windows_cmd_sync
from hydra_orch.core.git_workspace import is_link_or_junction


LOCKS = {"npm": ("npm-shrinkwrap.json", "package-lock.json"),
         "pnpm": ("pnpm-lock.yaml",), "yarn": ("yarn.lock",), "bun": ("bun.lock", "bun.lockb")}
BINARIES = {"typescript": "typescript/bin/tsc", "frontend_build": "vite/bin/vite.js",
            "vitest": "vitest/vitest.mjs", "eslint": "eslint/bin/eslint.js"}


def prepare(workspace: Path, cwd: Path, check_kind: str) -> int:
    workspace, cwd = workspace.resolve(), cwd.resolve()
    if not cwd.is_relative_to(workspace):
        raise ValueError("O diretório do pacote deve estar na cópia isolada.")

    binary = BINARIES[check_kind]
    paths = (binary, BINARIES["typescript"]) if check_kind == "frontend_build" else (binary,)
    # Node also resolves packages hoisted to an ancestor in a monorepo.
    def ready() -> bool:
        return all(any((root / "node_modules" / name).is_file() and
                       (root / "node_modules" / name).resolve().is_relative_to(workspace)
                       for root in (cwd, *cwd.parents) if root.is_relative_to(workspace)) for name in paths)

    if ready():
        print("Binários disponíveis na cópia isolada.")
        return 0

    manifests = [root for root in (cwd, *cwd.parents) if root.is_relative_to(workspace)
                 and (root / "package.json").is_file()]
    if not manifests:
        raise ValueError("Nenhum package.json encontrado na cópia isolada.")
    package_root = next((root for root in manifests if any((root / name).is_file()
                         for names in LOCKS.values() for name in names)), manifests[0])
    manifest = package_root / "package.json"
    locks = {manager for manager, names in LOCKS.items() if any((package_root / name).is_file() for name in names)}
    if any(is_link_or_junction(path) for path in (manifest, package_root / "node_modules",
           *(package_root / name for names in LOCKS.values() for name in names))):
        raise ValueError("O manifesto, lockfile e node_modules devem pertencer à cópia isolada.")
    declaration = str(json.loads(manifest.read_text(encoding="utf-8-sig")).get("packageManager", ""))
    declared = declaration.split("@", 1)[0]
    manager = declared or (next(iter(locks)) if len(locks) == 1 else "npm")
    if manager not in LOCKS or (locks and manager not in locks) or (not declared and len(locks) > 1):
        raise ValueError("O gerenciador declarado e os lockfiles do projeto são incompatíveis.")
    executable = shutil.which(manager)
    if executable is None:
        raise ValueError(f"Gerenciador {manager} indisponível para a verificação.")

    if not locks and manager != "npm":
        raise ValueError(f"Gere o lockfile de {manager} para preparar a cópia de forma reproduzível.")
    options = {
        "npm": ["ci", "--ignore-scripts", "--no-audit", "--no-fund"] if locks else
               ["install", "--ignore-scripts", "--no-package-lock", "--no-audit", "--no-fund"],
        "pnpm": ["install", "--frozen-lockfile", "--ignore-scripts", "--ignore-pnpmfile"],
        "yarn": ["install", "--immutable"],
        "bun": ["install", "--frozen-lockfile", "--ignore-scripts"],
    }[manager]
    if manager == "yarn":
        with (package_root / "yarn.lock").open(encoding="utf-8-sig", errors="replace") as lock:
            if declaration.startswith("yarn@1.") or "yarn lockfile v1" in lock.read(256):
                options = ["install", "--frozen-lockfile", "--ignore-scripts"]
        if (package_root / ".hydra-disabled-yarnrc.yml").exists():
            raise ValueError("O projeto contém um arquivo reservado à configuração isolada do Yarn.")
    print(f"Preparando {package_root.relative_to(workspace)} com {manager} "
          f"({'lockfile fixado' if locks else 'versões resolvidas pelo manifesto, sem gravar lockfile'}).", flush=True)
    env = {**os.environ, "YARN_IGNORE_PATH": "1", "YARN_ENABLE_SCRIPTS": "false",
           "YARN_RC_FILENAME": ".hydra-disabled-yarnrc.yml", "COREPACK_ENABLE_NETWORK": "0"}
    args = [executable, *options]
    kwargs = {"cwd": package_root, "env": env, "stdin": subprocess.DEVNULL}
    if os.name == "nt" and executable.lower().endswith((".cmd", ".bat")):
        npm_target = resolve_npm_node_script(executable)
        result = (subprocess.run([*npm_target, *options], **kwargs) if npm_target
                  else run_windows_cmd_sync(args, **kwargs))
    else:
        result = subprocess.run(args, **kwargs)
    if result.returncode:
        return result.returncode
    if not ready():
        raise ValueError(f"A instalação terminou sem os binários esperados para {check_kind}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(prepare(Path(os.environ["HYDRA_CHECK_WORKSPACE"]), Path.cwd(), sys.argv[1]))
    except (OSError, ValueError, KeyError) as exc:
        print(f"Preparação de dependências: {exc}", file=sys.stderr)
        sys.exit(1)
