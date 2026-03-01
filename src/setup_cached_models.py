#!/usr/bin/env python3
"""
Setup script to symlink RunPod's cached Hugging Face model (zimageturbo-minimal)
into ComfyUI model folders (unet, loras, clip, vae).

RunPod downloads the model to /runpod-volume/huggingface-cache/hub/ when you
set the endpoint's Model field to the Hugging Face repo. This script symlinks
each .safetensors file from the cache snapshot into the correct ComfyUI folder.

File mapping (viggemimog/zimageturbo-minimal):
  - zimage_turbo.safetensors     -> models/unet/
  - realistic_snapshot.safetensors -> models/loras/
  - qwen_3_4b.safetensors        -> models/clip/
  - mystic_xxx.safetensors       -> models/loras/
  - ae.safetensors              -> models/vae/

References:
  - https://docs.runpod.io/serverless/endpoints/model-caching
  - https://docs.runpod.io/tutorials/serverless/model-caching-text
"""
import os
import sys
from pathlib import Path

CACHE_ROOT = Path("/runpod-volume/huggingface-cache/hub")
COMFYUI_BASE = Path("/runpod-volume/models")

# Default model when RunPod Model field is set to this repo
DEFAULT_CACHED_MODEL_ID = "viggemimog/zimageturbo-minimal"

# Cached repo files are at snapshot root. Map filename -> ComfyUI subfolder (under models/).
# ComfyUI paths from extra_model_paths.yaml: unet, loras, clip, vae.
FILE_TO_COMFYUI_FOLDER = [
    ("zimage_turbo.safetensors", "unet"),
    ("realistic_snapshot.safetensors", "loras"),
    ("qwen_3_4b.safetensors", "clip"),
    ("mystic_xxx.safetensors", "loras"),
    ("ae.safetensors", "vae"),
]


def resolve_snapshot_path(model_id: str) -> Path | None:
    """
    Resolve the cached model snapshot directory for a Hugging Face model ID.

    RunPod stores cached models under CACHE_ROOT with structure:
      models--{org}--{name}/refs/main, snapshots/{hash}/...
    See: https://docs.runpod.io/serverless/endpoints/model-caching
    """
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


def setup_zimageturbo_minimal_from_cache(model_id: str) -> int:
    """
    Symlink each cached file from the snapshot into the correct ComfyUI folder.
    Returns the number of symlinks created.
    """
    snapshot_path = resolve_snapshot_path(model_id)
    if not snapshot_path or not snapshot_path.is_dir():
        return 0

    linked = 0
    for filename, subdir in FILE_TO_COMFYUI_FOLDER:
        src = snapshot_path / filename
        if not src.is_file():
            continue
        dest_dir = COMFYUI_BASE / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)
        tgt = dest_dir / filename
        if tgt.is_symlink():
            tgt.unlink()
        if tgt.exists():
            tgt.unlink()
        tgt.symlink_to(src)
        print(f"  [cached-model] Symlinked {filename} -> models/{subdir}/")
        linked += 1

    return linked


def main() -> None:
    model_id = os.environ.get("MODEL_NAME") or os.environ.get("CACHED_MODEL_ID") or DEFAULT_CACHED_MODEL_ID

    print("=" * 60)
    print("RunPod cached model setup (zimageturbo-minimal -> ComfyUI folders)")
    print("=" * 60)
    print(f"  Cache root: {CACHE_ROOT}")
    print(f"  Model ID:   {model_id}")

    if not CACHE_ROOT.exists():
        print("  [cached-model] Cache directory not present; using baked-in models from image (Dockerfile).")
        print("  Set Model in your RunPod endpoint to 'viggemimog/zimageturbo-minimal' to use model caching.")
        print("=" * 60)
        return

    snapshot_path = resolve_snapshot_path(model_id)
    if not snapshot_path:
        print(f"  [cached-model] Cached model not found: {model_id}; using baked-in models from image (Dockerfile).")
        if CACHE_ROOT.exists():
            entries = [e.name for e in CACHE_ROOT.iterdir() if e.is_dir()][:5]
            if entries:
                print(f"  [cached-model] Cache contents (sample): {entries}")
        print("=" * 60)
        return

    print(f"  [cached-model] Using cached model: {model_id}")
    print(f"  [cached-model] Snapshot path: {snapshot_path}")

    linked = setup_zimageturbo_minimal_from_cache(model_id)
    if linked:
        print(f"  [cached-model] Symlinked {linked} file(s) into ComfyUI model folders.")
    else:
        print("  [cached-model] No expected files found in cache snapshot; skipping symlinks.")

    print("=" * 60)


if __name__ == "__main__":
    main()
    sys.exit(0)
