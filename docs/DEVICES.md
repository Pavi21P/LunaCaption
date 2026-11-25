# Compute devices

CPU is the default. The desktop app's Compute device selector and the CLI
--device option accept cpu or cuda. CUDA is an experimental opt-in path for an
environment with compatible NVIDIA hardware and CUDA-enabled PyTorch. It has not
been exercised on a real GPU in this project.

~~~powershell
.\Launch-LunaCaption.cmd --device cpu
.\Launch-LunaCaption.cmd --device cuda
.\Launch-LunaCaption.cmd "C:\Photos\photo.jpg" --offline --device cuda --output captions.json
~~~

With no image arguments the launcher opens the desktop using the selected device.
The selector is locked during generation. Device preference applies to the current
app window; sessions and recovery files retain their existing format and do not
store a machine's device preference. Opening a session leaves the current choice
unchanged. Restarting without --device uses CPU again.

The status bar reports the actual device once the model is ready, and the batch
summary repeats the fallback reason if CUDA fell back to CPU. CLI status reports
the chosen device and any fallback reason. The selector stays on the requested choice. Switching the requested device
between batches releases the previous engine before loading another. A fallback
engine is reused across later batches with the same requested device.

## Fallback behavior

- CPU requests do not probe CUDA.
- If CUDA is unavailable, or its availability probe fails, use CPU and report it.
- If moving the model to CUDA raises a runtime/initialization error, try moving it
  back to CPU. A failed CPU placement remains a model-load error.
- CUDA out-of-memory during tensor transfer or generation triggers one CPU retry of
  that image. Subsequent images use CPU. A failed CPU recovery stops model work;
  an error during the single CPU retry is reported through the existing batch rules.
- Other inference errors remain errors; they are not hidden by repeated retries.

The model and all processor tensors move to the same device. Token IDs and masks
retain integer types; no half-precision conversion, automatic mixed precision,
device-index selection, or multi-GPU scheduling is added. Generation settings and
CPU thread limits are unchanged. This follows PyTorch's
[device-placement guidance](https://docs.pytorch.org/docs/2.15/notes/cuda.html).
CPU and GPU numerical results can differ; no cross-device caption parity is claimed.

## What was verified

The development host reports Intel HD Graphics 620, torch 2.15.0+cpu, no CUDA build,
zero CUDA devices, and CUDA unavailable. The installed environment, drivers, and
dependency locks were not replaced. The existing Windows setup/build recipe remains
the validated CPU environment; selecting cuda does not install GPU dependencies.

Simulated tests exercise routing, dtype preservation, initialization/placement
failures, memory exhaustion, retry limits, CLI dispatch, and desktop engine reuse.
Real offline runs cover default CPU and a CUDA request falling back to CPU, each
with Tk worker and export checks.

Real CUDA execution, throughput, peak GPU memory, driver compatibility, and GPU
packaging are unverified. Do not use CPU fallback timing as a GPU benchmark.
The evaluation runner stays on the CPU to keep its protocol fixed. The
offline smoke script accepts --device and records requested/actual devices plus
the fallback reason. Use fresh private report paths.
