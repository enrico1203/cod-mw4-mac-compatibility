# Compatibility improvement sources

Components used by release 1.

| Folder | Component |
| --- | --- |
| `shader/` | Barycentrics capability adjustment and two exact-match shader compatibility replacements. |
| `performance/` | Late input-poll wait and instruction checks. |
| `gpu-timing/` | Raw-frequency timestamp conversion, zero-divisor protection and overflow handling. |
| `exceptions/` | Eight checked dispatcher-relative operand corrections. |
| `launch/` | Initialization wait policy and a modeless notice that keeps event processing active. |
| `audio/` | Audio routing, driver verification and local runtime preparation. |
| `cache/` | Optional connectivity/cache preparation and filesystem tests. |
| `ultra-textures/` | Native Mac downloader, verification, local texture service and offline tests. |
| `common/` | Minimal Windows x64 ABI declarations. |

## Shader component

With Xcode Command Line Tools installed:

```sh
bash source/shader/build.sh
```

This builds and signs an x86-64 `sp26.dylib`, then runs the capability contract tests. The module verifies the relevant D3DMetal method and dispatch layout. Shader replacements are limited to two exact bytecode hashes; other shaders pass through unchanged. The capability change affects only a successful, correctly sized OPTIONS3 response advertising barycentrics support.

These checks do not establish rendering correctness or an FPS improvement.

## Audio and runtime preparation

`RuntimePreparation::prepare_runtime($crossover_root, $empty_output_directory, $resources_directory)` creates a local runtime using copies and symlinks. Require the module by an absolute path; supply the released EXE and dylib in the resources directory. Installed CrossOver files are read rather than overwritten. Preparation does not launch the game.

Audio changes require matching instructions at the operation being applied. The helper headers route and verify the prepared driver before audio initialization.

## Helper integration

The headers use the helper's existing process state, memory read/write operations and logging functions. Apply memory changes only while the relevant target is held, retain complete instruction checks, and verify writes.

- GPU timing uses the real returned frequency. Failed results, zero frequency and quotient overflow produce an unavailable sample. The zero-divisor guard remains intact; conversion success does not prove that every query is valid.
- Exception corrections check every original code window before writing the eight operands.
- Input polling is updated only at the established late initialization point.
- Late initialization keeps the required-hook safety deadline. A modeless waiting notice lets debug event processing continue and closes when startup completes or ends.

The launch contract tests run with temporary host fixtures and do not launch the game:

```sh
bash source/launch/test.sh
```

## Cache component

```sh
perl source/cache/test-cache-connectivity.pl "$(pwd)/source/cache/SP26CacheConnectivity.pm"
```

The module plans and applies non-destructive cache/connectivity preparation. Its best-effort entry point records an unavailable or conflicting optional operation and allows launch to continue. Existing cache data is preserved. These tests use temporary files and do not compile game shaders.

## Ultra textures

The complete component is in `ultra-textures/`. Its entry command is intended
to run from the `MW4-Ultra-Textures` folder placed inside the game's `sp26`.
The reviewed implementation revision is 0.2.2; it is bundled with release 1.
Upstream MIT notices and the modification record are preserved alongside it.
No downloaded publisher content, catalogue, settings or session token is included.

Offline tests use temporary data and synthetic loopback HTTP:

```sh
MW4_ADDON_TEST_PACKAGE="$(pwd)/source/ultra-textures" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s source/ultra-textures/tests
```

These tests do not activate the real privileged service or establish rendering quality.
