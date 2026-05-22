#!/usr/bin/env python3
"""
genetix-vast pipeline: FLUX 2 dev (T2I) -> LTX 2.3 (I2V)

Usage (на инстансе Vast.ai или с локальной машины через SSH-туннель):

    # 1) запустить локально с туннелем:  ssh -L 18188:127.0.0.1:18188 root@<INSTANCE>
    python pipeline.py \
        --flux-prompt "futuristic egyptian queen in desert, cinematic" \
        --ltx-prompt "smooth push-in, subtle wind, cinematic" \
        --width 1024 --height 1024 \
        --video-width 1280 --video-height 720 \
        --duration 5 --fps 25

Скрипт:
  1. Отправляет workflow FLUX 2 в ComfyUI /prompt.
  2. Ждёт завершения, забирает PNG из output/.
  3. Копирует/загружает PNG в input/ ComfyUI.
  4. Отправляет LTX 2.3 i2v workflow с этим PNG как Load Image.
  5. Ждёт завершения, печатает путь к видео.

Зависимости: только stdlib (urllib, json, uuid, time, argparse).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
from pathlib import Path


COMFY_DEFAULT_BASE = os.environ.get("COMFY_API", "http://127.0.0.1:18188")
CLIENT_ID = str(uuid.uuid4())

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"
FLUX_WORKFLOW_PATH = WORKFLOWS_DIR / "01_flux2_t2i_api.json"
LTX_WORKFLOW_PATH = WORKFLOWS_DIR / "02_ltx23_i2v_api.json"
LTX_SILENT_WORKFLOW_PATH = WORKFLOWS_DIR / "02_ltx23_i2v_silent_api.json"


def http_post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post_multipart(url: str, file_path: Path, extra_fields: dict | None = None) -> dict:
    """Минимальный multipart/form-data загрузчик для /upload/image (без зависимостей)."""
    boundary = f"----genetix{uuid.uuid4().hex}"
    body = bytearray()
    fields = extra_fields or {}
    for k, v in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += f"--{boundary}\r\n".encode()
    body += (
        f'Content-Disposition: form-data; name="image"; filename="{file_path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body += file_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def queue_prompt(base: str, workflow: dict) -> str:
    resp = http_post_json(
        f"{base}/prompt",
        {"prompt": workflow, "client_id": CLIENT_ID},
    )
    if "prompt_id" not in resp:
        raise RuntimeError(f"ComfyUI отказал: {resp}")
    return resp["prompt_id"]


def wait_for_prompt(base: str, prompt_id: str, poll_s: float = 2.0, timeout_s: int = 60 * 30) -> dict:
    """Опрашивает /history/<id> пока не появится результат."""
    started = time.time()
    while True:
        try:
            history = http_get_json(f"{base}/history/{prompt_id}")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            history = {}
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"Workflow завершился ошибкой: {status}")
            if status.get("completed") or entry.get("outputs"):
                return entry
        if time.time() - started > timeout_s:
            raise TimeoutError(f"Превышен таймаут {timeout_s}s ожидания prompt {prompt_id}")
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(poll_s)


def collect_outputs(history_entry: dict, kind: str) -> list[dict]:
    """kind in {'images', 'videos', 'gifs'} — собираем все указанные элементы."""
    items: list[dict] = []
    for node_outputs in history_entry.get("outputs", {}).values():
        for v in node_outputs.get(kind, []) or []:
            items.append(v)
    return items


VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".gif")


def collect_video_outputs(history_entry: dict) -> list[dict]:
    """ComfyUI SaveVideo может класть mp4 в ключи 'videos', 'gifs' или даже 'images'.
    Возвращаем все элементы, имя которых заканчивается на видео-расширение."""
    found: list[dict] = []
    for node_outputs in history_entry.get("outputs", {}).values():
        for key in ("videos", "gifs", "images"):
            for v in node_outputs.get(key, []) or []:
                fn = (v.get("filename") or "").lower()
                if fn.endswith(VIDEO_EXTS):
                    found.append(v)
    return found


def download_file(base: str, item: dict, dest_dir: Path) -> Path:
    """Скачивает файл (image/video) с /view?filename=...&subfolder=...&type=output."""
    params = urllib.parse.urlencode(
        {
            "filename": item["filename"],
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        }
    )
    url = f"{base}/view?{params}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / item["filename"]
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return dest


def upload_image_to_comfy(base: str, image_path: Path, overwrite: bool = True) -> str:
    """Загружает картинку в input/ ComfyUI. Возвращает имя файла, под которым она доступна."""
    resp = http_post_multipart(
        f"{base}/upload/image",
        image_path,
        extra_fields={
            "overwrite": "true" if overwrite else "false",
            "type": "input",
        },
    )
    return resp.get("name") or image_path.name


def load_workflow(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_flux(base: str, args, out_dir: Path) -> Path:
    wf = load_workflow(FLUX_WORKFLOW_PATH)

    wf["6"]["inputs"]["text"] = args.flux_prompt
    wf["25"]["inputs"]["noise_seed"] = (
        args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    )
    wf["26"]["inputs"]["guidance"] = args.flux_guidance
    wf["47"]["inputs"]["width"] = args.width
    wf["47"]["inputs"]["height"] = args.height
    wf["48"]["inputs"]["steps"] = args.flux_steps
    wf["48"]["inputs"]["width"] = args.width
    wf["48"]["inputs"]["height"] = args.height
    wf["9"]["inputs"]["filename_prefix"] = f"flux2/{args.tag}"

    print(f"[FLUX] prompt: {args.flux_prompt!r}")
    print(f"[FLUX] seed={wf['25']['inputs']['noise_seed']} size={args.width}x{args.height} steps={args.flux_steps}")
    pid = queue_prompt(base, wf)
    print(f"[FLUX] prompt_id={pid}, ждём ", end="", flush=True)
    entry = wait_for_prompt(base, pid)
    print(" done")

    imgs = collect_outputs(entry, "images")
    if not imgs:
        raise RuntimeError(f"FLUX не вернул images. entry={entry}")
    img = imgs[0]
    local = download_file(base, img, out_dir)
    print(f"[FLUX] saved: {local}")
    return local


def run_ltx(base: str, args, image_local: Path, out_dir: Path) -> Path:
    uploaded_name = upload_image_to_comfy(base, image_local)
    print(f"[LTX] uploaded image as: {uploaded_name}")

    wf_path = LTX_SILENT_WORKFLOW_PATH if args.silent else LTX_WORKFLOW_PATH
    wf = load_workflow(wf_path)
    print(f"[LTX] workflow: {wf_path.name}")
    wf["269"]["inputs"]["image"] = uploaded_name
    wf["320:319"]["inputs"]["value"] = args.ltx_prompt
    seed1 = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    wf["320:276"]["inputs"]["noise_seed"] = seed1
    if not args.silent:
        seed2 = (seed1 + 1) & 0x7FFFFFFF
        wf["320:277"]["inputs"]["noise_seed"] = seed2
    wf["320:312"]["inputs"]["value"] = args.video_width
    wf["320:299"]["inputs"]["value"] = args.video_height
    wf["320:300"]["inputs"]["value"] = args.fps
    wf["320:301"]["inputs"]["value"] = args.duration
    wf["75"]["inputs"]["filename_prefix"] = f"video/{args.tag}"

    seed_info = f"seed={seed1}" if args.silent else f"seeds=({seed1},{(seed1 + 1) & 0x7FFFFFFF})"
    print(
        f"[LTX] prompt: {args.ltx_prompt!r}\n"
        f"[LTX] size={args.video_width}x{args.video_height} fps={args.fps} duration={args.duration}s {seed_info}"
    )
    pid = queue_prompt(base, wf)
    print(f"[LTX] prompt_id={pid}, ждём ", end="", flush=True)
    entry = wait_for_prompt(base, pid, timeout_s=60 * 60)
    print(" done")

    vids = collect_video_outputs(entry)
    if not vids:
        raise RuntimeError(f"LTX не вернул video. entry={entry}")
    v = vids[0]
    local = download_file(base, v, out_dir)
    print(f"[LTX] saved: {local}")
    return local


def main() -> int:
    p = argparse.ArgumentParser(description="FLUX 2 dev -> LTX 2.3 i2v pipeline")
    p.add_argument("--base", default=COMFY_DEFAULT_BASE, help=f"ComfyUI API base (default {COMFY_DEFAULT_BASE})")
    p.add_argument("--flux-prompt", required=True, help="Промпт для FLUX 2 dev (стартовое изображение)")
    p.add_argument("--ltx-prompt", required=True, help="Промпт для LTX 2.3 i2v (как оживить кадр)")
    p.add_argument("--width", type=int, default=1024, help="FLUX width")
    p.add_argument("--height", type=int, default=1024, help="FLUX height")
    p.add_argument("--flux-steps", type=int, default=28)
    p.add_argument("--flux-guidance", type=float, default=4.0)
    p.add_argument("--video-width", type=int, default=1280)
    p.add_argument("--video-height", type=int, default=720)
    p.add_argument("--duration", type=int, default=5, help="Длительность видео, сек")
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--seed", type=int, default=None, help="Фиксированный seed (одинаковый для FLUX/LTX базовый)")
    p.add_argument("--tag", default=time.strftime("%Y%m%d_%H%M%S"), help="Префикс файлов")
    p.add_argument("--out", default="./out", help="Локальная папка для скачанных результатов")
    p.add_argument("--skip-flux", action="store_true", help="Не запускать FLUX, использовать --image вместо этого")
    p.add_argument("--image", default=None, help="Готовая картинка (если --skip-flux)")
    p.add_argument(
        "--with-audio",
        dest="silent",
        action="store_false",
        help="Использовать полный 2-pass workflow с генерацией аудио (медленнее ~2x)",
    )
    p.set_defaults(silent=True)
    args = p.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.skip_flux:
        if not args.image:
            print("--skip-flux требует --image", file=sys.stderr)
            return 2
        img_local = Path(args.image)
        if not img_local.exists():
            print(f"Файл {img_local} не найден", file=sys.stderr)
            return 2
    else:
        img_local = run_flux(args.base, args, out_dir)

    video_local = run_ltx(args.base, args, img_local, out_dir)
    print("\n✓ Готово.")
    print(f"  image: {img_local}")
    print(f"  video: {video_local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
