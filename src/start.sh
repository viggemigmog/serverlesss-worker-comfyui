#!/usr/bin/env bash

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

# Ensure ComfyUI-Manager runs in offline network mode inside the container
comfy-manager-set-mode offline || echo "worker-comfyui - Could not set ComfyUI-Manager network_mode" >&2

# Setup cached model (zimageturbo-minimal) from RunPod cache into models/unet, loras, clip, vae
echo "worker-comfyui: Setting up cached model..."
python -u /setup_cached_models.py

echo "worker-comfyui: Starting ComfyUI"

# Allow operators to tweak verbosity; default is DEBUG.
: "${COMFY_LOG_LEVEL:=DEBUG}"

# Serve the API and don't shutdown the container
if [ "$SERVE_API_LOCALLY" == "true" ]; then
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --listen --verbose "${COMFY_LOG_LEVEL}" --log-stdout &
else
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --verbose "${COMFY_LOG_LEVEL}" --log-stdout &
fi

# Wait for ComfyUI to be reachable before starting the handler (avoids basic_test failing on cold start)
echo "worker-comfyui: Waiting for ComfyUI API at 127.0.0.1:8188..."
max_wait="${COMFY_READY_WAIT_SEC:-120}"
elapsed=0
while [ "$elapsed" -lt "$max_wait" ]; do
  if python -c "
import urllib.request
try:
    urllib.request.urlopen('http://127.0.0.1:8188/', timeout=2)
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; then
    echo "worker-comfyui: ComfyUI API is ready."
    break
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done
if [ "$elapsed" -ge "$max_wait" ]; then
  echo "worker-comfyui: WARNING - ComfyUI did not become ready in ${max_wait}s; starting handler anyway."
fi

echo "worker-comfyui: Starting RunPod Handler"
if [ "$SERVE_API_LOCALLY" == "true" ]; then
    python -u /handler.py --rp_serve_api --rp_api_host=0.0.0.0
else
    python -u /handler.py
fi