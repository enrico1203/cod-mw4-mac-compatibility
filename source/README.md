# Compatibility improvement sources

This folder contains sources for the performance, shader compatibility, audio, GPU timing and cache improvements used by release 0.1.

| Folder | Component |
| --- | --- |
| `shader/` | D3DMetal `BarycentricsSupported` capability adjustment and isolated ABI tests. |
| `performance/` | Late input-poll wait, instruction-boundary checks and exact code signatures. |
| `audio/` | Audio routing, driver identity verification and runtime preparation. |
| `gpu-timing/` | Zero-divisor guard for GPU timestamp conversion and code signatures. |
| `cache/` | Connectivity settings, non-destructive cache link preparation and filesystem tests. |
| `common/` | Minimal Windows x64 ABI declarations used by the helper fragments. |

## Shader component

On macOS with Xcode Command Line Tools installed:

```sh
bash source/shader/build.sh
```

This builds an x86-64 `sp26.dylib` in `source/shader/build/`, verifies its ad-hoc signature and runs the included contract checks. The shader component uses identity-guarded native dispatch slots for the tested D3DMetal build. Other builds are not automatically supported by these fixed offsets.

The adjustment changes only a successful, correctly sized OPTIONS3 response advertising `BarycentricsSupported = 1`. It enables the game's fallback shader path; it does not implement the unsupported shader instruction. The tests exercise the two calling conventions and preservation of unrelated fields, results and errno. They are not a rendering or FPS benchmark.

## Audio and runtime preparation

`audio/RuntimePreparation.pm` exposes:

```perl
RuntimePreparation::prepare_runtime($crossover_root, $empty_output_directory, $release_resources_directory);
```

Require the module by an absolute path. The resources directory must contain the released `MW4-Compatibility.exe` and `sp26.dylib`. The module creates a separate runtime using copies and symlinks, prepares the audio correction and early loading of the shader component, then verifies signatures. Installed CrossOver files are read, not overwritten. It does not launch the game.

`audio_route.h` redirects the tested mmdevapi implementation to the prepared driver before audio initialization. `audio_observe.h` verifies the loaded native driver and corrected instruction sequence.

## Helper integration fragments

The performance, GPU timing and audio headers are the release's helper fragments, not standalone applications. Integration requires the helper's process state (`R`), memory read/write helpers, logging helpers, and controlled thread handling.

- Apply the input-poll wait only after audio routing and successful late thread suspension. Preserve its full code-window, Sleep target, instruction-boundary and readback checks. The host supplies `rex_has_legacy_input` after validating the supported input loop.
- The GPU timing guard requires the verified original code and padding, a held target and the helper's memory-write protections. It preserves the nonzero-divisor path and returns an unavailable sample for the zero-divisor path; it does not invent a GPU frequency.

## Cache component

From the repository root:

```sh
perl source/cache/test-cache-connectivity.pl "$(pwd)/source/cache/SP26CacheConnectivity.pm"
```

The module supports planning, applying and checking the connectivity/cache changes. Its tests use temporary fixtures, preserve existing cache data, and cover missing directories, repeat application and conflicting paths. This is cache preparation, not shader compilation.
