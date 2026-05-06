# Bundled stimuli

Grayscale 256×256 JPEG photographs.

- `city/` — 10 city scene images (the "go" / dominant category).
- `mountain/` — 10 mountain scene images (the "no-go" / non-dominant category).
- `scrambled/` — 60 phase-scrambled scenes; off by default. Enable via
  `cfg.stimuli.scrambled_enabled = true` (see `docs/configuration.md`).

Source: copied verbatim from `gradcptpy/scenes5/` (David Braun, MIT License,
2024). Images are pre-cropped to 256×256 squares; circular masking is applied
at runtime by `gradcpt.stimuli`.
