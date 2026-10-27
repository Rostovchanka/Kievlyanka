# Elsewhere Studio — Code Audit, October 2026

## Scope

Reviewed the exact preceding EOS R5 fixed project: `elsewhere_studio.py`, `engine.py`, `io_formats.py`, existing tests, requirements, Windows batch builder, and GitHub Actions workflow. Added `recipe.py` for validating user recipes.

## Fixed defects / hazards

1. **RAW crash previously reported:** no undocumented `raw.camera_make` / `raw.camera_model` references remain in runtime decoding; the metadata path degrades to optional fields.
2. **Overlapping image-open requests:** render/load tokens now reject older results; an old photo cannot replace the new photo's preview.
3. **Unsafe shutdown:** the UI defers closing while export/open/preview worker threads are running, preventing QThread teardown during work.
4. **Source-file overwrite:** UI and IO worker prevent exporting an edited photograph over the original input path.
5. **Undo correctness:** keyboard/scroll slider changes enter undo history; a new action invalidates the redo branch.
6. **Malformed recipe handling:** type, finite-number, adjustment bounds, geometry bounds and RAW choices validated before the UI is changed.
7. **Tone curve behavior:** nominal luminance curves now remap luminance instead of independently editing RGB channels.
8. **Extreme controls:** HSV output bounded to valid channel ranges; tiny images no longer fail due to chromatic offset slicing.
9. **Transparency:** transparent 8/16-bit PNG and TIFF composites onto white, including TIFF associated/unassociated alpha.
10. **TIFF channel layout:** handles planar-separated color channels via TIFF metadata rather than width-dependent heuristics.
11. **Unicode filenames:** PNG IO uses Unicode-safe OpenCV memory coding and atomic replacement after injecting sRGB metadata.
12. **Preview fidelity:** noise reduction is no longer intentionally hidden from the fast preview.
13. **Small UI correctness:** clears stale canvas/histogram on new file and updates alpha/ICC notes.

## Results in audit environment

- 35 passing non-GUI tests; 1 GUI test module skipped due to missing PySide6.
- 120 additional randomized image/settings/geometry executions completed without an exception.
- Python syntax compiled for all project modules.
- Format tests cover 8-bit JPEG, true 16-bit PNG/TIFF round-trips, PNG sRGB chunk, TIFF ICC tag, RGBA alpha, TIFF planar storage, camera JPEG EXIF rotation, and Unicode filenames.
- Fake RAW objects cover optional metadata present/missing/invalid; **no physical EOS R5 CR3 test was possible**.

## Remaining risks / unverified items

- The Qt application and Windows executable were not run in this audit runtime; tests for those are included in the GitHub Windows build workflow.
- Large EOS R5 CR3 images could exceed available RAM or render slowly; no GPU engine or tiled export is implemented.
- RAW results still depend on LibRaw's Canon support and the individual file/camera firmware.
- PNG/TIFF source ICC conversion is incomplete; only an sRGB working-space assumption with a warning is provided.
- Sophisticated Lightroom-quality color profiling, lens calibration, AI denoising and photographic parity have not been established.
- Native/Qt application behavior, OS-specific file permissions, and hardware-dependent defects cannot be ruled out by local synthetic tests.

## Build result

This archive contains **source code and the GitHub Windows builder**, not a precompiled `.exe`. The Windows workflow runs all tests and a packaged executable smoke check before uploading an artifact. A successful workflow run validates only those checks, not every camera or edit.
