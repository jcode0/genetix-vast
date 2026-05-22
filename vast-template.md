# genetix-vast — Vast.ai Template

> Репозиторий: `https://github.com/jcode0/genetix-vast` (должен быть public, иначе vast не сможет скачать manifest).

## Образ

```
vastai/comfy:v0.18.2-cuda-12.9-py312
```

Свой образ не нужен — все модели и workflow тянутся **PROVISIONING_MANIFEST** при первом запуске. Если позже захотите зафиксировать конфиг — соберите свой образ с `COPY provisioning/manifest.yaml /provisioning.yaml`.

## Docker Options (вставлять целиком в поле «Docker Options» при редактировании template)

```text
-p 1111:1111 -p 8080:8080 -p 8384:8384 -p 72299:72299 -p 8188:8188 -p 8288:8288
-e COMFYUI_ARGS="--disable-auto-launch --disable-xformers --port 18188 --enable-cors-header"
-e COMFYUI_API_BASE="http://localhost:18188"
-e OPEN_BUTTON_PORT="1111"
-e OPEN_BUTTON_TOKEN="1"
-e JUPYTER_DIR="/"
-e DATA_DIRECTORY="/workspace/"
-e PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8288:18288:/docs:API Wrapper|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal|localhost:8384:18384:/:Syncthing"
-e PROVISIONING_MANIFEST="https://raw.githubusercontent.com/jcode0/genetix-vast/main/provisioning/manifest.yaml"
```

Дополнительные env (опционально, если модели за gate-ом):
```text
-e HF_TOKEN=<your_hf_token>
```

## On-start command

```
entrypoint.sh
```

## Параметры инстанса

| Параметр | Рекомендация |
|----------|--------------|
| Disk | **150 GB** (минимум 120 GB) |
| GPU | **≥24 GB VRAM** — RTX 4090 / A5000 / A6000 / L40 / H100 |
| Jupyter | on |
| SSH | on |
| Direct IP | on |

## Vast.ai CLI команда

```bash
vastai create instance <OFFER_ID> \
  --image vastai/comfy:v0.18.2-cuda-12.9-py312 \
  --env '-p 1111:1111 -p 8080:8080 -p 8384:8384 -p 72299:72299 -p 8188:8188 -p 8288:8288 -e COMFYUI_ARGS="--disable-auto-launch --disable-xformers --port 18188 --enable-cors-header" -e COMFYUI_API_BASE="http://localhost:18188" -e OPEN_BUTTON_PORT="1111" -e OPEN_BUTTON_TOKEN="1" -e JUPYTER_DIR="/" -e DATA_DIRECTORY="/workspace/" -e PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8288:18288:/docs:API Wrapper|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal|localhost:8384:18384:/:Syncthing" -e PROVISIONING_MANIFEST="https://raw.githubusercontent.com/jcode0/genetix-vast/main/provisioning/manifest.yaml"' \
  --onstart-cmd 'entrypoint.sh' \
  --disk 150 --jupyter --ssh --direct
```

Где найти `<OFFER_ID>`:
```bash
vastai search offers 'gpu_ram>=24 disk_space>=150 cuda_vers>=12.4 reliability>0.95' -o 'dph_total'
```
