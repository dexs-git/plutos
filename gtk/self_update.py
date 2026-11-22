"""Aktualisiert Plutos selbst – über die öffentlichen GitHub-Releases.

Je nach Installationsart:
  * Quellcode-Installation (Linux-/macOS-/Windows-Installationsskripte, GTK und Qt):
    die Programmdateien des Release-Tags werden von GitHub geladen, geprüft und
    ersetzt; Plutos startet danach neu. Die vorherigen Dateien bleiben im Ordner
    ``.update-backup`` neben dem Programm liegen.
  * AppImage (Linux): die neue AppImage-Datei ersetzt die laufende.
  * Windows-Installer: das neue Setup wird geladen und gestartet.
  * macOS-dmg: das neue dmg wird in „Downloads“ gespeichert und geöffnet
    (die App selbst muss in Programme gezogen werden).
  * Alles andere: nur Hinweis auf die Download-Seite.

Es werden nur Dateien von github.com geladen; die Datenbank wird nie angefasst.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

REPO = "dexs-git/plutos"
MAX_BYTES = 300 * 1024 * 1024
BACKUP_DIR = ".update-backup"


class UpdateError(Exception):
    """Fehler mit lesbarer (deutscher) Meldung."""


def app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def variant():
    """"qt" oder "gtk" – je nachdem, welche Oberfläche läuft."""
    return "qt" if "PySide6" in sys.modules else "gtk"


def detect_mode(directory=None, environ=None, frozen=None, platform=None):
    """Wie wurde Plutos installiert? -> appimage | windows-setup | macos-dmg | source | manual"""
    environ = os.environ if environ is None else environ
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    platform = sys.platform if platform is None else platform
    if environ.get("APPIMAGE") and os.path.isfile(environ["APPIMAGE"]):
        return "appimage"
    if frozen:
        if platform == "win32":
            return "windows-setup"
        if platform == "darwin":
            return "macos-dmg"
        return "manual"
    directory = directory or app_dir()
    if os.path.isfile(os.path.join(directory, "main.py")) and os.access(directory, os.W_OK):
        return "source"
    return "manual"


def find_asset(assets, mode):
    """Passende Release-Datei für die Installationsart (oder None)."""
    patterns = {"appimage": r"\.AppImage$", "windows-setup": r"-Setup\.exe$",
                "macos-dmg": r"\.dmg$"}
    pattern = patterns.get(mode)
    if not pattern:
        return None
    for asset in assets or []:
        if re.search(pattern, asset.get("name", ""), re.I):
            return asset
    return None


def can_self_update(release, mode=None):
    mode = mode or detect_mode()
    if mode == "source":
        return True
    return bool(find_asset(release.get("assets"), mode))


def _open(url, opener=None, timeout=30):
    if not url.startswith("https://"):
        raise UpdateError("Nur HTTPS-Adressen werden geladen")
    request = urllib.request.Request(url, headers={"User-Agent": "Plutos"})
    return (opener or urllib.request.urlopen)(request, timeout=timeout)


def download(url, dest, progress=None, opener=None):
    """Lädt url nach dest (Fortschritt: progress(bytes_gelesen, gesamt_oder_0))."""
    try:
        with _open(url, opener) as response:
            headers = getattr(response, "headers", None)
            total = int(headers.get("Content-Length", 0) or 0) if headers else 0
            if total > MAX_BYTES:
                raise UpdateError("Die Datei ist ungewöhnlich groß – Abbruch")
            done = 0
            with open(dest, "wb") as out:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > MAX_BYTES:
                        raise UpdateError("Die Datei ist ungewöhnlich groß – Abbruch")
                    out.write(chunk)
                    if progress:
                        progress(done, total)
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f"Download fehlgeschlagen: {exc}") from exc


def _stamp_version(source, tag):
    version = tag.lstrip("vV")
    stamped, n = re.subn(r'(?m)^APP_VERSION = .*$', f'APP_VERSION = "{version}"', source)
    return stamped if n else source + f'\nAPP_VERSION = "{version}"\n'


def read_source_files(archive_path, flavor):
    """Liest die .py-Dateien des Ordners ``<flavor>/`` aus dem GitHub-Tarball."""
    files = {}
    try:
        with tarfile.open(archive_path, "r:*") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                parts = member.name.split("/")
                # <repo-tag>/<flavor>/<datei>.py
                if len(parts) == 3 and parts[1] == flavor and parts[2].endswith(".py") \
                        and not parts[2].startswith("."):
                    files[parts[2]] = tar.extractfile(member).read().decode("utf-8")
    except (tarfile.TarError, OSError, UnicodeDecodeError) as exc:
        raise UpdateError(f"Das heruntergeladene Paket ist unlesbar: {exc}") from exc
    return files


def apply_source_files(files, tag, directory):
    """Prüft (Syntax) und ersetzt die Programmdateien; bei Fehlern Rückbau."""
    for needed in ("main.py", "db.py", "version.py"):
        if needed not in files:
            raise UpdateError(f"Im Paket fehlt {needed} – Update abgebrochen")
    files = dict(files)
    files["version.py"] = _stamp_version(files["version.py"], tag)
    for name, source in files.items():
        try:
            compile(source, name, "exec")
        except SyntaxError as exc:
            raise UpdateError(f"{name} ist fehlerhaft ({exc.msg}) – Update abgebrochen") from exc

    backup = os.path.join(directory, BACKUP_DIR)
    shutil.rmtree(backup, ignore_errors=True)
    os.makedirs(backup)
    touched = []
    try:
        for name in files:
            target = os.path.join(directory, name)
            if os.path.isfile(target):
                shutil.copy2(target, os.path.join(backup, name))
        for name, source in files.items():
            target = os.path.join(directory, name)
            tmp = target + ".new"
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(source)
            os.replace(tmp, target)
            touched.append(name)
    except Exception as exc:
        for name in touched:
            saved = os.path.join(backup, name)
            if os.path.isfile(saved):
                shutil.copy2(saved, os.path.join(directory, name))
            else:
                try:
                    os.remove(os.path.join(directory, name))
                except OSError:
                    pass
        raise UpdateError(f"Dateien konnten nicht ersetzt werden: {exc}") from exc
    return sorted(files)


def update_source(release, flavor=None, directory=None, progress=None, opener=None):
    tag = release["tag"]
    if not re.fullmatch(r"v?\d+(\.\d+){0,3}", tag):
        raise UpdateError("Unerwartete Versionsbezeichnung")
    flavor = flavor or variant()
    directory = directory or app_dir()
    with tempfile.TemporaryDirectory(prefix="plutos-update-") as tmp:
        archive = os.path.join(tmp, "source.tar.gz")
        download(f"https://github.com/{REPO}/archive/refs/tags/{tag}.tar.gz",
                 archive, progress, opener)
        files = read_source_files(archive, flavor)
        names = apply_source_files(files, tag, directory)
    return {"restart": True, "files": names}


def update_appimage(release, progress=None, opener=None, environ=None):
    environ = os.environ if environ is None else environ
    asset = find_asset(release.get("assets"), "appimage")
    if not asset:
        raise UpdateError("Im Release gibt es keine AppImage-Datei")
    target = environ["APPIMAGE"]
    tmp = target + ".new"
    try:
        download(asset["url"], tmp, progress, opener)
        os.chmod(tmp, 0o755)
        os.replace(tmp, target)
    except OSError as exc:
        raise UpdateError(f"AppImage konnte nicht ersetzt werden: {exc}") from exc
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return {"restart": True, "restart_command": [target]}


def update_windows(release, progress=None, opener=None):
    asset = find_asset(release.get("assets"), "windows-setup")
    if not asset:
        raise UpdateError("Im Release gibt es keinen Windows-Installer")
    dest = os.path.join(tempfile.gettempdir(), asset["name"])
    download(asset["url"], dest, progress, opener)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([dest, "/SILENT", "/CLOSEAPPLICATIONS"], creationflags=flags, close_fds=True)
    return {"restart": False, "quit": True}


def update_macos(release, progress=None, opener=None):
    asset = find_asset(release.get("assets"), "macos-dmg")
    if not asset:
        raise UpdateError("Im Release gibt es keine dmg-Datei")
    folder = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, asset["name"])
    download(asset["url"], dest, progress, opener)
    subprocess.Popen(["open", dest])
    return {"restart": False, "manual": dest}


def apply_update(release, progress=None, opener=None):
    """Führt das Update für die erkannte Installationsart aus.
    Ergebnis: {"mode": …, "restart": bool, …}; Fehler als UpdateError."""
    mode = detect_mode()
    if mode == "source":
        result = update_source(release, progress=progress, opener=opener)
    elif mode == "appimage":
        result = update_appimage(release, progress=progress, opener=opener)
    elif mode == "windows-setup":
        result = update_windows(release, progress=progress, opener=opener)
    elif mode == "macos-dmg":
        result = update_macos(release, progress=progress, opener=opener)
    else:
        raise UpdateError("Diese Installation kann sich nicht selbst aktualisieren")
    result["mode"] = mode
    return result


def restart_command(result=None):
    if result and result.get("restart_command"):
        return list(result["restart_command"])
    if getattr(sys, "frozen", False):
        return [sys.executable] + sys.argv[1:]
    return [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:]


def restart(result=None):
    """Startet Plutos neu (der Aufrufer beendet danach die laufende Instanz)."""
    cwd = app_dir() if not getattr(sys, "frozen", False) else None
    subprocess.Popen(restart_command(result), cwd=cwd, close_fds=True)
