#!/usr/bin/env python3
"""
Setup script to create symlinks from ComfyUI model directories
to RunPod's Hugging Face cached models.

This enables using RunPod's model caching feature for faster cold starts
and reduced costs when loading large models.

Reference: https://docs.runpod.io/serverless/endpoints/model-caching
"""
import os
from pathlib import Path

# RunPod cached models location (HuggingFace cache layout)
CACHE_ROOT = Path("/runpod-volume/huggingface-cache/hub")

# ComfyUI model directories (matching extra_model_paths.yaml)
COMFYUI_MODELS_BASE = Path("/runpod-volume/models")

# Model type mapping: HF repo subfolder -> ComfyUI model directory
# These match the structure in extra_model_paths.yaml
MODEL_TYPE_MAPPING = {
    "checkpoints": "checkpoints",
    "loras": "loras",
    "clip": "clip",
    "clip_vision": "clip_vision",
    "vae": "vae",
    "unet": "unet",
    "controlnet": "controlnet",
    "embeddings": "embeddings",
    "upscale_models": "upscale_models",
    "diffusion_models": "diffusion_models",
    "text_encoders": "text_encoders",
    "mmaudio": "mmaudio",
    "configs": "configs",
}


def resolve_snapshot_path(model_id: str) -> Path | None:
    """
    Resolve the path to a cached model's snapshot directory.
    
    Args:
        model_id: HuggingFace model ID (e.g., 'org/model-name')
    
    Returns:
        Path to the snapshot directory, or None if not found
    """
    if "/" not in model_id:
        print(f"  Invalid model ID format: {model_id} (expected 'org/name')")
        return None
    
    org, name = model_id.split("/", 1)
    model_dir = CACHE_ROOT / f"models--{org}--{name}"
    
    if not model_dir.exists():
        return None
    
    # Prefer refs/main when present (indicates the default branch)
    ref_main = model_dir / "refs" / "main"
    if ref_main.exists():
        rev = ref_main.read_text().strip()
        snap = model_dir / "snapshots" / rev
        if snap.exists():
            return snap
    
    # Fallback: first snapshot directory
    snap_root = model_dir / "snapshots"
    if snap_root.exists():
        snaps = sorted(snap_root.glob("*"))
        if snaps:
            return snaps[0]
    
    return None


def setup_model_symlinks(model_id: str) -> bool:
    """
    Create symlinks from ComfyUI model directories to cached model files.
    
    Args:
        model_id: HuggingFace model ID (e.g., 'your-org/your-models')
    
    Returns:
        True if any symlinks were created, False otherwise
    """
    print(f"\nSetting up cached models for: {model_id}")
    
    snapshot_path = resolve_snapshot_path(model_id)
    if not snapshot_path:
        print(f"  WARNING: Model {model_id} not found in cache at {CACHE_ROOT}")
        print(f"  Make sure you've configured the model in your RunPod endpoint settings")
        # List what's actually in the cache for debugging
        if CACHE_ROOT.exists():
            entries = list(CACHE_ROOT.iterdir())[:10]
            if entries:
                print(f"  Cache contains: {[e.name for e in entries]}")
        return False
    
    print(f"  Found snapshot at: {snapshot_path}")
    
    # Ensure base model directory exists
    COMFYUI_MODELS_BASE.mkdir(parents=True, exist_ok=True)
    
    links_created = 0
    
    # Scan the snapshot for model subdirectories and create symlinks
    for hf_subdir, comfy_subdir in MODEL_TYPE_MAPPING.items():
        source_dir = snapshot_path / hf_subdir
        target_dir = COMFYUI_MODELS_BASE / comfy_subdir
        
        if not source_dir.exists():
            continue
        
        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"  Processing {hf_subdir}/...")
        
        # Create symlinks for each file in the source directory
        for source_file in source_dir.iterdir():
            if source_file.is_file():
                target_link = target_dir / source_file.name
                
                # Remove existing symlink if present
                if target_link.is_symlink():
                    target_link.unlink()
                    print(f"    Updated: {source_file.name}")
                elif target_link.exists():
                    # Don't overwrite real files
                    print(f"    SKIP: {source_file.name} (real file exists)")
                    continue
                else:
                    print(f"    Linked: {source_file.name}")
                
                target_link.symlink_to(source_file)
                links_created += 1
    
    print(f"  Created {links_created} symlink(s)")
    return links_created > 0


def list_cached_models() -> list[str]:
    """
    List all models available in the RunPod cache.
    
    Returns:
        List of model IDs in 'org/name' format
    """
    if not CACHE_ROOT.exists():
        return []
    
    models = []
    for item in CACHE_ROOT.iterdir():
        if item.is_dir() and item.name.startswith("models--"):
            # Convert models--org--name back to org/name
            parts = item.name.replace("models--", "").split("--", 1)
            if len(parts) == 2:
                models.append(f"{parts[0]}/{parts[1]}")
    
    return sorted(models)


def main():
    """Main entry point for the setup script."""
    import sys
    
    print("=" * 60)
    print("RunPod Cached Models Setup for ComfyUI")
    print("=" * 60)
    print(f"Cache root: {CACHE_ROOT}")
    print(f"ComfyUI models: {COMFYUI_MODELS_BASE}")
    
    # Check if cache directory exists
    if not CACHE_ROOT.exists():
        print(f"\nCache directory does not exist: {CACHE_ROOT}")
        print("This is normal if no cached model is configured for the endpoint.")
        print("Configure a model in RunPod endpoint settings to use caching.")
        return
    
    # List available cached models
    cached_models = list_cached_models()
    if cached_models:
        print(f"\nFound {len(cached_models)} cached model(s):")
        for m in cached_models:
            print(f"  - {m}")
    else:
        print("\nNo cached models found in cache directory.")
        print("Configure a model in your RunPod endpoint settings.")
        return
    
    # Get model ID from environment variable or command line
    model_id = os.environ.get("CACHED_MODEL_ID")
    if len(sys.argv) > 1:
        model_id = sys.argv[1]
    
    # Setup specific model if provided, otherwise auto-setup all cached models
    if model_id:
        print(f"\nSetting up specified model: {model_id}")
        setup_model_symlinks(model_id)
    else:
        print("\nAuto-setting up all cached models...")
        for m in cached_models:
            setup_model_symlinks(m)
    
    print("\n" + "=" * 60)
    print("Setup complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
