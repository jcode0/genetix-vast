# genetix-vast

Шаблон Vast.ai для пайплайна **FLUX 2 dev (T2I) → LTX 2.3 (I2V)** на одном инстансе ComfyUI.

```
prompt_1 ──► FLUX 2 dev ──► image.png ──► LTX 2.3 i2v ──► video.mp4
                                              ▲
                                              └── prompt_2
```

- Образ: `vastai/comfy:v0.18.2-cuda-12.9-py312`
- Дополнительный Docker-образ собирать **не нужно** — модели тянет provisioning при первом старте.
- Качаются **только** модели из `provisioning/manifest.yaml` — никаких сторонних весов из шаблонов Vast.

## Структура репозитория

```
genetix-vast/
├── provisioning/
│   └── manifest.yaml            # PROVISIONING_MANIFEST: модели + custom node + два workflow
├── workflows/
│   ├── 01_flux2_t2i_api.json    # API-формат FLUX 2 dev T2I (для pipeline.py)
│   └── 02_ltx23_i2v_api.json    # API-формат LTX 2.3 i2v
├── scripts/
│   └── pipeline.py              # Цепочка FLUX → LTX через ComfyUI API
├── vast-template.md             # Docker Options + CLI команда для Vast.ai
└── README.md
```

## Что качается (сводно)

| Группа | Файл | HF путь | Назначение |
|---|---|---|---|
| FLUX | `flux2_dev_fp8mixed.safetensors` | `Comfy-Org/flux2-dev/split_files/diffusion_models/` | UNET, ~16 GB |
| FLUX | `flux2-vae.safetensors` | `Comfy-Org/flux2-dev/split_files/vae/` | VAE |
| FLUX | `mistral_3_small_flux2_fp8.safetensors` | `Comfy-Org/flux2-dev/split_files/text_encoders/` | Text encoder |
| FLUX | `Flux2TurboComfyv2.safetensors` *(опц.)* | `Comfy-Org/flux2-dev/split_files/loras/` | Turbo LoRA, 8 steps |
| LTX | `ltx-2.3-22b-dev-fp8.safetensors` | `Lightricks/LTX-2.3-fp8/` | Основной чекпоинт LTX 2.3 |
| LTX | `ltx-2.3-22b-distilled-lora-384.safetensors` | `Lightricks/LTX-2.3/` | Distilled LoRA (ускорение) |
| LTX | `gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors` | `Comfy-Org/ltx-2/split_files/loras/` | Gemma LoRA |
| LTX | `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | `Lightricks/LTX-2.3/` | Spatial upscale x2 |
| LTX | `gemma_3_12B_it_fp4_mixed.safetensors` | `Comfy-Org/ltx-2/split_files/text_encoders/` | Text encoder |
| Custom node | `ComfyUI-LTXVideo` | `github.com/Lightricks/ComfyUI-LTXVideo` | Нужен для LTXV* нод |

**Итог:** ~55 GB моделей. Disk на инстансе ставьте **150 GB**.

## Развёртывание

### 1. Закоммитьте репозиторий

Нужен публично доступный raw URL до `provisioning/manifest.yaml`. Положите в GitHub:

```bash
git init
git add .
git commit -m "initial: genetix-vast FLUX2+LTX2.3 template"
git branch -M main
git remote add origin git@github.com:jcode0/genetix-vast.git
git push -u origin main
```

После пуша raw URL:
```
https://raw.githubusercontent.com/jcode0/genetix-vast/main/provisioning/manifest.yaml
```

### 2. Создайте template на Vast.ai

Параметры — см. `vast-template.md`. Главное:

- **Image:** `vastai/comfy:v0.18.2-cuda-12.9-py312`
- **Docker Options:** содержит `-e PROVISIONING_MANIFEST="https://raw.githubusercontent.com/jcode0/genetix-vast/main/provisioning/manifest.yaml"`
- **Disk:** 150 GB
- **GPU:** ≥24 GB VRAM

### 3. Rent инстанс

При первом запуске:
1. Скачивается образ (~10–15 мин).
2. Provisioner качает ~55 GB моделей и клонирует custom node (~10–30 мин в зависимости от линка).
3. Когда появится зелёный «Running» — открываем Instance Portal → Launch ComfyUI.

В сайдбаре `Workflows → Browse` появятся `01_flux2_t2i` и `02_ltx23_i2v`.

> Проверить прогресс: SSH в инстанс → `supervisorctl tail -f comfyui` или `tail -f /var/log/portal/comfyui.log`.

## Использование

### Вариант A — вручную в ComfyUI UI

1. Откройте workflow `01_flux2_t2i` → впишите промпт → Run → дождитесь PNG в `output/flux2/...`.
2. Откройте workflow `02_ltx23_i2v` → в ноду `Load Image` загрузите/выберите PNG из шага 1 → впишите промпт движения → Run.
3. Видео появится в `output/video/...`.

> Workflow `02_ltx23_i2v` генерирует **видео с аудио** (LTX 2.3 — joint audio-video). Если нужен «немой» клип — просто выкиньте/Bypass-ните audio-выходы и `SaveVideo` ноду подключите к `VAEDecodeTiled` напрямую.

### Вариант B — автоматически через `pipeline.py`

С локальной машины через SSH-туннель:

```bash
# 1. Туннель ComfyUI API
ssh -L 18188:127.0.0.1:18188 root@<VAST_INSTANCE_IP> -p <SSH_PORT>

# 2. В другом терминале — запуск цепочки
python scripts/pipeline.py \
  --flux-prompt "futuristic egyptian queen in desert at sunset, cinematic, photoreal" \
  --ltx-prompt  "smooth slow push-in, subtle wind, sand particles, cinematic" \
  --width 1024 --height 1024 \
  --video-width 1280 --video-height 720 \
  --duration 5 --fps 25 \
  --out ./out
```

Результаты лягут в `./out/`. Скрипт сам:
1. Шлёт FLUX workflow, ждёт PNG.
2. Загружает PNG в `input/` ComfyUI через `/upload/image`.
3. Шлёт LTX workflow с этим именем.
4. Скачивает финальный mp4.

### Прямо на инстансе (без туннеля)

```bash
ssh root@<VAST_INSTANCE_IP> -p <SSH_PORT>
cd /workspace
git clone https://github.com/jcode0/genetix-vast.git
cd genetix-vast
python3 scripts/pipeline.py --flux-prompt "..." --ltx-prompt "..."
```

## Параметры pipeline.py

| Флаг | По умолчанию | Описание |
|---|---|---|
| `--flux-prompt` | required | Промпт для FLUX (стартовый кадр) |
| `--ltx-prompt`  | required | Промпт для LTX (как оживить) |
| `--width / --height` | 1024 / 1024 | Размер кадра FLUX |
| `--flux-steps` | 28 | Шагов FLUX (8 при Turbo LoRA) |
| `--flux-guidance` | 4.0 | CFG для FLUX |
| `--video-width / --video-height` | 1280 / 720 | Размер видео |
| `--duration` | 5 | Длительность, сек |
| `--fps` | 25 | Кадров/сек |
| `--seed` | random | Фиксированный seed |
| `--skip-flux --image PATH` | — | Использовать готовую картинку |
| `--base` | `http://127.0.0.1:18188` | URL ComfyUI API |

## Подключение Turbo LoRA (опционально)

`Flux2TurboComfyv2.safetensors` качается в `models/loras/`. Чтобы получить **8 шагов вместо 28**, добавьте в `01_flux2_t2i_api.json` ноду:

```json
"50": {
  "inputs": {
    "lora_name": "Flux2TurboComfyv2.safetensors",
    "strength_model": 1.0,
    "model": ["12", 0]
  },
  "class_type": "LoraLoaderModelOnly",
  "_meta": {"title": "Turbo LoRA"}
}
```

И в ноду `"22"` (BasicGuider) подайте `["50", 0]` вместо `["12", 0]`. Снизьте `--flux-steps 8`.

## Тонкости и подводные камни

- **VRAM.** FLUX 2 fp8 + LTX 2.3 22B fp8 одновременно в памяти не помещаются. ComfyUI выгружает первую модель перед запуском второй (это нормальное поведение, замедления секунды).
- **Первый запуск ~30 мин.** Provisioner кэширует прогресс в `/.provisioner_state/`, повторные `supervisorctl restart comfyui` мгновенные.
- **`/.provisioning_complete`** — флаг успеха. Если provisioning упал, удалите файл и перезагрузите инстанс.
- **HF rate limits.** Если упёрлись — добавьте `-e HF_TOKEN=...` в Docker Options.
- **Audio в LTX 2.3.** Модель совмещённая (audio+video). Чтобы получить немое видео, в UI отключите audio-ноды или сделайте свой урезанный workflow.
- **Workflow JSON в репо ≠ workflow в ComfyUI.** В `workflows/` — **API-формат** (плоский dict нод) для `pipeline.py`. В UI ComfyUI открываются **GUI-формат** workflow, скачанные manifest'ом из `Comfy-Org/workflow_templates`.

## Лицензии моделей

- **FLUX 2 dev** — Black Forest Labs FLUX 2 license (non-commercial по умолчанию, см. карточку модели).
- **LTX 2.3** — Lightricks LTX Video license (см. карточку модели).
- **Gemma 3** — Google Gemma Terms of Use.

Перед коммерческим использованием — прочитайте лицензии на HuggingFace.
