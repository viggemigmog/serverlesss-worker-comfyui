#!/usr/bin/env python3
"""
Setup script to symlink RunPod's cached Hugging Face model (Z-Image-Turbo)
into ComfyUI's unet folder.

RunPod downloads the model to /runpod-volume/huggingface-cache/hub/ when you
configure the endpoint's Model field. This script symlinks the transformer
weights into /runpod-volume/models/unet/ so ComfyUI can load them.

Reference: https://docs.runpod.io/serverless/endpoints/model-caching
"""
import os
import sys
from pathlib import Path

CACHE_ROOT = Path("/runpod-volume/huggingface-cache/hub")
COMFYUI_UNET = Path("/runpod-volume/models/unet")

# Default model when RunPod Model field is set to Tongyi-MAI/Z-Image-Turbo
DEFAULT_CACHED_MODEL_ID = "Tongyi-MAI/Z-Image-Turbo"

# Diffusers layout: transformer/ contains the DiT .safetensors
HF_TRANSFORMER_SUBDIR = "transformer"


def resolve_snapshot_path(model_id: str) -> Path | None:
    """Resolve the cached model snapshot directory for a HuggingFace model ID."""
    if "/" not in model_id:
        return None
    org, name = model_id.split("/", 1)
    model_dir = CACHE_ROOT / f"models--{org}--{name}"
    if not model_dir.exists():
        return None
    ref_main = model_dir / "refs" / "main"
    if ref_main.exists():
        rev = ref_main.read_text().strip()
        snap = model_dir / "snapshots" / rev
        if snap.exists():
            return snap
    snap_root = model_dir / "snapshots"
    if snap_root.exists():
        snaps = sorted(snap_root.glob("*"))
        if snaps:
            return snaps[0]
    return None


# Filename workflows expect so they see one "Z-Image-Turbo" option; when cache
# is present we expose the cached file under this name so cache is used first.
Z_IMAGE_TURBO_UNET_FILENAME = "z_image_turbo_bf16.safetensors"


def setup_z_image_turbo_from_cache(model_id: str) -> bool:
    """
    Symlink the cached model's transformer weights into ComfyUI unet folder.
    Uses the standard filename so ComfyUI/workflows prefer this over the baked-in
    file in /comfyui/models/unet/. When cache is absent, the baked-in file is
    used (from the Dockerfile).
    Returns True if symlinks were created, False otherwise.
    """
    snapshot_path = resolve_snapshot_path(model_id)
    if not snapshot_path:
        return False

    transformer_dir = snapshot_path / HF_TRANSFORMER_SUBDIR
    if not transformer_dir.exists() or not transformer_dir.is_dir():
        return False

    COMFYUI_UNET.mkdir(parents=True, exist_ok=True)
    # Find the main weight file (e.g. diffusion_pytorch_model.safetensors)
    safetensors = [f for f in transformer_dir.iterdir() if f.is_file() and f.suffix == ".safetensors"]
    if not safetensors:
        return False

    src_file = safetensors[0]
    tgt = COMFYUI_UNET / Z_IMAGE_TURBO_UNET_FILENAME
    if tgt.is_symlink():
        tgt.unlink()
    if tgt.exists():
        tgt.unlink()
    tgt.symlink_to(src_file)
    print(f"  [cached-model] Symlinked cached transformer -> models/unet/{Z_IMAGE_TURBO_UNET_FILENAME} (cache takes precedence over baked-in)")
    return True


def main() -> None:
    model_id = os.environ.get("MODEL_NAME") or os.environ.get("CACHED_MODEL_ID") or DEFAULT_CACHED_MODEL_ID

    print("=" * 60)
    print("RunPod cached model setup (Z-Image-Turbo -> unet)")
    print("=" * 60)
    print(f"  Cache root: {CACHE_ROOT}")
    print(f"  Model ID:   {model_id}")

    if not CACHE_ROOT.exists():
        print("  [cached-model] Cache directory not present; using baked-in model from image (Dockerfile).")
        print("  Configure Model in your RunPod endpoint settings to use model caching.")
        print("=" * 60)
        return

    snapshot_path = resolve_snapshot_path(model_id)
    if not snapshot_path:
        print(f"  [cached-model] Cached model not found: {model_id}; using baked-in model from image (Dockerfile).")
        if CACHE_ROOT.exists():
            entries = [e.name for e in CACHE_ROOT.iterdir() if e.is_dir()][:5]
            if entries:
                print(f"  [cached-model] Cache contents (sample): {entries}")
        print("=" * 60)
        return

    print(f"  [cached-model] Using cached model: {model_id}")
    print(f"  [cached-model] Snapshot path: {snapshot_path}")

    if setup_z_image_turbo_from_cache(model_id):
        print("  [cached-model] Cached model symlinked to models/unet/ — ComfyUI will use the cached model.")
    else:
        print("  [cached-model] No transformer files found in cache snapshot; skipping unet symlinks.")

    print("=" * 60)


if __name__ == "__main__":
    main()
    sys.exit(0)
