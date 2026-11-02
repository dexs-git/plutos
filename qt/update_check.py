"""Prüft beim Start (im Hintergrund), ob auf GitHub eine neuere Version von
Plutos veröffentlicht wurde. Es wird nur die öffentliche Release-Information
abgefragt (https://api.github.com/repos/dexs-git/plutos/releases/latest);
es werden keine Daten übertragen. Jeder Fehler (kein Netz, Rate-Limit, …) wird
still ignoriert. Abschaltbar im Tab „Export / Import“."""
import json
import re
import urllib.request

REPO = "dexs-git/plutos"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"


def parse_version(text):
    """'v1.2.10' / '1.2' -> (1, 2, 10); nicht lesbar -> None."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+){0,3})", str(text or ""))
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def fetch_latest(timeout=4.0, opener=None):
    """Liest den neuesten Release; gibt {"tag": "v1.2.0", "url": …} oder None zurück."""
    try:
        request = urllib.request.Request(
            API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "Plutos"})
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        tag = str(data.get("tag_name") or "")
        if not tag or data.get("draft") or data.get("prerelease"):
            return None
        return {"tag": tag, "url": data.get("html_url") or RELEASES_URL}
    except Exception:
        return None


def check_for_update(current_version, skipped_tag="", timeout=4.0, opener=None):
    """Neuerer, nicht übersprungener Release oder None."""
    latest = fetch_latest(timeout, opener)
    if not latest or latest["tag"] == skipped_tag:
        return None
    return latest if is_newer(latest["tag"], current_version) else None
