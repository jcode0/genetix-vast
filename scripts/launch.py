#!/usr/bin/env python3
"""
Запуск инстанса Vast.ai одной командой, минуя проблемы PowerShell
с вложенными кавычками в --env.

Использование:
    python scripts/launch.py <OFFER_ID>
    python scripts/launch.py <OFFER_ID> --disk 250
    python scripts/launch.py <OFFER_ID> --hf-token hf_xxxx
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


MANIFEST_URL = (
    "https://raw.githubusercontent.com/jcode0/genetix-vast/main/provisioning/manifest.yaml"
)

PORTAL_CONFIG = (
    "localhost:1111:11111:/:Instance Portal"
    "|localhost:8188:18188:/:ComfyUI"
    "|localhost:8288:18288:/docs:API Wrapper"
    "|localhost:8080:18080:/:Jupyter"
    "|localhost:8080:8080:/terminals/1:Jupyter Terminal"
    "|localhost:8384:18384:/:Syncthing"
)


def build_env(hf_token: str | None) -> str:
    parts = [
        "-p 1111:1111",
        "-p 8080:8080",
        "-p 8384:8384",
        "-p 72299:72299",
        "-p 8188:8188",
        "-p 8288:8288",
        '-e COMFYUI_ARGS="--disable-auto-launch --disable-xformers --port 18188 --enable-cors-header"',
        '-e COMFYUI_API_BASE="http://localhost:18188"',
        '-e OPEN_BUTTON_PORT="1111"',
        '-e OPEN_BUTTON_TOKEN="1"',
        '-e JUPYTER_DIR="/"',
        '-e DATA_DIRECTORY="/workspace/"',
        f'-e PORTAL_CONFIG="{PORTAL_CONFIG}"',
        f'-e PROVISIONING_MANIFEST="{MANIFEST_URL}"',
    ]
    if hf_token:
        parts.append(f'-e HF_TOKEN="{hf_token}"')
    return " ".join(parts)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("offer_id", help="Vast.ai offer ID (из vastai search offers)")
    p.add_argument("--image", default="vastai/comfy:v0.18.2-cuda-12.9-py312")
    p.add_argument("--disk", type=int, default=200, help="Disk GB (default 200)")
    p.add_argument("--hf-token", default=None, help="HuggingFace token (опционально)")
    args = p.parse_args()

    if shutil.which("vastai") is None:
        print("ERROR: vastai CLI не найден. Сделайте `pip install --upgrade vastai`.", file=sys.stderr)
        return 1

    cmd = [
        "vastai",
        "create",
        "instance",
        str(args.offer_id),
        "--image",
        args.image,
        "--env",
        build_env(args.hf_token),
        "--onstart-cmd",
        "entrypoint.sh",
        "--disk",
        str(args.disk),
        "--jupyter",
        "--ssh",
        "--direct",
    ]

    print("Запускаю команду:")
    print("  " + " ".join(f'"{c}"' if " " in c or '"' in c else c for c in cmd))
    print()

    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
