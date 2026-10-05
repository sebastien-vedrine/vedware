# Vedware

A small software manager for Windows apps published on **GitHub Releases**.

Paste a repository address (`https://github.com/owner/repo`), and Vedware finds the
Windows installer in its latest release, installs it, then stays in the system tray and
notifies you whenever a new version is published. Interface in English and French
(follows the Windows language).

## Features

- Add apps by GitHub URL, `owner/repo`, or by dropping a link onto the window
- Picks the right file automatically (`.exe` / `.msi` / `.msix` / Windows `.zip`), prefers
  installers and your CPU architecture (x64 / ARM64), skips macOS/Linux files —
  or choose the file yourself per app
- Detects the installed version from *Apps & features*, so apps installed before
  Vedware are recognised
- Background checks (every 1–24 h, also after sleep) with tray notifications
  and an update-count badge; ignored updates are re-announced once a day
- One-click install/update with progress; UAC prompt only when the installer needs it;
  SHA-256 verification when GitHub publishes a digest
- **Automatic updates** (Settings → *Install updates automatically*, off by default):
  updates install silently in the background. Inno Setup, NSIS and MSI installers are
  detected and run unattended; anything else, or a failed attempt, falls back to a
  notification. Can be turned off per app in its ⋯ menu
- Release notes, optional pre-releases, rename, “mark as installed”
- Optional GitHub token (private repos / higher rate limit), encrypted with Windows DPAPI
- Starts with Windows (minimised to tray), single instance, updates itself

## Install

Download **`Installer-Vedware.exe`** from the
[latest release](https://github.com/sebastien-vedrine/Vedware/releases/latest) and
double-click it. One file, no admin rights, nothing to configure. Running a newer
installer updates Vedware in place and keeps your app list and settings.

## Build the installer

- **On Windows:** double-click **`build.bat`**. It installs Python and Inno Setup with winget
  if needed and produces `dist\Installer-Vedware.exe`.
- **On GitHub:** *Actions → Build Windows installer → Run workflow*, then download the
  `.exe` from the run's artifacts. Pushing a tag matching `__version__` in `vedware.py`
  (e.g. `v1.0.0`) also publishes it as a Release, which is how Vedware updates itself.

Run from source: `pip install -r requirements.txt` then `python vedware.py`.

## Files

| Path | Content |
|---|---|
| `%APPDATA%\Vedware\config.json` | app list and settings |
| `%APPDATA%\Vedware\cache\` | cached release data |
| `%LOCALAPPDATA%\Vedware\downloads\` | downloaded installers |
| `%LOCALAPPDATA%\Vedware\apps\` | extracted portable (.zip) apps |

## License

MIT
