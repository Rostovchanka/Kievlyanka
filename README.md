# Elsewhere Studio — Audited Build (0.6.2)

A photographic editor specialized for photographs you took yourself, with 16-bit RAW/PNG/TIFF processing, JPEG input/output, geometry, Backrooms presets, advanced color and liminal-atmosphere adjustments. It does **not** generate scenes or bundle textures, brushes, or painting gradients.

## Install on Windows without installing Python

The GitHub Actions workflow builds a portable Windows application whose Python runtime and libraries are bundled.

1. Unzip this archive. The `.github` folder must be placed at the repository root, alongside `elsewhere_studio.py`, `engine.py`, `io_formats.py`, `recipe.py`, and `requirements.txt`.
2. Upload/replace the files in the GitHub repository **without adding an extra parent folder**. Commit changes.
3. In GitHub: **Actions → Build Standalone Elsewhere for Windows → Run workflow**.
4. Open the successful run's **Artifacts** section and download `Elsewhere-Studio-Windows-Portable`.
5. Extract it, then run `Elsewhere Studio.exe`. Keep the accompanying `_internal` / runtime files in the same extracted app folder.

You do not need to install Python to **run** the built Windows app. If you want to compile it locally instead, install Python 3.11 and run `BUILD_WINDOWS.cmd`.

## EOS R5 / CR3

The original `camera_make` crash has been removed. `rawpy` exposes optional `raw.other` and `raw.lens` metadata; missing fields no longer block opening a sensor image. EOS R5 CR3 decoding still depends on the installed LibRaw version. An actual EOS R5 CR3 was not available for this audit.

## Audit fixes

- Prevent background opening of older photos from overwriting a newer photo's preview.
- Invalidate out-of-date preview rendering and clear stale canvas content on new open.
- Prevent closing a window while QThreads are active.
- Reject export destinations equal to the source photograph, preserving originals.
- Restore keyboard-slider undo and fix redo-history invalidation.
- Validate loaded recipe values, rejecting NaN/infinite/out-of-range settings.
- Preserve transparent PNG/TIFF appearance by compositing on white rather than discarding alpha. Handle associated TIFF alpha and planar TIFF samples.
- Allow Unicode PNG filenames on Windows via OpenCV in-memory decoding/encoding.
- Correct tone curves to work on luminance rather than channel-by-channel.
- Bound chromatic edge offsets for tiny images; clamp HSV parameters into a valid range.
- Render noise reduction in the preview rather than skipping it.
- Report ICC profile assumptions/alpha compositing in image metadata.
- Add regression tests and strengthen the Windows workflow syntax check.

## Verification / important limitations

- **35 local tests passed** (engine, IO, regression, simulated RAW metadata). One Windows/Qt UI test module was skipped locally because PySide6 is not installed in this environment; the GitHub Windows workflow runs it.
- Python source compiled without syntax errors; 120 additional randomized engine cases were run during auditing.
- The complete Windows .exe, native Qt GUI, and real EOS R5 CR3 images were **not** tested in this environment.
- 16-bit processing is float32 internally and 16-bit on TIFF/PNG output, but camera-specific profiles/advanced soft proofing are not equivalent to Lightroom.
- PNG/TIFF files with non-sRGB ICC profiles are currently treated as sRGB and are warned about; accurate profile conversion is unfinished.
- Large, full-resolution RAW processing is CPU-bound and can require several gigabytes of RAM. Peak memory use on full-size R5 files was not measured.
- TIFF alpha is composited to white; alpha is not preserved on export. Multi-page TIFF workflows are not supported.
- RAW white-balance options do not participate in the grade undo/redo history.

See `AUDIT_REPORT.md` for the test scope. No audit can establish the absence of every possible bug.
