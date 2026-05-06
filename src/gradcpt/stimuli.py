"""Single-image preprocessing for GradCPT stimuli.

Loading is grayscale-only (we use Pillow). Preprocessing applies an optional
circular mask, optional vertical flip (preserving the original gradcptpy
quirk by default), and optional normalization to [-1, 1].
"""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import numpy as np
from PIL import Image

from .config import StimuliConfig


MID_GRAY_8BIT: float = 127.5  # neutral fill for masked-out pixels in [0, 255] space


def bundled_stimuli_root() -> Path:
    """Return the absolute path to the bundled `stimuli_assets/` directory."""
    return Path(str(files("gradcpt") / "stimuli_assets"))


def category_folder(cfg: StimuliConfig, category: str) -> Path:
    """Resolve the folder containing images for ``category``.

    If ``cfg.folder`` is set, expects a ``{folder}/{category}/`` layout.
    Otherwise uses the bundled stimuli.
    """
    root = cfg.folder if cfg.folder is not None else bundled_stimuli_root()
    return Path(root) / category


def list_images(folder: Path) -> list[Path]:
    """Return sorted JPEG paths in ``folder`` (top-level only)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"stimulus folder not found: {folder}")
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"})


def load_grayscale(path: Path) -> np.ndarray:
    """Load an image as a uint8 grayscale 2D ndarray (H, W)."""
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.uint8)


def normalize_minus1_plus1(img: np.ndarray) -> np.ndarray:
    """Map uint8 [0, 255] → float32 [-1, +1]."""
    return (img.astype(np.float32) / 255.0) * 2.0 - 1.0


def apply_circular_mask(img: np.ndarray, fill: float | None = None) -> np.ndarray:
    """Set pixels outside a centered circle (radius = min(H, W) / 2) to ``fill``.

    If ``fill`` is None, fill is mid-gray for the image dtype:
      - floats → 0.0 (exact mid-gray in [-1, 1])
      - uint8 → 127 (mid-gray in [0, 255], one bit off from the true 127.5)
    """
    if img.ndim != 2:
        raise ValueError(f"expected 2D image, got shape {img.shape}")
    h, w = img.shape
    y, x = np.ogrid[:h, :w]
    cy, cx = h / 2, w / 2
    radius = min(cx, cy)
    inside = ((y - cy) ** 2 + (x - cx) ** 2) <= radius**2
    out = img.copy()
    if fill is None:
        if np.issubdtype(out.dtype, np.floating):
            fill = 0.0
        else:
            fill = int(MID_GRAY_8BIT)  # truncates 127.5 → 127
    out[~inside] = fill
    return out


def preprocess_image(img: np.ndarray, cfg: StimuliConfig) -> np.ndarray:
    """Apply all enabled preprocessing steps in the canonical order.

    Order is chosen so that the mask fill lands on exact mid-gray in the
    final dtype:

    * flip_vertical first (orientation only)
    * normalize next (so the float space exists for the mask if enabled)
    * mask last (fill = 0.0 in float space; exact mid-gray)

    When normalization is disabled, the mask is applied to uint8 with fill 127.
    """
    out = img
    if cfg.flip_vertical:
        out = np.flipud(out)
    if cfg.normalize_to_minus1_plus1:
        out = normalize_minus1_plus1(out)
        if cfg.apply_circular_mask:
            out = apply_circular_mask(out, fill=0.0)
    else:
        if cfg.apply_circular_mask:
            out = apply_circular_mask(out)
        out = out.astype(np.float32)
    return np.ascontiguousarray(out)


def load_category(
    cfg: StimuliConfig, category: str
) -> tuple[list[str], list[np.ndarray]]:
    """Load every image in a category folder, preprocessed.

    Returns (image_ids, preprocessed_arrays) where image_ids are filename
    stems suitable for use as identifiers in the sequencing module.
    """
    folder = category_folder(cfg, category)
    paths = list_images(folder)
    if not paths:
        raise FileNotFoundError(f"no JPEG stimuli found in {folder}")
    ids: list[str] = []
    arrays: list[np.ndarray] = []
    for p in paths:
        raw = load_grayscale(p)
        if raw.shape != (cfg.image_size_px, cfg.image_size_px):
            raise ValueError(
                f"{p}: shape {raw.shape} != expected ({cfg.image_size_px},"
                f" {cfg.image_size_px}) — set stimuli.image_size_px to match"
            )
        ids.append(p.stem)
        arrays.append(preprocess_image(raw, cfg))
    return ids, arrays
