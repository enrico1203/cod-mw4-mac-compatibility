# COD: MW4 Mac Compatibility

Compatibility and performance improvements for running COD: MW4 on macOS with CrossOver.

**Version 0.1**

## Improvements

- Startup fixes
- Performance and stability improvements
- Shader compatibility improvements
- Audio fixes
- Automatic cache and connectivity setup

## Installation

1. Download and extract the ZIP from **Releases**.
2. Copy `MW4-Compatibility.exe` and `sp26.dylib` into the game's `sp26` folder.
3. In your CrossOver bottle, use **Run Command** to open `MW4-Compatibility.exe`.

Use this EXE for future launches. You can save it as a CrossOver launcher.
Keep both files together. No launch arguments or separate setup command are needed.

## Recommended setup

- CrossOver Preview with D3DMetal 4.0b3.
- Select **D3DMetal** as the graphics backend for your game bottle.
- Enable **Metal 4** and **MSync** in CrossOver for your game bottle (recommended).

## Tested configuration

**M4 Max / macOS 27 / CrossOver Preview 27.0.0.41073 / D3DMetal 4.0b3**

This is the tested configuration, not a minimum hardware or exact-version requirement. Other configurations have not yet been verified.

## Project status

On the tested configuration, the game is now playable and has been largely stable in our play sessions. Development is still at an early stage, with further performance, compatibility and stability improvements planned.

The first game window may take a while to appear.

## Reporting an issue

Open an issue with your Mac model, macOS version, CrossOver version and a description of the problem. Include the error message or a screenshot when available.
