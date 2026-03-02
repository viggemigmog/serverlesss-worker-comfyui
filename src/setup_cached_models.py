#!/usr/bin/env python3
"""
Setup script for RunPod's cached Hugging Face model (e.g. zimageturbo-minimal).

RunPod downloads the model to /runpod-volume/huggingface-cache/hub/ when you
set the endpoint's Model field to the Hugging Face repo. This script:

1. **Stage to local disk** (default): Copy cached files into /comfyui/models/
   so ComfyUI reads from local disk for faster inference (avoids slow I/O on
   cache volume). Uses a sentinel to skip re-copy when the same snapshot is
   already staged.

2. **Symlink only** (COMFYUI_CACHE_SYMLINK_ONLY=true): Symlink into
   /comfyui/models/ pointing at the cache path (no copy; for debugging).

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
import shutil
import sys
import time
from pathlib import Path

CACHE_ROOT = Path("/runpod-volume/huggingface-cache/hub")
COMFYUI_MODELS_BASE = Path("/comfyui/models")
SENTINEL_FILE = COMFYUI_MODELS_BASE / ".cached_models_staged"

# Default model when RunPod Model field is set to this repo
DEFAULT_CACHED_MODEL_ID = "viggemimog/zimageturbo-minimal"

# Cached repo files are at snapshot root. Map filename -> ComfyUI subfolder (under models/).
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


def stage_to_local(snapshot_path: Path) -> int:
    """
    Copy cached model files from snapshot to local disk (/comfyui/models).
    Uses a sentinel file to avoid re-copying when the same snapshot is already staged.
    Returns the number of files copied (0 if skipped via sentinel).
    """
    snapshot_str = str(snapshot_path)
    if SENTINEL_FILE.exists():
        try:
            if SENTINEL_FILE.read_text().strip() == snapshot_str:
                print("  [cached-model] Sentinel present; skipping copy (already staged).")
                return 0
        except OSError:
            pass

    copied = 0
    for filename, subdir in FILE_TO_COMFYUI_FOLDER:
        src = snapshot_path / filename
        if not src.is_file():
            continue
        dest_dir = COMFYUI_MODELS_BASE / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)
        tgt = dest_dir / filename
        shutil.copy2(src, tgt)
        print(f"  [cached-model] Copied {filename} -> models/{subdir}/ (local disk)")
        copied += 1

    if copied > 0:
        COMFYUI_MODELS_BASE.mkdir(parents=True, exist_ok=True)
        try:
            SENTINEL_FILE.write_text(snapshot_str)
        except OSError as e:
            print(f"  [cached-model] WARNING: could not write sentinel: {e}")

    return copied


def setup_symlinks_to_cache(snapshot_path: Path) -> int:
    """
    Symlink each cached file from the snapshot into ComfyUI's model dirs.
    Returns the number of symlinks created.
    """
    linked = 0
    for filename, subdir in FILE_TO_COMFYUI_FOLDER:
        src = snapshot_path / filename
        if not src.is_file():
            continue
        dest_dir = COMFYUI_MODELS_BASE / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)
        tgt = dest_dir / filename
        if tgt.is_symlink():
            tgt.unlink()
        if tgt.exists():
            tgt.unlink()
        tgt.symlink_to(src)
        print(f"  [cached-model] Symlinked {filename} -> models/{subdir}/ (reads from cache)")
        linked += 1
    return linked


def main() -> None:
    script_start = time.perf_counter()
    symlink_only = os.environ.get("COMFYUI_CACHE_SYMLINK_ONLY", "").lower() == "true"
    model_id = (
        os.environ.get("MODEL_NAME")
        or os.environ.get("CACHED_MODEL_ID")
        or DEFAULT_CACHED_MODEL_ID
    )

    print("=" * 60)
    print("RunPod cached model setup (ComfyUI)")
    print("=" * 60)
    print(f"  Cache root:    {CACHE_ROOT}")
    print(f"  Model ID:     {model_id}")
    print(f"  ComfyUI:      {COMFYUI_MODELS_BASE}")
    print(f"  Symlink only: {symlink_only} (set COMFYUI_CACHE_SYMLINK_ONLY=true to skip copy)")

    if not CACHE_ROOT.exists():
        print("  [cached-model] Cache directory not present; using baked-in models from image (Dockerfile).")
        print("  Set Model in your RunPod endpoint to use model caching.")
        print("=" * 60)
        return

    t0 = time.perf_counter()
    snapshot_path = resolve_snapshot_path(model_id)
    resolve_elapsed = time.perf_counter() - t0
    print(f"  [cached-model] Resolved snapshot in {resolve_elapsed:.2f}s")

    if not snapshot_path:
        print(f"  [cached-model] ERROR: Cached model not found: {model_id}")
        if CACHE_ROOT.exists():
            entries = [e.name for e in CACHE_ROOT.iterdir() if e.is_dir()][:5]
            if entries:
                print(f"  [cached-model] Cache contents (sample): {entries}")
        print("  Ensure the endpoint Model field matches the intended Hugging Face repo.")
        print("=" * 60)
        sys.exit(1)

    print(f"  [cached-model] Snapshot path: {snapshot_path}")

    step_start = time.perf_counter()
    if symlink_only:
        count = setup_symlinks_to_cache(snapshot_path)
        if count:
            print(f"  [cached-model] Symlinked {count} file(s); ComfyUI will load from cache path.")
        else:
            print("  [cached-model] No expected files found in cache snapshot.")
    else:
        count = stage_to_local(snapshot_path)
        if count:
            print(f"  [cached-model] Staged {count} file(s) to local disk; ComfyUI will load from /comfyui/models.")
        elif not SENTINEL_FILE.exists():
            print("  [cached-model] No expected files found in cache snapshot.")

    step_elapsed = time.perf_counter() - step_start
    total_elapsed = time.perf_counter() - script_start
    print(f"  [cached-model] Setup took {step_elapsed:.2f}s; total {total_elapsed:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
    sys.exit(0)
