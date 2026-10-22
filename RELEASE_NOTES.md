# COD: MW4 Mac Compatibility 1

Our first stable release, now including Ultra Textures.

- Startup, performance, shader compatibility and audio improvements.
- Improved GPU timing and exception handling.
- Updated initialization and cache/connectivity preparation.
- Included Ultra texture downloader with resume, verification and local streaming.

Copy the two program files and the `MW4-Ultra-Textures` folder into `sp26`. Open `MW4-Compatibility.exe` through CrossOver; no arguments or separate setup are needed for the compatibility fix.

For textures, open `MW4-Ultra-Textures/Ultra-Textures.command` on your Mac. It shows the download size and location before downloading. After verification, choose **Start Textures**, keep its window open, and launch the game as usual. Python 3.10+ is required; starting textures asks for macOS administrator permission.

See the README for the recommended setup and tested configuration. Further compatibility and performance improvements are planned. The first game window can still take a while to appear.
