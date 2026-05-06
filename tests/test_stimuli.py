from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from gradcpt.config import StimuliConfig
from gradcpt.stimuli import (
    apply_circular_mask,
    bundled_stimuli_root,
    list_images,
    load_category,
    load_grayscale,
    normalize_minus1_plus1,
    preprocess_image,
)


def test_bundled_stimuli_root_exists():
    root = bundled_stimuli_root()
    assert root.is_dir()
    assert (root / "city").is_dir()
    assert (root / "mountain").is_dir()


def test_list_images_returns_sorted_jpegs():
    root = bundled_stimuli_root()
    paths = list_images(root / "city")
    assert len(paths) == 10
    assert all(p.suffix == ".jpg" for p in paths)
    assert paths == sorted(paths)


def test_list_images_missing_folder_raises():
    with pytest.raises(FileNotFoundError):
        list_images(Path("/nonexistent/folder/xyz"))


def test_load_grayscale_shape_and_dtype():
    p = list_images(bundled_stimuli_root() / "city")[0]
    arr = load_grayscale(p)
    assert arr.shape == (256, 256)
    assert arr.dtype == np.uint8


def test_normalize_minus1_plus1_maps_endpoints():
    img = np.array([[0, 127, 255]], dtype=np.uint8)
    out = normalize_minus1_plus1(img)
    assert out.dtype == np.float32
    np.testing.assert_allclose(out, [[-1.0, (127 / 255) * 2 - 1, 1.0]], rtol=1e-6)


def test_apply_circular_mask_zeros_outside_circle_uint8():
    img = np.full((10, 10), 200, dtype=np.uint8)
    masked = apply_circular_mask(img)
    # Corner is outside circle (radius=5, center=(5,5))
    assert masked[0, 0] == 127
    # Center is inside
    assert masked[5, 5] == 200


def test_apply_circular_mask_zero_fill_for_floats():
    img = np.full((8, 8), 0.7, dtype=np.float32)
    masked = apply_circular_mask(img)
    assert masked[0, 0] == 0.0
    assert masked[4, 4] == 0.7


def test_preprocess_image_full_pipeline():
    img = np.full((256, 256), 200, dtype=np.uint8)
    cfg = StimuliConfig()
    out = preprocess_image(img, cfg)
    assert out.dtype == np.float32
    assert out.shape == (256, 256)
    # Inside the circle, value should be (200/255)*2 - 1 ≈ 0.5686
    np.testing.assert_allclose(out[128, 128], (200 / 255) * 2 - 1, rtol=1e-5)
    # Corners are masked → 0.0
    assert out[0, 0] == 0.0


def test_preprocess_image_can_disable_steps():
    img = np.zeros((256, 256), dtype=np.uint8)
    img[0, 0] = 255  # marker for vertical-flip detection
    cfg = StimuliConfig(
        flip_vertical=False, apply_circular_mask=False, normalize_to_minus1_plus1=False
    )
    out = preprocess_image(img, cfg)
    assert out[0, 0] == 255.0  # no flip, no mask, no normalize
    assert out.dtype == np.float32


def test_preprocess_image_flips_vertically():
    img = np.zeros((4, 4), dtype=np.uint8)
    img[0, 0] = 255
    cfg = StimuliConfig(
        flip_vertical=True, apply_circular_mask=False, normalize_to_minus1_plus1=False
    )
    out = preprocess_image(img, cfg)
    # Flipping (0,0) lands at (3,0)
    assert out[3, 0] == 255.0
    assert out[0, 0] == 0.0


def test_load_category_returns_ids_and_arrays():
    cfg = StimuliConfig()
    ids, arrays = load_category(cfg, "city")
    assert len(ids) == 10 == len(arrays)
    assert all(isinstance(i, str) for i in ids)
    assert all(a.shape == (256, 256) for a in arrays)
    assert all(a.dtype == np.float32 for a in arrays)


def test_load_category_missing_raises(tmp_path):
    cfg = StimuliConfig(folder=tmp_path)  # empty folder
    with pytest.raises(FileNotFoundError):
        load_category(cfg, "city")
