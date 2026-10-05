#!/usr/bin/env python3
"""Vedware — a software manager for Windows apps published on GitHub Releases.

Add GitHub repository URLs; Vedware finds the Windows installer in each
repository's releases, installs it, keeps running in the system tray and
notifies you when a new version is published.
"""
from __future__ import annotations

import base64
import fnmatch
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLocale, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QFont, QIcon,
                           QPainter, QPainterPath, QPixmap)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QSystemTrayIcon, QTextBrowser, QToolButton,
                               QVBoxLayout, QWidget)

APP_NAME = "Vedware"
__version__ = "1.1.1"
SELF_REPO = "sebastien-vedrine/Vedware"
SELF_ID = SELF_REPO.lower()
# Added automatically on first launch. Edit to taste.
DEFAULT_REPOS = [SELF_REPO, "sebastien-vedrine/PDF-Facile"]

IS_WIN = sys.platform == "win32"
API = "https://api.github.com"

_home = os.environ.get("VEDWARE_HOME")
CONFIG_DIR = Path(_home) if _home else Path(os.environ.get("APPDATA") or Path.home() / ".config") / APP_NAME
DATA_DIR = Path(_home) if _home else Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local/share") / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = CONFIG_DIR / "cache"
AVATAR_DIR = CONFIG_DIR / "avatars"
DOWNLOAD_DIR = DATA_DIR / "downloads"
PORTABLE_DIR = DATA_DIR / "apps"

HEARTBEAT_MS = 10 * 60 * 1000          # how often we ask "is a check due?"
REMIND_AFTER_S = 24 * 3600             # re-notify an ignored update once a day
RECHECK_ON_OPEN_S = 5 * 60             # reopening the window re-checks if the last check is older


def resource_path(name: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name


# --------------------------------------------------------------------------- i18n
LANG = "en"
STRINGS = {
    "tagline": ("Your Windows apps from GitHub, always up to date",
                "Vos logiciels Windows depuis GitHub, toujours à jour"),
    "add_placeholder": ("Paste a GitHub repository address, e.g. github.com/owner/repo",
                        "Collez l'adresse d'un dépôt GitHub, ex. : github.com/proprietaire/depot"),
    "add": ("Add", "Ajouter"),
    "adding": ("Adding…", "Ajout…"),
    "check_now": ("Check for updates", "Rechercher les mises à jour"),
    "settings": ("Settings", "Paramètres"),
    "empty": ("No software yet.\nPaste a GitHub repository address above to get started.",
              "Aucun logiciel pour le moment.\nCollez l'adresse d'un dépôt GitHub ci-dessus pour commencer."),
    "installed": ("Installed {v}", "Installé : {v}"),
    "not_installed": ("Not installed", "Non installé"),
    "latest": ("Latest {v}", "Dernière version : {v}"),
    "up_to_date": ("Up to date", "À jour"),
    "update_to": ("Update available: {v}", "Mise à jour disponible : {v}"),
    "no_windows_asset": ("No Windows download in the recent releases",
                         "Aucun fichier Windows dans les versions récentes"),
    "no_release": ("No release published yet", "Aucune version publiée"),
    "checking": ("Checking…", "Vérification…"),
    "install": ("Install", "Installer"),
    "update": ("Update", "Mettre à jour"),
    "downloading": ("Downloading… {p}%", "Téléchargement… {p} %"),
    "installing": ("Installing… finish the steps in the installer window",
                   "Installation… suivez les étapes dans la fenêtre d'installation"),
    "menu_notes": ("What's new in {v}", "Nouveautés de la version {v}"),
    "menu_github": ("Open on GitHub", "Ouvrir sur GitHub"),
    "menu_reinstall": ("Reinstall {v}", "Réinstaller la version {v}"),
    "menu_rename": ("Rename…", "Renommer…"),
    "menu_prerelease": ("Include pre-releases", "Inclure les versions préliminaires"),
    "menu_pattern": ("Choose the file to download…", "Choisir le fichier à télécharger…"),
    "menu_mark": ("Mark {v} as installed", "Marquer la version {v} comme installée"),
    "menu_forget": ("Forget installed version", "Oublier la version installée"),
    "menu_check": ("Check this app now", "Vérifier ce logiciel maintenant"),
    "menu_remove": ("Remove from list", "Retirer de la liste"),
    "pattern_title": ("File to download", "Fichier à télécharger"),
    "pattern_label": ("Which file of the release should Vedware download?",
                      "Quel fichier de la version Vedware doit-il télécharger ?"),
    "pattern_auto": ("Automatic (recommended)", "Automatique (recommandé)"),
    "rename_title": ("Rename", "Renommer"),
    "rename_label": ("Display name:", "Nom affiché :"),
    "remove_confirm": ("Remove {n} from the list?\nThe software itself stays installed.",
                       "Retirer {n} de la liste ?\nLe logiciel reste installé sur l'ordinateur."),
    "invalid_url": ("This doesn't look like a GitHub repository address.\nExample: https://github.com/owner/repo",
                    "Cette adresse ne ressemble pas à un dépôt GitHub.\nExemple : https://github.com/proprietaire/depot"),
    "already": ("{n} is already in the list.", "{n} est déjà dans la liste."),
    "last_check": ("Last check: {t}", "Dernière vérification : {t}"),
    "never_checked": ("Not checked yet", "Pas encore vérifié"),
    "checking_all": ("Checking for updates…", "Recherche de mises à jour…"),
    "n_updates": ("{n} update(s) available", "{n} mise(s) à jour disponible(s)"),
    "notif_one": ("{n} {v} is available", "{n} {v} est disponible"),
    "notif_one_body": ("Click to open Vedware and update.", "Cliquez pour ouvrir Vedware et mettre à jour."),
    "notif_many": ("{c} updates available", "{c} mises à jour disponibles"),
    "notif_installed": ("{n} {v} installed", "{n} {v} est installé"),
    "tray_hint": ("Vedware keeps running here and will tell you when updates are available.",
                  "Vedware reste ouvert ici et vous préviendra quand des mises à jour seront disponibles."),
    "tray_open": ("Open Vedware", "Ouvrir Vedware"),
    "tray_quit": ("Quit", "Quitter"),
    "s_interval": ("Check for updates every", "Rechercher les mises à jour toutes les"),
    "s_hours": ("{h} hour(s)", "{h} heure(s)"),
    "s_autostart": ("Start Vedware with Windows", "Démarrer Vedware avec Windows"),
    "s_notify": ("Show a notification when an update is available",
                 "Afficher une notification quand une mise à jour est disponible"),
    "s_language": ("Language", "Langue"),
    "s_lang_auto": ("Automatic", "Automatique"),
    "s_lang_restart": ("Language changes apply after restarting Vedware.",
                       "Le changement de langue s'appliquera au prochain démarrage de Vedware."),
    "s_token": ("GitHub token (optional)", "Jeton GitHub (facultatif)"),
    "s_token_help": ("Only needed for private repositories or many apps. Stored encrypted for your Windows account.",
                     "Utile seulement pour des dépôts privés ou beaucoup de logiciels. Stocké chiffré pour votre compte Windows."),
    "s_about": ("Vedware {v}", "Vedware {v}"),
    "err_not_found": ("Repository not found (or private)", "Dépôt introuvable (ou privé)"),
    "err_rate_limit": ("GitHub limit reached — try again later or add a token in Settings",
                       "Limite GitHub atteinte — réessayez plus tard ou ajoutez un jeton dans les paramètres"),
    "err_bad_token": ("The GitHub token was refused", "Le jeton GitHub a été refusé"),
    "err_network": ("No connection to GitHub", "Pas de connexion à GitHub"),
    "err_bad_checksum": ("The download is corrupted (checksum mismatch)",
                         "Le fichier téléchargé est corrompu (somme de contrôle incorrecte)"),
    "err_cancelled": ("Installation cancelled", "Installation annulée"),
    "err_exit_code": ("The installer stopped with code {c}", "L'installateur s'est arrêté avec le code {c}"),
    "err_title": ("Vedware", "Vedware"),
    "check_failed": ("Last check failed: {e}", "Échec de la dernière vérification : {e}"),
    "install_failed": ("Couldn't install {n}: {e}", "Impossible d'installer {n} : {e}"),
    "auto_updating": ("Updating automatically…", "Mise à jour automatique…"),
    "auto_manual": ("This installer can't run unattended — click Update",
                    "Ce logiciel ne peut pas se mettre à jour tout seul — cliquez sur Mettre à jour"),
    "menu_auto": ("Update automatically", "Mettre à jour automatiquement"),
    "s_auto": ("Install updates automatically", "Installer les mises à jour automatiquement"),
    "s_auto_help": ("Updates install silently in the background. Apps whose installer can't run "
                    "unattended still get a notification instead.",
                    "Les mises à jour s'installent en arrière-plan, sans rien demander. Pour les logiciels "
                    "qui ne le permettent pas, vous recevrez une notification à la place."),
    "notif_updated": ("{n} updated to {v}", "{n} a été mis à jour ({v})"),
    "notif_auto_failed": ("{n} {v} needs your attention", "{n} {v} : action nécessaire"),
    "notif_auto_failed_body": ("It couldn't be updated automatically. Click to open Vedware.",
                               "La mise à jour automatique n'a pas abouti. Cliquez pour ouvrir Vedware."),
    "self_update": ("Vedware will close to update itself.", "Vedware va se fermer pour se mettre à jour."),
}


def tr(key: str, **kw) -> str:
    pair = STRINGS.get(key)
    s = (pair[1] if LANG == "fr" else pair[0]) if pair else key
    return s.format(**kw) if kw else s


def tr_error(code: str) -> str:
    return tr(f"err_{code}") if f"err_{code}" in STRINGS else code


# --------------------------------------------------------------------------- helpers
def now_ts() -> float:
    return time.time()


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("+", "plus"))


def pretty_version(tag: str | None) -> str:
    return re.sub(r"^[vV](?=\d)", "", tag or "")


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)


def parse_repo(text: str):
    """Return (owner, repo) from a GitHub URL, SSH address or 'owner/repo'."""
    t = (text or "").strip().strip("<>\"'")
    m = (re.match(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)", t, re.I)
         or re.match(r"^git@github\.com:([\w.-]+)/([\w.-]+)", t, re.I)
         or re.match(r"^([\w.-]+)/([\w.-]+)/?$", t))
    if not m:
        return None
    owner, repo = m.group(1), re.sub(r"\.git$", "", m.group(2), flags=re.I)
    if not repo or owner.lower() in ("orgs", "settings", "topics", "search", "marketplace"):
        return None
    return owner, repo


_PRE_RANK = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "pre": 3, "preview": 3, "rc": 4}


def parse_version(s: str | None):
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)*)(.*)", s)
    if not m:
        return None
    nums = [int(x) for x in m.group(1).split(".")]
    while len(nums) > 1 and nums[-1] == 0:
        nums.pop()
    pm = re.match(r"[-._ +]?(dev|alpha|beta|preview|pre|rc|a|b)[-._ ]?(\d*)", m.group(2).lower())
    if pm:
        return tuple(nums), 0, _PRE_RANK[pm.group(1)], int(pm.group(2) or 0)
    return tuple(nums), 1, 0, 0


def is_newer(candidate: str | None, current: str | None) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    if a is None or b is None:
        return norm(pretty_version(candidate)) != norm(pretty_version(current))
    return a > b


def host_arch() -> str:
    a = (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE")
         or platform.machine()).lower()
    if a in ("arm64", "aarch64"):
        return "arm64"
    if a in ("x86", "i386", "i686"):
        return "x86"
    return "amd64"


HOST_ARCH = host_arch()
_EXT_SCORE = [(".msixbundle", 20), (".msix", 20), (".msi", 28), (".exe", 30), (".zip", 10)]
_OTHER_OS = {"mac", "macos", "darwin", "osx", "linux", "appimage", "deb", "rpm", "android", "ios", "apk"}
_JUNK = {"debug", "symbols", "pdb", "src", "source", "sources"}


def asset_score(name: str):
    """Score how likely a release file is the Windows installer for this PC (None = no)."""
    n = name.lower()
    ext = next((e for e, _ in _EXT_SCORE if n.endswith(e)), None)
    if not ext:
        return None
    n2 = n.replace("x86_64", "x64").replace("x86-64", "x64")
    tokens = set(re.split(r"[^a-z0-9]+", n2))
    if tokens & _OTHER_OS or tokens & _JUNK:
        return None
    win = bool(tokens & {"win", "windows", "win64", "win32", "msvc"}) or "win" in n2
    if ext == ".zip" and not win:
        return None
    score = dict(_EXT_SCORE)[ext]
    if "setup" in n2 or "install" in n2:
        score += 8
    if win:
        score += 3
    if tokens & {"arm64", "aarch64", "arm"}:
        score += 6 if HOST_ARCH == "arm64" else -40
    elif tokens & {"x64", "amd64", "win64", "64bit"}:
        score += {"amd64": 5, "arm64": -2, "x86": -40}[HOST_ARCH]
    elif tokens & {"x86", "i386", "i686", "ia32", "32bit"}:
        score += 5 if HOST_ARCH == "x86" else -6
    if "portable" in tokens:
        score -= 4
    return score if score >= 0 else None


def pick_asset(assets: list, pattern: str | None = None):
    if pattern:
        matches = [a for a in assets if fnmatch.fnmatch(a["name"].lower(), pattern.lower())]
        matches.sort(key=lambda a: asset_score(a["name"]) or 0, reverse=True)
        return matches[0] if matches else None
    scored = [(asset_score(a["name"]), a) for a in assets]
    scored = [(s, a) for s, a in scored if s is not None]
    return max(scored, key=lambda x: x[0])[1] if scored else None


def pattern_from_name(name: str) -> str:
    """'Installer-PDF-Facile-1.6.exe' -> 'Installer-PDF-Facile-*.exe' (survives new versions)."""
    p = re.sub(r"v?\d+(?:\.\d+)+", "*", name)
    return re.sub(r"\*+", "*", p)


def pick_release(releases: list, include_pre: bool, pattern: str | None):
    """Newest non-draft release that has a Windows download → (release, asset, reason)."""
    seen = False
    for r in releases or []:
        if r.get("draft") or (r.get("prerelease") and not include_pre):
            continue
        seen = True
        asset = pick_asset(r.get("assets") or [], pattern)
        if asset:
            return r, asset, None
    return None, None, ("no_windows_asset" if seen else "no_release")


# --------------------------------------------------------------------------- GitHub
class GitHubError(Exception):
    pass


class _StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Don't forward the GitHub token to the storage host GitHub redirects downloads to."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.remove_header("Authorization")
        return new


_opener = urllib.request.build_opener(_StripAuthRedirect())


def _request(url, token=None, etag=None, accept="application/vnd.github+json"):
    headers = {"User-Agent": f"{APP_NAME}/{__version__}", "Accept": accept}
    if urllib.parse.urlsplit(url).netloc == "api.github.com":
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        if token:
            headers["Authorization"] = f"Bearer {token}"
    if etag:
        headers["If-None-Match"] = etag
    return urllib.request.Request(url, headers=headers)


def _raise_for(e: urllib.error.HTTPError):
    if e.code == 404:
        raise GitHubError("not_found")
    if e.code == 401:
        raise GitHubError("bad_token")
    if e.code == 429 or (e.code == 403 and e.headers.get("X-RateLimit-Remaining") == "0"):
        raise GitHubError("rate_limit")
    raise GitHubError(f"HTTP {e.code}")


def http_get(url, token=None, etag=None, timeout=20):
    try:
        with _opener.open(_request(url, token, etag), timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return 304, b"", etag
        _raise_for(e)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GitHubError("network")


def fetch_repo_info(owner, repo, token=None) -> dict:
    _, body, _ = http_get(f"{API}/repos/{owner}/{repo}", token)
    d = json.loads(body)
    return {"full_name": d["full_name"], "description": d.get("description") or "",
            "html_url": d.get("html_url"), "avatar_url": (d.get("owner") or {}).get("avatar_url")}


def trim_release(r: dict) -> dict:
    return {
        "tag_name": r.get("tag_name"), "name": r.get("name"), "draft": r.get("draft"),
        "prerelease": r.get("prerelease"), "published_at": r.get("published_at"),
        "html_url": r.get("html_url"), "body": (r.get("body") or "")[:20000],
        "assets": [{"name": a["name"], "url": a["browser_download_url"], "api_url": a.get("url"),
                    "size": a.get("size") or 0, "digest": a.get("digest")}
                   for a in r.get("assets") or []],
    }


def download_file(asset, dest: Path, token, progress_cb):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    if token and asset.get("api_url"):
        req = _request(asset["api_url"], token, accept="application/octet-stream")
    else:
        req = _request(asset["url"], accept="application/octet-stream")
    h = hashlib.sha256()
    try:
        with _opener.open(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or asset.get("size") or 0)
            done, last = 0, -1
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    p = min(100, done * 100 // total)
                    if p != last:
                        progress_cb(p)
                        last = p
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        _raise_for(e)
    except (urllib.error.URLError, TimeoutError, OSError):
        tmp.unlink(missing_ok=True)
        raise GitHubError("network")
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:") and h.hexdigest() != digest[7:].lower():
        tmp.unlink(missing_ok=True)
        raise GitHubError("bad_checksum")
    os.replace(tmp, dest)
    return dest


# --------------------------------------------------------------------------- Windows integration
def registry_entries() -> list:
    """(DisplayName, DisplayVersion) of everything in Add/Remove Programs."""
    if not IS_WIN:
        return []
    import winreg
    path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    out = []
    for root, flag in ((winreg.HKEY_CURRENT_USER, 0),
                       (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                       (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY)):
        try:
            key = winreg.OpenKey(root, path, 0, winreg.KEY_READ | flag)
        except OSError:
            continue
        with key:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(key, sub) as sk:
                        name = winreg.QueryValueEx(sk, "DisplayName")[0]
                        try:
                            ver = winreg.QueryValueEx(sk, "DisplayVersion")[0]
                        except OSError:
                            ver = None
                    out.append((str(name), str(ver) if ver else None))
                except OSError:
                    continue
    return out


def strip_display_version(name: str) -> str:
    n = re.sub(r"(\s*[(\[][^)\]]*[)\]])+\s*$", "", name)
    return re.sub(r"[\s_-]+(v(ersion)?\s*)?\d+(\.\d+)*.*$", "", n, flags=re.I)


def detect_installed(app: dict, reg: list):
    if app["id"] == SELF_ID:
        return __version__
    keys = {k for k in (norm(app["repo"]), norm(app.get("name", ""))) if len(k) >= 3}
    best = None
    for name, ver in reg:
        if ver and norm(strip_display_version(name)) in keys:
            if best is None or is_newer(ver, best):
                best = ver
    return best


class InstallCancelled(Exception):
    pass


class NeedsManualInstall(Exception):
    pass


def installer_kind(path: Path) -> str:
    """Identify the installer technology so we know how to run it unattended."""
    ext = path.suffix.lower()
    if ext == ".msi":
        return "msi"
    if ext in (".msix", ".msixbundle"):
        return "msix"
    if ext != ".exe":
        return "unknown"
    marks = {"inno": (b"Inno Setup", "Inno Setup".encode("utf-16-le")),
             "nsis": (b"Nullsoft.NSIS", b"NullsoftInst", b"Nullsoft Install System")}
    try:
        with open(path, "rb") as f:
            head = f.read(8 * 1024 * 1024)
    except OSError:
        return "unknown"
    for kind, needles in marks.items():
        if any(n in head for n in needles):
            return kind
    return "unknown"


SILENT_ARGS = {
    "inno": "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS",
    "nsis": "/S",
}


def silent_command(path: Path):
    """(file, parameters) to install without any window, or None if we can't do it safely."""
    kind = installer_kind(path)
    if kind == "msi":
        return "msiexec.exe", f'/i "{path}" /passive /norestart'
    if kind in SILENT_ARGS:
        return str(path), SILENT_ARGS[kind]
    return None


def run_installer_and_wait(path: Path, params: str | None = None, file: str | None = None):
    """ShellExecuteEx so installers that need admin rights get their UAC prompt; wait for exit."""
    if not IS_WIN:
        raise RuntimeError("Installers can only run on Windows")
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                    ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

    shell32, kernel32 = ctypes.windll.shell32, ctypes.windll.kernel32
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040 | 0x00000100          # NOCLOSEPROCESS | NOASYNC
    info.lpVerb = "open"
    info.lpFile = file or str(path)
    info.lpParameters = params
    info.lpDirectory = str(path.parent)
    info.nShow = 0 if params else 1
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = kernel32.GetLastError()
        if err == 1223:                            # user said "No" to UAC
            raise InstallCancelled()
        raise ctypes.WinError(err)
    if not info.hProcess:
        return None                                # handed off (e.g. MSIX App Installer)
    kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    kernel32.CloseHandle(info.hProcess)
    return code.value


def launch_detached(path: Path, params: str = ""):
    if IS_WIN:
        os.startfile(str(path), "open", params)  # noqa: S606
    else:
        raise RuntimeError("Installers can only run on Windows")


def open_path(path: Path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else sys.executable}" "{Path(__file__).resolve()}" --minimized'


def set_autostart(enabled: bool):
    if not IS_WIN:
        return
    import winreg
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if enabled:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def encrypt_secret(s: str) -> str:
    if not s:
        return ""
    raw = s.encode()
    if IS_WIN:
        try:
            return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode()
        except OSError:
            pass
    return "plain:" + base64.b64encode(raw).decode()


def decrypt_secret(s: str) -> str:
    try:
        kind, _, data = (s or "").partition(":")
        raw = base64.b64decode(data)
        return (_dpapi(raw, False) if kind == "dpapi" else raw).decode()
    except Exception:
        return ""


# --------------------------------------------------------------------------- storage
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def cache_path(app_id: str) -> Path:
    return CACHE_DIR / (safe_name(app_id.replace("/", "__")) + ".json")


def display_name(repo: str) -> str:
    name = re.sub(r"[-_]+", " ", repo).strip() or repo
    return name[:1].upper() + name[1:] if name.islower() else name


def new_app(owner: str, repo: str, info: dict | None = None) -> dict:
    app = {"id": f"{owner}/{repo}".lower(), "owner": owner, "repo": repo,
           "name": display_name(repo), "prerelease": False, "pattern": None,
           "installed_version": None, "detected": None, "etag": None, "last_checked": None,
           "error": None, "notified": None, "auto_update": True, "auto_failed": None}
    if info:
        app.update(info)
    return app


def default_config() -> dict:
    return {"language": "auto", "interval_hours": 6, "notify": True, "autostart": True, "auto_update": False,
            "token": "", "last_check": None, "tray_hint_shown": False,
            "apps": [new_app(*parse_repo(r)) for r in DEFAULT_REPOS]}


# --------------------------------------------------------------------------- background work
def check_app(app: dict, token: str, reg: list, has_cache: bool) -> dict:
    res = {"error": None, "releases": None, "info": None, "avatar": False}
    owner, repo = app["owner"], app["repo"]
    try:
        if not app.get("avatar_url"):
            res["info"] = fetch_repo_info(owner, repo, token)
        st, body, etag = http_get(f"{API}/repos/{owner}/{repo}/releases?per_page=15", token,
                                  app.get("etag") if has_cache else None)
        res["etag"] = etag
        if st != 304:
            res["releases"] = [trim_release(r) for r in json.loads(body)]
    except GitHubError as e:
        res["error"] = str(e)
    avatar_url = (res["info"] or {}).get("avatar_url") or app.get("avatar_url")
    avatar_file = AVATAR_DIR / f"{safe_name(owner.lower())}.png"
    if avatar_url and not avatar_file.exists():
        try:
            sep = "&" if "?" in avatar_url else "?"
            _, data, _ = http_get(f"{avatar_url}{sep}s=96")
            avatar_file.parent.mkdir(parents=True, exist_ok=True)
            avatar_file.write_bytes(data)
            res["avatar"] = True
        except GitHubError:
            pass
    res["detected"] = detect_installed(app, reg)
    res["checked_at"] = now_ts()
    return res


class Bridge(QObject):
    """Carries results from worker threads back to the GUI thread (queued signals)."""
    checked = Signal(str, dict)
    check_done = Signal(bool)
    added = Signal(str, str, dict)
    add_failed = Signal(str)
    progress = Signal(str, int)
    phase = Signal(str, str)
    install_done = Signal(str, dict)
    install_failed = Signal(str, str)
    activate = Signal()


# --------------------------------------------------------------------------- UI
ACCENT, ACCENT_DARK, ORANGE, GREEN, MUTED = "#4f46e5", "#4338ca", "#ea580c", "#16a34a", "#6b7385"

STYLE = f"""
QMainWindow, #central {{ background: #f4f6fb; }}
QWidget {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: #1d2433; }}
#title {{ font-size: 20pt; font-weight: 700; }}
#tagline, #cardSub, #footer {{ color: {MUTED}; }}
#card {{ background: white; border: 1px solid #e3e7ef; border-radius: 12px; }}
#card[highlight="true"] {{ border: 2px solid {ACCENT}; }}
#cardTitle {{ font-size: 12pt; font-weight: 600; }}
#empty {{ color: {MUTED}; font-size: 11pt; padding: 50px; }}
QScrollArea, #cards {{ background: transparent; border: none; }}
QLineEdit {{ padding: 9px 11px; border: 1px solid #cfd6e4; border-radius: 8px; background: white; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{ padding: 8px 16px; border-radius: 8px; border: 1px solid #cfd6e4; background: white; }}
QPushButton:hover {{ background: #eef1f8; }}
QPushButton:disabled {{ color: #9aa3b5; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; color: white; border: none; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {ACCENT_DARK}; }}
QPushButton[kind="update"] {{ background: {ORANGE}; color: white; border: none; font-weight: 600; }}
QPushButton[kind="update"]:hover {{ background: #c2410c; }}
QToolButton {{ border: none; border-radius: 8px; padding: 4px 10px; font-size: 14pt; color: {MUTED}; }}
QToolButton:hover {{ background: #eef1f8; }}
QToolButton::menu-indicator {{ image: none; }}
QProgressBar {{ border: none; background: #e7eaf3; border-radius: 4px; max-height: 8px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QMenu {{ background: white; border: 1px solid #e3e7ef; padding: 4px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: #eef1f8; color: #1d2433; }}
"""


def app_icon() -> QIcon:
    p = resource_path("icon.ico")
    return QIcon(str(p)) if p.exists() else QIcon(letter_pixmap("V", 64))


def letter_pixmap(text: str, size: int, color: str = ACCENT) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
    f = QFont("Segoe UI", int(size * 0.42), QFont.Bold)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(pm.rect(), Qt.AlignCenter, text[:1].upper())
    p.end()
    return pm


def rounded(pm: QPixmap, size: int) -> QPixmap:
    pm = pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


def badge_icon(base: QIcon, count: int) -> QIcon:
    if not count:
        return base
    pm = base.pixmap(64, 64)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(ORANGE)))
    p.setPen(QColor("white"))
    p.drawEllipse(30, 30, 33, 33)
    p.setFont(QFont("Segoe UI", 15, QFont.Bold))
    p.drawText(30, 30, 33, 33, Qt.AlignCenter, str(min(count, 9)))
    p.end()
    return QIcon(pm)


def fmt_time(ts) -> str:
    if not ts:
        return tr("never_checked")
    dt = datetime.fromtimestamp(ts)
    fmt = "%d/%m %H:%M" if LANG == "fr" else "%b %d, %H:%M"
    return tr("last_check", t=dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime(fmt))


class AppCard(QFrame):
    def __init__(self, win: "MainWindow", app_id: str):
        super().__init__()
        self.win, self.app_id = win, app_id
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 10, 12)
        lay.setSpacing(14)
        self.avatar = QLabel()
        self.avatar.setFixedSize(48, 48)
        lay.addWidget(self.avatar, 0, Qt.AlignTop)
        mid = QVBoxLayout()
        mid.setSpacing(2)
        self.title = QLabel(objectName="cardTitle")
        self.sub = QLabel(objectName="cardSub")
        self.sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status = QLabel()
        self.status.setTextFormat(Qt.RichText)
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        for w in (self.title, self.sub, self.status, self.progress):
            mid.addWidget(w)
        lay.addLayout(mid, 1)
        self.button = QPushButton()
        self.button.setMinimumWidth(130)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(lambda: win.install(app_id))
        lay.addWidget(self.button, 0, Qt.AlignVCenter)
        self.more = QToolButton()
        self.more.setText("⋯")
        self.more.setPopupMode(QToolButton.InstantPopup)
        self.more.setCursor(Qt.PointingHandCursor)
        self.menu = QMenu(self)
        self.menu.aboutToShow.connect(self.build_menu)
        self.more.setMenu(self.menu)
        lay.addWidget(self.more, 0, Qt.AlignVCenter)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self, self.refresh)

    def set_kind(self, kind):
        self.button.setProperty("kind", kind)
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)

    def refresh(self):
        app = self.win.app(self.app_id)
        if not app:
            return
        st = self.win.state(app)
        self.title.setText(app["name"])
        sub = app["id"] if not app.get("description") else f'{app["owner"]}/{app["repo"]} · {app["description"]}'
        self.sub.setText(self.sub.fontMetrics().elidedText(sub, Qt.ElideRight, max(200, self.sub.width())))
        self.sub.setToolTip(app.get("description") or "")
        self.avatar.setPixmap(self.win.avatar(app))

        busy = self.win.busy.get(self.app_id)
        self.progress.setVisible(bool(busy))
        self.button.setVisible(False)
        warn = ""
        if app.get("error"):
            warn = f' <span style="color:{ORANGE}">⚠</span>'
            self.status.setToolTip(tr("check_failed", e=tr_error(app["error"])))
        else:
            self.status.setToolTip("")

        if busy:
            if busy["phase"] == "download":
                self.progress.setRange(0, 100)
                self.progress.setValue(busy["p"])
                text = tr("downloading", p=busy["p"])
            else:
                self.progress.setRange(0, 0)
                text = tr("auto_updating") if busy.get("silent") else tr("installing")
            self.status.setText(f'<span style="color:{ACCENT}">{text}</span>')
            return
        if self.app_id in self.win.in_check and not st["release"]:
            self.status.setText(f'<span style="color:{MUTED}">{tr("checking")}</span>')
            return
        if not st["release"]:
            msg = tr_error(app["error"]) if app.get("error") and not st["has_cache"] else tr(st["reason"])
            self.status.setText(f'<span style="color:{MUTED}">{msg}</span>')
            return
        latest = pretty_version(st["latest"])
        if st["installed"] and st["has_update"]:
            self.status.setText(f'{tr("installed", v=pretty_version(st["installed"]))} · '
                                f'<b style="color:{ORANGE}">{tr("update_to", v=latest)}</b>{warn}')
            if app.get("auto_failed") == st["latest"]:
                self.status.setToolTip(tr("auto_manual"))
            elif self.win.auto_enabled(app):
                self.status.setText(self.status.text() + f' <span style="color:{MUTED}">· ⟳</span>')
            self.button.setText(tr("update"))
            self.set_kind("update")
            self.button.setVisible(True)
        elif st["installed"]:
            self.status.setText(f'{tr("installed", v=pretty_version(st["installed"]))} · '
                                f'<span style="color:{GREEN}">✓ {tr("up_to_date")}</span>{warn}')
        else:
            self.status.setText(f'<span style="color:{MUTED}">{tr("not_installed")} · '
                                f'{tr("latest", v=latest)}</span>{warn}')
            self.button.setText(tr("install"))
            self.set_kind("primary")
            self.button.setVisible(True)

    def build_menu(self):
        m, app = self.menu, self.win.app(self.app_id)
        m.clear()
        if not app:
            return
        st = self.win.state(app)
        busy = self.app_id in self.win.busy
        v = pretty_version(st["latest"]) if st["latest"] else ""
        if st["release"]:
            m.addAction(tr("menu_notes", v=v), lambda: self.win.show_notes(self.app_id))
        m.addAction(tr("menu_github"), lambda: QDesktopServices.openUrl(
            QUrl(app.get("html_url") or f'https://github.com/{app["owner"]}/{app["repo"]}')))
        m.addAction(tr("menu_check"), lambda: self.win.start_check([self.app_id]))
        m.addSeparator()
        if st["release"] and st["installed"] and not st["has_update"]:
            m.addAction(tr("menu_reinstall", v=v), lambda: self.win.install(self.app_id)).setEnabled(not busy)
        if st["release"] and self.app_id != SELF_ID and st["installed"] != st["latest"] and \
                (not st["installed"] or st["has_update"]):
            m.addAction(tr("menu_mark", v=v), lambda: self.win.mark_installed(self.app_id, st["latest"]))
        if app.get("installed_version"):
            m.addAction(tr("menu_forget"), lambda: self.win.mark_installed(self.app_id, None))
        m.addAction(tr("menu_rename"), lambda: self.win.rename(self.app_id))
        pre = QAction(tr("menu_prerelease"), m)
        pre.setCheckable(True)
        pre.setChecked(bool(app.get("prerelease")))
        pre.toggled.connect(lambda on: self.win.set_option(self.app_id, "prerelease", on))
        m.addAction(pre)
        if self.win.cfg.get("auto_update") and self.app_id != SELF_ID:
            auto = QAction(tr("menu_auto"), m)
            auto.setCheckable(True)
            auto.setChecked(app.get("auto_update", True))
            auto.toggled.connect(lambda on: self.win.set_option(self.app_id, "auto_update", on))
            m.addAction(auto)
        m.addAction(tr("menu_pattern"), lambda: self.win.choose_pattern(self.app_id))
        m.addSeparator()
        m.addAction(tr("menu_remove"), lambda: self.win.remove(self.app_id)).setEnabled(not busy)


class SettingsDialog(QDialog):
    INTERVALS = [1, 3, 6, 12, 24]

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.win = win
        cfg = win.cfg
        self.setWindowTitle(tr("settings"))
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        form.setVerticalSpacing(12)
        self.interval = QComboBox()
        for h in self.INTERVALS:
            self.interval.addItem(tr("s_hours", h=h), h)
        self.interval.setCurrentIndex(max(0, self.INTERVALS.index(cfg["interval_hours"])
                                          if cfg["interval_hours"] in self.INTERVALS else 2))
        form.addRow(tr("s_interval"), self.interval)
        self.autostart = QCheckBox(tr("s_autostart"), checked=cfg["autostart"])
        self.notify = QCheckBox(tr("s_notify"), checked=cfg["notify"])
        self.auto = QCheckBox(tr("s_auto"), checked=cfg.get("auto_update", False))
        form.addRow(self.autostart)
        form.addRow(self.notify)
        form.addRow(self.auto)
        auto_help = QLabel(tr("s_auto_help"), objectName="cardSub")
        auto_help.setWordWrap(True)
        form.addRow(auto_help)
        self.lang = QComboBox()
        for code, label in (("auto", tr("s_lang_auto")), ("en", "English"), ("fr", "Français")):
            self.lang.addItem(label, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(cfg.get("language", "auto"))))
        form.addRow(tr("s_language"), self.lang)
        self.token = QLineEdit(win.token())
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("github_pat_…")
        form.addRow(tr("s_token"), self.token)
        help_ = QLabel(tr("s_token_help"), objectName="cardSub")
        help_.setWordWrap(True)
        form.addRow(help_)
        form.addRow(QLabel(tr("s_about", v=__version__), objectName="cardSub"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def apply(self):
        cfg = self.win.cfg
        lang_changed = self.lang.currentData() != cfg.get("language", "auto")
        cfg["interval_hours"] = self.interval.currentData()
        cfg["autostart"] = self.autostart.isChecked()
        cfg["notify"] = self.notify.isChecked()
        auto_turned_on = self.auto.isChecked() and not cfg.get("auto_update")
        cfg["auto_update"] = self.auto.isChecked()
        cfg["language"] = self.lang.currentData()
        token_changed = self.token.text().strip() != self.win.token()
        cfg["token"] = encrypt_secret(self.token.text().strip())
        set_autostart(cfg["autostart"])
        self.win.save()
        if lang_changed:
            QMessageBox.information(self, APP_NAME, tr("s_lang_restart"))
        if token_changed:
            self.win.start_check()
        elif auto_turned_on:
            self.win.run_auto_updates()


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, start_hidden: bool):
        super().__init__()
        self.cfg = cfg
        self.bridge = Bridge()
        self.releases = {a["id"]: load_json(cache_path(a["id"]), None) for a in cfg["apps"]}
        self.cards: dict[str, AppCard] = {}
        self.busy: dict[str, dict] = {}
        self.in_check: set[str] = set()
        self.full_check_running = False
        self.auto_queue: list[str] = []
        self.quitting = False
        self._avatars: dict[str, QPixmap] = {}
        self.base_icon = app_icon()

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(self.base_icon)
        self.resize(760, 620)
        self.setAcceptDrops(True)
        self._build_ui()
        self._build_tray()

        b = self.bridge
        b.checked.connect(self.on_checked)
        b.check_done.connect(self.on_check_done)
        b.added.connect(self.on_added)
        b.add_failed.connect(self.on_add_failed)
        b.progress.connect(self.on_progress)
        b.phase.connect(self.on_phase)
        b.install_done.connect(self.on_install_done)
        b.install_failed.connect(self.on_install_failed)
        b.activate.connect(self.show_window)

        self.refresh_detected()                         # don't show stale versions from the last session
        self.rebuild_cards()
        self.heartbeat = QTimer(self, interval=HEARTBEAT_MS, timeout=self.maybe_check)
        self.heartbeat.start()
        QTimer.singleShot(4000, self.start_check)       # always check shortly after launch
        if not start_hidden or not self.tray:
            self.show()

    # ---------- layout
    def _build_ui(self):
        central = QWidget(objectName="central")
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 14)
        root.setSpacing(14)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self.base_icon.pixmap(44, 44))
        head.addWidget(logo)
        tbox = QVBoxLayout()
        tbox.setSpacing(0)
        tbox.addWidget(QLabel(APP_NAME, objectName="title"))
        tbox.addWidget(QLabel(tr("tagline"), objectName="tagline"))
        head.addLayout(tbox, 1)
        gear = QPushButton("⚙  " + tr("settings"))
        gear.clicked.connect(self.open_settings)
        head.addWidget(gear, 0, Qt.AlignTop)
        root.addLayout(head)

        add_row = QHBoxLayout()
        self.url = QLineEdit(placeholderText=tr("add_placeholder"))
        self.url.returnPressed.connect(self.add_clicked)
        self.add_btn = QPushButton(tr("add"))
        self.add_btn.setProperty("kind", "primary")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self.add_clicked)
        add_row.addWidget(self.url, 1)
        add_row.addWidget(self.add_btn)
        root.addLayout(add_row)

        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cards_box = QWidget(objectName="cards")
        self.cards_lay = QVBoxLayout(self.cards_box)
        self.cards_lay.setContentsMargins(0, 0, 4, 0)
        self.cards_lay.setSpacing(10)
        self.empty = QLabel(tr("empty"), objectName="empty", alignment=Qt.AlignCenter)
        self.cards_lay.addWidget(self.empty)
        self.cards_lay.addStretch(1)
        self.scroll.setWidget(self.cards_box)
        root.addWidget(self.scroll, 1)

        foot = QHBoxLayout()
        self.footer = QLabel(objectName="footer")
        foot.addWidget(self.footer, 1)
        self.check_btn = QPushButton("⟳  " + tr("check_now"))
        self.check_btn.clicked.connect(lambda: self.start_check())
        foot.addWidget(self.check_btn)
        root.addLayout(foot)
        self.setCentralWidget(central)

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.base_icon, self)
        menu = QMenu()
        menu.addAction(tr("tray_open"), self.show_window)
        menu.addAction(tr("check_now"), lambda: self.start_check())
        menu.addSeparator()
        menu.addAction(tr("tray_quit"), self.quit_app)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_window()
                                    if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.messageClicked.connect(self.show_window)
        self.tray.setToolTip(APP_NAME)
        self.tray.show()

    # ---------- data access
    def app(self, app_id):
        return next((a for a in self.cfg["apps"] if a["id"] == app_id), None)

    def token(self) -> str:
        return decrypt_secret(self.cfg.get("token", ""))

    def save(self):
        save_json(CONFIG_FILE, self.cfg)

    def state(self, app: dict) -> dict:
        rels = self.releases.get(app["id"])
        rel, asset, reason = pick_release(rels or [], app.get("prerelease", False), app.get("pattern"))
        # Trust the newest of: what Windows reports, and what Vedware itself installed.
        found = [v for v in (app.get("detected"), app.get("installed_version")) if v]
        installed = max(found, key=lambda v: parse_version(v) or ((), 0, 0, 0)) if found else None
        latest = rel["tag_name"] if rel else None
        return {"release": rel, "asset": asset, "reason": reason, "installed": installed,
                "latest": latest, "has_cache": rels is not None,
                "has_update": bool(rel and installed and is_newer(latest, installed))}

    def avatar(self, app) -> QPixmap:
        key = app["owner"].lower()
        if key not in self._avatars:
            f = AVATAR_DIR / f"{safe_name(key)}.png"
            pm = QPixmap(str(f)) if f.exists() else QPixmap()
            if pm.isNull():
                return letter_pixmap(app["name"] or "?", 48, "#94a3b8")
            self._avatars[key] = rounded(pm, 48)
        return self._avatars[key]

    def refresh_detected(self):
        """Re-read Apps & features (local, fast): picks up updates made outside Vedware."""
        reg = registry_entries()
        for a in self.cfg["apps"]:
            a["detected"] = detect_installed(a, reg)

    def updates(self) -> list:
        return [a for a in self.cfg["apps"] if self.state(a)["has_update"]]

    # ---------- list
    def sort_key(self, app):
        st = self.state(app)
        rank = 0 if st["has_update"] else 1 if st["installed"] else 2 if st["release"] else 3
        return rank, app["name"].lower()

    def rebuild_cards(self):
        for c in self.cards.values():
            c.setParent(None)
            c.deleteLater()
        self.cards.clear()
        apps = sorted(self.cfg["apps"], key=self.sort_key)
        for i, a in enumerate(apps):
            card = AppCard(self, a["id"])
            self.cards[a["id"]] = card
            self.cards_lay.insertWidget(i, card)
            card.refresh()
        self.empty.setVisible(not apps)
        self.update_summary()

    def refresh_card(self, app_id):
        if app_id in self.cards:
            self.cards[app_id].refresh()

    def update_summary(self):
        n = len(self.updates())
        text = tr("checking_all") if self.full_check_running else fmt_time(self.cfg.get("last_check"))
        if n:
            text += "  ·  " + tr("n_updates", n=n)
        self.footer.setText(text)
        self.check_btn.setEnabled(not self.full_check_running)
        if self.tray:
            self.tray.setIcon(badge_icon(self.base_icon, n))
            self.tray.setToolTip(f"{APP_NAME} — {tr('n_updates', n=n)}" if n else APP_NAME)

    def highlight(self, app_id):
        card = self.cards.get(app_id)
        if not card:
            return
        self.scroll.ensureWidgetVisible(card)
        card.setProperty("highlight", "true")
        card.style().polish(card)
        QTimer.singleShot(1800, lambda: self._unhighlight(app_id))

    def _unhighlight(self, app_id):
        card = self.cards.get(app_id)
        if card:
            card.setProperty("highlight", "false")
            card.style().polish(card)

    # ---------- adding
    def add_clicked(self):
        self.add_from_text(self.url.text())

    def add_from_text(self, text):
        parsed = parse_repo(text)
        if not parsed:
            QMessageBox.warning(self, APP_NAME, tr("invalid_url"))
            return
        owner, repo = parsed
        existing = self.app(f"{owner}/{repo}".lower())
        if existing:
            self.url.clear()
            self.highlight(existing["id"])
            QMessageBox.information(self, APP_NAME, tr("already", n=existing["name"]))
            return
        self.add_btn.setEnabled(False)
        self.add_btn.setText(tr("adding"))
        token = self.token()

        def work():
            try:
                info = fetch_repo_info(owner, repo, token)
                o, r = info["full_name"].split("/", 1)
                self.bridge.added.emit(o, r, info)
            except GitHubError as e:
                self.bridge.add_failed.emit(str(e))
        threading.Thread(target=work, daemon=True).start()

    def on_added(self, owner, repo, info):
        self.add_btn.setEnabled(True)
        self.add_btn.setText(tr("add"))
        self.url.clear()
        app = new_app(owner, repo, {k: info[k] for k in ("description", "html_url", "avatar_url")})
        if self.app(app["id"]):
            self.highlight(app["id"])
            return
        self.cfg["apps"].append(app)
        self.releases[app["id"]] = None
        self.save()
        self.rebuild_cards()
        self.highlight(app["id"])
        self.start_check([app["id"]])

    def on_add_failed(self, err):
        self.add_btn.setEnabled(True)
        self.add_btn.setText(tr("add"))
        QMessageBox.warning(self, APP_NAME, tr_error(err))

    def dragEnterEvent(self, e):
        if e.mimeData().hasText() or e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        text = md.urls()[0].toString() if md.hasUrls() else md.text()
        self.url.setText(text.strip())
        self.add_from_text(text)

    # ---------- checking
    def maybe_check(self):
        last = self.cfg.get("last_check") or 0
        if now_ts() - last >= self.cfg["interval_hours"] * 3600:
            self.start_check()

    def start_check(self, ids=None):
        full = ids is None
        if full and self.full_check_running:
            return
        apps = [dict(a) for a in self.cfg["apps"] if full or a["id"] in ids]
        if full:
            self.full_check_running = True
        for a in apps:
            self.in_check.add(a["id"])
            self.refresh_card(a["id"])
        self.update_summary()
        token = self.token()
        has_cache = {a["id"]: self.releases.get(a["id"]) is not None for a in apps}

        def work():
            reg = registry_entries()
            for a in apps:
                self.bridge.checked.emit(a["id"], check_app(a, token, reg, has_cache[a["id"]]))
            self.bridge.check_done.emit(full)
        threading.Thread(target=work, daemon=True).start()

    def on_checked(self, app_id, res):
        self.in_check.discard(app_id)
        app = self.app(app_id)
        if not app:
            return
        if res.get("info"):
            app.update({k: res["info"][k] for k in ("description", "html_url", "avatar_url")})
        if res.get("avatar"):
            self._avatars.pop(app["owner"].lower(), None)
        app["error"] = res["error"]
        app["detected"] = res["detected"]
        app["last_checked"] = res["checked_at"]
        if not res["error"]:
            app["etag"] = res.get("etag")
        if res["releases"] is not None:
            self.releases[app_id] = res["releases"]
            save_json(cache_path(app_id), res["releases"])
        self.refresh_card(app_id)

    def on_check_done(self, full):
        if full:
            self.full_check_running = False
            self.cfg["last_check"] = now_ts()
        self.save()
        self.rebuild_cards()
        self.run_auto_updates()
        self.notify_updates()

    # ---------- automatic updates
    def auto_enabled(self, app) -> bool:
        return bool(self.cfg.get("auto_update") and (app.get("auto_update", True) or app["id"] == SELF_ID))

    def auto_candidates(self) -> list:
        out = []
        for a in self.updates():
            latest = self.state(a)["latest"]
            if not self.auto_enabled(a) or a.get("auto_failed") == latest or a["id"] in self.busy:
                continue
            if a["id"] == SELF_ID and self.isVisible():
                continue                       # don't close Vedware under the user's eyes
            out.append(a["id"])
        out.sort(key=lambda i: i == SELF_ID)   # Vedware itself last: it restarts
        return out

    def run_auto_updates(self):
        for app_id in self.auto_candidates():
            if app_id not in self.auto_queue:
                self.auto_queue.append(app_id)
        self.next_auto_update()

    def next_auto_update(self):
        if any(b.get("silent") for b in self.busy.values()):
            return                             # one unattended install at a time
        while self.auto_queue:
            app_id = self.auto_queue.pop(0)
            app = self.app(app_id)
            if app and self.state(app)["has_update"] and app_id not in self.busy:
                self.install(app_id, silent=True)
                return

    def notify_updates(self):
        due = []
        pending = set(self.auto_queue) | {i for i, b in self.busy.items() if b.get("silent")}
        for a in self.updates():
            if a["id"] in pending:
                continue
            latest = self.state(a)["latest"]
            n = a.get("notified") or {}
            if n.get("v") != latest or now_ts() - n.get("at", 0) > REMIND_AFTER_S:
                due.append((a, latest))
        if not due or not self.cfg.get("notify", True) or not self.tray:
            return
        for a, latest in due:
            a["notified"] = {"v": latest, "at": now_ts()}
        self.save()
        if len(due) == 1:
            a, latest = due[0]
            self.tray.showMessage(tr("notif_one", n=a["name"], v=pretty_version(latest)),
                                  tr("notif_one_body"), self.base_icon, 10000)
        else:
            body = ", ".join(f'{a["name"]} {pretty_version(v)}' for a, v in due)
            self.tray.showMessage(tr("notif_many", c=len(due)), body, self.base_icon, 10000)

    # ---------- installing
    def install(self, app_id, silent=False):
        app = self.app(app_id)
        if not app or app_id in self.busy:
            return
        st = self.state(app)
        if not st["asset"]:
            return
        rel, asset = st["release"], st["asset"]
        self.busy[app_id] = {"phase": "download", "p": 0, "silent": silent}
        self.refresh_card(app_id)
        token = self.token()
        snapshot = dict(app)

        def work():
            try:
                dest = DOWNLOAD_DIR / safe_name(app_id.replace("/", "__")) / asset["name"]
                download_file(asset, dest, token, lambda p: self.bridge.progress.emit(app_id, p))
                self.bridge.phase.emit(app_id, "install")
                result = {"tag": rel["tag_name"], "kind": "installer"}
                if dest.suffix.lower() == ".zip":
                    folder = PORTABLE_DIR / safe_name(snapshot["repo"])
                    shutil.rmtree(folder, ignore_errors=True)
                    with zipfile.ZipFile(dest) as z:
                        z.extractall(folder)
                    result.update(kind="zip", folder=str(folder))
                elif app_id == SELF_ID:
                    launch_detached(dest, SILENT_ARGS["inno"] if silent else "")
                    result["kind"] = "self"
                elif silent:
                    cmd = silent_command(dest)
                    if not cmd:
                        raise NeedsManualInstall()
                    result["exit"] = run_installer_and_wait(dest, params=cmd[1], file=cmd[0])
                    result["detected"] = detect_installed(snapshot, registry_entries())
                else:
                    result["exit"] = run_installer_and_wait(dest)
                    result["detected"] = detect_installed(snapshot, registry_entries())
                self.bridge.install_done.emit(app_id, result)
            except InstallCancelled:
                self.bridge.install_failed.emit(app_id, "cancelled")
            except NeedsManualInstall:
                self.bridge.install_failed.emit(app_id, "manual")
            except GitHubError as e:
                self.bridge.install_failed.emit(app_id, str(e))
            except Exception as e:  # noqa: BLE001 — surface anything to the user
                self.bridge.install_failed.emit(app_id, str(e) or e.__class__.__name__)
        threading.Thread(target=work, daemon=True).start()

    def on_progress(self, app_id, p):
        if app_id in self.busy:
            self.busy[app_id]["p"] = p
            self.refresh_card(app_id)

    def on_phase(self, app_id, phase):
        if app_id in self.busy:
            self.busy[app_id]["phase"] = phase
            self.refresh_card(app_id)

    def on_install_done(self, app_id, res):
        silent = (self.busy.pop(app_id, None) or {}).get("silent", False)
        app = self.app(app_id)
        if not app:
            self.next_auto_update()
            return
        if res["kind"] == "self":
            if self.tray:
                self.tray.showMessage(APP_NAME, tr("self_update"), self.base_icon, 4000)
            QTimer.singleShot(1500, self.quit_app)
            return
        ok = True
        if res["kind"] == "zip":
            app["installed_version"] = res["tag"]
            if not silent:
                open_path(Path(res["folder"]))
        else:
            app["detected"] = res.get("detected")
            code = res.get("exit")
            if code in (0, None, 1641, 3010):          # 1641/3010 = success, reboot needed
                app["installed_version"] = res["tag"]
            elif not app["detected"] or is_newer(res["tag"], app["detected"]):
                ok = False
        if not ok:
            if silent:
                self.auto_failed(app, res["tag"])
            else:
                QMessageBox.warning(self, APP_NAME, tr("install_failed", n=app["name"],
                                                       e=tr("err_exit_code", c=res.get("exit"))))
        else:
            app["notified"] = None
            app["auto_failed"] = None
        self.save()
        self.rebuild_cards()
        if ok and self.tray:
            key = "notif_updated" if silent else "notif_installed"
            self.tray.showMessage(tr(key, n=app["name"], v=pretty_version(res["tag"])),
                                  "", self.base_icon, 5000)
        self.next_auto_update()

    def auto_failed(self, app, version):
        """An unattended update didn't work: don't retry this version, ask the user instead."""
        app["auto_failed"] = version
        app["notified"] = {"v": version, "at": now_ts()}
        self.save()
        self.rebuild_cards()
        if self.tray and self.cfg.get("notify", True):
            self.tray.showMessage(tr("notif_auto_failed", n=app["name"], v=pretty_version(version)),
                                  tr("notif_auto_failed_body"), self.base_icon, 10000)

    def on_install_failed(self, app_id, err):
        silent = (self.busy.pop(app_id, None) or {}).get("silent", False)
        self.refresh_card(app_id)
        app = self.app(app_id)
        if silent:
            if app:
                self.auto_failed(app, self.state(app)["latest"])
            self.next_auto_update()
            return
        if err == "cancelled":
            return
        QMessageBox.warning(self, APP_NAME, tr("install_failed", n=app["name"] if app else app_id,
                                               e=tr_error(err)))

    # ---------- per-app actions
    def mark_installed(self, app_id, version):
        app = self.app(app_id)
        app["installed_version"] = version
        if version is None:
            app["detected"] = None
        self.save()
        self.rebuild_cards()

    def set_option(self, app_id, key, value):
        self.app(app_id)[key] = value
        self.save()
        self.rebuild_cards()

    def rename(self, app_id):
        app = self.app(app_id)
        name, ok = QInputDialog.getText(self, tr("rename_title"), tr("rename_label"), text=app["name"])
        if ok and name.strip():
            self.set_option(app_id, "name", name.strip())

    def choose_pattern(self, app_id):
        app = self.app(app_id)
        rels = [r for r in self.releases.get(app_id) or []
                if not r.get("draft") and (app.get("prerelease") or not r.get("prerelease"))]
        names = [a["name"] for a in (rels[0]["assets"] if rels else [])]
        items = [tr("pattern_auto")] + names
        current = 0
        if app.get("pattern"):
            current = next((i + 1 for i, n in enumerate(names)
                            if fnmatch.fnmatch(n.lower(), app["pattern"].lower())), 0)
        choice, ok = QInputDialog.getItem(self, tr("pattern_title"), tr("pattern_label"), items, current, False)
        if ok:
            self.set_option(app_id, "pattern", None if choice == items[0] else pattern_from_name(choice))

    def remove(self, app_id):
        app = self.app(app_id)
        if QMessageBox.question(self, APP_NAME, tr("remove_confirm", n=app["name"])) != QMessageBox.Yes:
            return
        self.cfg["apps"].remove(app)
        self.releases.pop(app_id, None)
        cache_path(app_id).unlink(missing_ok=True)
        self.save()
        self.rebuild_cards()

    def show_notes(self, app_id):
        app = self.app(app_id)
        rel = self.state(app)["release"]
        dlg = QDialog(self)
        dlg.setWindowTitle(f'{app["name"]} {pretty_version(rel["tag_name"])}')
        dlg.resize(620, 520)
        lay = QVBoxLayout(dlg)
        date = (rel.get("published_at") or "")[:10]
        lay.addWidget(QLabel(f'<b style="font-size:13pt">{rel.get("name") or rel["tag_name"]}</b>'
                             f'<br><span style="color:{MUTED}">{date}</span>'))
        tb = QTextBrowser(openExternalLinks=True)
        tb.setMarkdown(rel.get("body") or "—")
        lay.addWidget(tb, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()

    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            dlg.apply()
            self.update_summary()

    # ---------- window / tray
    def show_window(self):
        reopened = not self.isVisible() or self.isMinimized()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if reopened:                                    # back from the tray: show fresh state
            self.refresh_detected()
            self.rebuild_cards()
            if now_ts() - (self.cfg.get("last_check") or 0) >= RECHECK_ON_OPEN_S:
                self.start_check()

    def closeEvent(self, e):
        if self.quitting or not self.tray:
            self.quitting = True
            e.accept()
            QApplication.quit()
            return
        e.ignore()
        self.hide()
        if not self.cfg.get("tray_hint_shown"):
            self.cfg["tray_hint_shown"] = True
            self.save()
            self.tray.showMessage(APP_NAME, tr("tray_hint"), self.base_icon, 6000)

    def quit_app(self):
        self.quitting = True
        self.save()
        if self.tray:
            self.tray.hide()
        QApplication.quit()


# --------------------------------------------------------------------------- entry point
def load_config() -> dict:
    cfg = load_json(CONFIG_FILE, None)
    if not isinstance(cfg, dict):
        cfg = default_config()
    base = default_config()
    base["apps"] = []
    for k, v in base.items():
        cfg.setdefault(k, v)
    for a in cfg["apps"]:
        for k, v in new_app(a["owner"], a["repo"]).items():
            a.setdefault(k, v)
    return cfg


def main():
    global LANG
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Vedware.Vedware")
        except Exception:
            pass
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)

    server_name = f"vedware-{safe_name(getpass.getuser())}"
    sock = QLocalSocket()
    sock.connectToServer(server_name)
    if sock.waitForConnected(400):                 # already running → bring it to front
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(400)
        return 0

    cfg = load_config()
    lang = cfg.get("language", "auto")
    LANG = lang if lang in ("en", "fr") else ("fr" if QLocale.system().name().lower().startswith("fr") else "en")
    qapp.setStyleSheet(STYLE)
    set_autostart(cfg["autostart"])                # keep the Run key in sync with the setting

    win = MainWindow(cfg, start_hidden="--minimized" in sys.argv)
    win.save()

    server = QLocalServer()
    QLocalServer.removeServer(server_name)
    server.listen(server_name)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.bridge.activate.emit()))
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
