# Building for Windows

The build produces a portable folder with a windowed desktop launcher and a console
launcher. Keep the whole output folder together. Model weights are downloaded
separately. The recipe is pinned and repeatable, but identical binary hashes across
rebuilds are not promised.

## Prerequisites

Use Windows x64, CPython 3.11.9, and the source environment created by
`Setup-Windows.ps1 -Dev`. Runtime dependencies must match `requirements-lock.txt`;
the build adds only the versions in `requirements-build.txt`. Other Python patch
versions need their own validated recipe. A full build needs at least 3 GiB of free
disk space and a fair amount of memory, so close heavy applications first.

To check prerequisites without building anything:

~~~powershell
.\Build-Windows.ps1 -CheckOnly -BuildName "LunaCaption-preflight-check"
~~~

This reads the Windows/Python architecture and version, the locked package versions,
the project version, whether the output name is free, and the 3 GiB disk minimum.
It does not create folders, install tools, load the model, or start PyInstaller.
`-CheckOnly` cannot be combined with `-InstallBuildTools`. A passing check does not
measure RAM or reserve disk space.

## Build

From the project folder:

~~~powershell
.\Build-Windows.ps1 -InstallBuildTools
~~~

Later builds can omit `-InstallBuildTools`. The script checks every locked version,
then runs PyInstaller 6.22.3 with hooks 2026.9 and writes a local build log. It never
deletes earlier output, so choose a new name for each build:

~~~powershell
.\Build-Windows.ps1 -BuildName "LunaCaption-0.1.0-win64-second"
~~~

The default output is `dist/LunaCaption-0.1.0-win64/LunaCaption/`:

- `LunaCaption.exe`: the desktop app, without a console window.
- `LunaCaption-CLI.exe`: captions, model setup, and diagnostics in a terminal.
- `_internal/`: Python, Tk, dependencies, and supporting files. Keep this directory.
- `README-Windows.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `licenses/`.
- `build-info.json`: package versions, build time, source hashes, and bundled-file hashes.

Both executables use `packaging/LunaCaption.ico`. `build/` and `dist/` are ignored by
Git; don't commit generated executables or logs. The build does not create an
installer, sign the executables, or publish a release.

If a file can't be hashed while writing `build-info.json`, the build stops, names
the file and the OS error, and does not write a manifest. Keep that output for
investigation rather than distributing it.

## Model cache

Packaged executables default to `%LOCALAPPDATA%\LunaCaption\models` (a model
downloaded under the earlier `LumaCaption` folder name is reused). Both launchers
honor `LUNACAPTION_CACHE`. To reuse the development cache:

~~~powershell
$env:LUNACAPTION_CACHE = (Resolve-Path ".cache\models").Path
& ".\dist\LunaCaption-0.1.0-win64\LunaCaption\LunaCaption-CLI.exe" --diagnose
~~~

On another machine, run `LunaCaption-CLI.exe --download-model` while online, then use
`--offline` or the desktop Offline checkbox. No weights or photos are included in the build.

## Verifying a build

1. Run `--help` and `--diagnose` with `LunaCaption-CLI.exe`.
2. Run the bundled offline smoke test with your own local photos and a fresh report path:

~~~powershell
$env:LUNACAPTION_CACHE = (Resolve-Path ".cache\models").Path
$exe = ".\dist\LunaCaption-0.1.0-win64\LunaCaption\LunaCaption-CLI.exe"
& $exe --verify-package "D:\local\photo.jpg" --desktop --report ".local\packaged-smoke.json"
~~~

3. Repeat `--verify-package` with `LunaCaption.exe` and a different report path to
   check the windowed launcher. From PowerShell, use `Start-Process -Wait -PassThru`
   so the exit code is checked.
4. Compare captions and image hashes with a source run. The smoke test blocks network
   access, runs the real Tk caption worker and CSV/JSON exports, and disables
   recovery so it doesn't touch user data.

A successful build or a running process alone is not proof the package works; test
actual model loading and caption generation before calling a build usable.

## Latest verified build (2026-11-24)

Built on Windows 10 Home x64 (Intel Core i5-7200U, 8 GB RAM) from the LunaCaption
source with the pinned recipe: about 6 minutes, 621.6 MiB output, `build-info.json`
written. The build ran at below-normal priority with a free-memory watchdog; free RAM
never fell below 2.16 GiB.

| Check | Result |
| --- | --- |
| `LunaCaption-CLI.exe --help` / `--diagnose` | Exit 0 / exit 0, all checks OK |
| CLI `--verify-package --desktop`, 2 photos in a folder with spaces | Pass: offline, 0 network attempts, desktop worker and CSV/JSON exports verified, inputs unchanged |
| `LunaCaption.exe` (windowed) `--verify-package`, second offline launch | Pass, same checks and identical captions |
| Captions vs. the source app | Identical |
| Empty model cache with `--offline` | Exit 2 with a clear "connect once to download" message; `--diagnose` exits 1 and names the fix |
| Executable icon | LunaCaption crescent embedded |

Not yet verified: a clean Windows machine without the development tools, a fresh
model download through the packaged CLI, and real NVIDIA GPU execution.

## Build choices and limits

The [PyInstaller spec](https://pyinstaller.org/en/stable/spec-files.html) shares one
analysis between the two launchers. Transformers source files and explicit BLIP/BERT
imports support its lazy import maps; package metadata is kept for dependency checks.
The finalization step removes pip `direct_url.json` files inside the bundle so local
source paths aren't shipped. The entry point calls `freeze_support` before
application imports and supplies sink streams in windowed mode, following
[PyInstaller's guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html).

The evaluation CLI is a source-only tool; the packaged app covers desktop and CLI
captioning plus diagnostics. The package is unsigned and has not yet been tested on
a clean Windows machine.
