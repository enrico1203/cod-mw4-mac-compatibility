MW4 Ultra Textures — included with COD: MW4 Mac Compatibility 1

One entry point
  1. Copy this whole MW4-Ultra-Textures folder into the game's sp26 folder.
  2. Open Ultra-Textures.command directly on your Mac.
  3. It finds the game, calculates the highest-quality campaign download and
     asks for confirmation. The size comes from your game's catalogue.
  4. Choose Download. A progress bar shows percentage, downloaded/total size,
     current speed and estimated time left. You can pause with Control-C.
  5. Open the same command again to resume. When everything is downloaded and
     verified, the same entry offers Start Textures for your next play session.

No CrossOver is needed to run this add-on. Python 3.10+ is required. No extra
Python packages. Keep using your existing fix/CrossOver to launch the game.

Storage and size
  The current full campaign + boot set is 103,631 pieces: 81.6 GiB (87.6 GB).
  Ultra includes every texture size, including the largest pieces. Multiplayer
  and DMZ packages are excluded. The download size is calculated, not hardcoded.
  The default mirror is next to the game folder, outside the installed game.
  If there is not enough space, it offers a folder picker for another drive.
  It keeps 10 GiB free; planning also includes a 2% download-space margin.
  Confirmation shows the estimated space left after the remaining download.
  The former 40 GiB default from 0.1/0.2 settings is migrated automatically;
  your storage location and other custom reserve values are preserved.
  Your download does not start unless you choose Download or Resume Download.
  Cancelling leaves the existing game and mirror unchanged. The add-on keeps
  only its own settings/logs in its Data folder inside this add-on folder.

Download and verification
  Four connections, no bandwidth or quality-size cap. The CDN's rate limits
  and Retry-After are respected. Expected length and MD5 ETag must match.
  Progress appears in the Terminal window; confirmation dialogs are native
  macOS windows. Details of each run are saved in Data/Logs.
  Pausing finishes in-flight pieces. Reopening this command resumes the rest.
  Verification checks the full set. Corrupt pieces are reset for downloading;
  missing/unavailable pieces keep the mirror incomplete.
  Once the full campaign is verified, old file variants and .part leftovers
  of the same verified chunk are removed from this add-on's objects folder.
  Its current copy is checked again before cleanup. Smaller detail levels are
  kept: Ultra still includes every size. Unknown files/ids and symlinks are kept.
  This cleans redundant add-on storage; it does not clear the game's cache.
  Copies of version 0.2.2 share a storage lock across download/verify/play,
  so two copies cannot change or serve that same mirror at the same time.

While playing
  This download is separate storage, not a ready-made engine cache.
  Another drive works because the service supplies files requested by the game.
  That drive must stay connected while playing. The game may also grow its own
  cache; the remaining-space estimate covers this download only. The local
  service must stay open every time you play. Start Textures asks for an admin
  password to open port 80 and temporarily route the texture CDN to loopback.
  File serving runs as your ordinary user, offline, with no quality filter.
  Launch the game with your existing fix after starting textures.
  After you exit the game, press Control-C in the texture window, or open
  Ultra-Textures.command again and choose Stop Textures. Its routing is restored.
  An interrupted session can offer Restore Routing from that same entry.

The texture component does not alter game
EXE/DLL, settings, shaders, saves or CrossOver, and does not terminate the game.
No game content, keys or catalogues are included in this package. Keep downloaded
publisher content local and use it only with your own installed game.

See VALIDATION.txt for exact test scope. A completed download or a successful
HTTP test does not establish HD rendering, performance or long-session stability.
A later real user game session verified local texture delivery on the tested Mac.
Controlled image-quality, FPS and long-session comparisons have not been performed.

Downloader adapted from voidfnc/mw4-texture-streaming-research v0.3.0-beta,
commit b79be342461d24d50797593c5282ecf1e2e5617b. MIT license preserved in
UPSTREAM-LICENSE.txt. See MODIFICATIONS.txt for local changes.
