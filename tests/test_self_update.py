"""Tests für self_update.py (kein echter Netzwerkzugriff)."""
import importlib.util
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(variant):
    spec = importlib.util.spec_from_file_location(f"su_{variant}", ROOT / variant / "self_update.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["gtk", "qt"])
def su(request):
    return _load(request.param)


def _tarball(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in entries.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _Resp(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(payload, seen=None):
    def opener(request, timeout=None):
        if seen is not None:
            seen.append(request.full_url)
        return _Resp(payload)
    return opener


GOOD = {
    "plutos-1.3.0/qt/main.py": "print('neu')\n",
    "plutos-1.3.0/qt/db.py": "X = 2\n",
    "plutos-1.3.0/qt/version.py": 'APP_VERSION = "1.2.0"\n',
    "plutos-1.3.0/qt/extra.py": "Y = 1\n",
    "plutos-1.3.0/gtk/main.py": "print('gtk')\n",
    "plutos-1.3.0/qt/sub/evil.py": "boom\n",
    "plutos-1.3.0/README.md": "x",
}


def test_identical_copies():
    assert (ROOT / "gtk" / "self_update.py").read_text() == (ROOT / "qt" / "self_update.py").read_text()


def test_source_update_replaces_and_stamps_version(su, tmp_path):
    (tmp_path / "main.py").write_text("print('alt')\n")
    (tmp_path / "db.py").write_text("X = 1\n")
    (tmp_path / "version.py").write_text('APP_VERSION = "1.2.0"\n')
    seen = []
    res = su.update_source({"tag": "v1.3.0"}, flavor="qt", directory=str(tmp_path),
                           opener=_opener(_tarball(GOOD), seen))
    assert res["restart"] and sorted(res["files"]) == ["db.py", "extra.py", "main.py", "version.py"]
    assert seen == ["https://github.com/dexs-git/plutos/archive/refs/tags/v1.3.0.tar.gz"]
    assert (tmp_path / "main.py").read_text() == "print('neu')\n"
    assert 'APP_VERSION = "1.3.0"' in (tmp_path / "version.py").read_text()
    assert (tmp_path / "extra.py").exists() and not (tmp_path / "sub").exists()
    assert (tmp_path / ".update-backup" / "main.py").read_text() == "print('alt')\n"
    assert not list(tmp_path.glob("*.new"))


def test_source_update_other_flavor(su, tmp_path):
    entries = dict(GOOD)
    entries.update({"plutos-1.3.0/gtk/db.py": "G = 1\n", "plutos-1.3.0/gtk/version.py": 'APP_VERSION = "x"\n'})
    su.update_source({"tag": "v1.3.0"}, flavor="gtk", directory=str(tmp_path),
                     opener=_opener(_tarball(entries)))
    assert (tmp_path / "main.py").read_text() == "print('gtk')\n"
    assert not (tmp_path / "extra.py").exists()


def test_broken_package_changes_nothing(su, tmp_path):
    (tmp_path / "main.py").write_text("print('alt')\n")
    broken = dict(GOOD)
    broken["plutos-1.3.0/qt/db.py"] = "def (:\n"
    with pytest.raises(su.UpdateError):
        su.update_source({"tag": "v1.3.0"}, flavor="qt", directory=str(tmp_path),
                         opener=_opener(_tarball(broken)))
    assert (tmp_path / "main.py").read_text() == "print('alt')\n"
    incomplete = {k: v for k, v in GOOD.items() if not k.endswith("qt/db.py")}
    with pytest.raises(su.UpdateError):
        su.update_source({"tag": "v1.3.0"}, flavor="qt", directory=str(tmp_path),
                         opener=_opener(_tarball(incomplete)))
    with pytest.raises(su.UpdateError):
        su.update_source({"tag": "../../evil"}, flavor="qt", directory=str(tmp_path),
                         opener=_opener(b""))


def test_rollback_on_write_error(su, tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("print('alt')\n")
    (tmp_path / "db.py").write_text("X = 1\n")
    real = os.replace
    calls = {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("Platte voll")
        return real(a, b)
    monkeypatch.setattr(su.os, "replace", flaky)
    with pytest.raises(su.UpdateError):
        su.update_source({"tag": "v1.3.0"}, flavor="qt", directory=str(tmp_path),
                         opener=_opener(_tarball(GOOD)))
    assert (tmp_path / "main.py").read_text() == "print('alt')\n"
    assert (tmp_path / "db.py").read_text() == "X = 1\n"


def test_detect_mode_and_assets(su, tmp_path):
    (tmp_path / "main.py").write_text("")
    assert su.detect_mode(str(tmp_path), environ={}, frozen=False, platform="linux") == "source"
    assert su.detect_mode(str(tmp_path), environ={}, frozen=True, platform="win32") == "windows-setup"
    assert su.detect_mode(str(tmp_path), environ={}, frozen=True, platform="darwin") == "macos-dmg"
    image = tmp_path / "Plutos.AppImage"
    image.write_text("x")
    assert su.detect_mode(str(tmp_path), environ={"APPIMAGE": str(image)}, frozen=True,
                          platform="linux") == "appimage"
    assert su.detect_mode(str(tmp_path / "nix"), environ={}, frozen=False, platform="linux") == "manual"
    assets = [{"name": "Plutos-v1.3.0-x86_64.AppImage", "url": "u1"},
              {"name": "Plutos-v1.3.0-Setup.exe", "url": "u2"},
              {"name": "Plutos-v1.3.0-macOS-arm64.dmg", "url": "u3"}]
    assert su.find_asset(assets, "appimage")["url"] == "u1"
    assert su.find_asset(assets, "windows-setup")["url"] == "u2"
    assert su.find_asset(assets, "macos-dmg")["url"] == "u3"
    assert su.find_asset([], "appimage") is None and su.find_asset(assets, "source") is None


def test_appimage_update_replaces_file(su, tmp_path):
    image = tmp_path / "Plutos.AppImage"
    image.write_bytes(b"alt")
    rel = {"tag": "v1.3.0", "assets": [{"name": "Plutos-v1.3.0.AppImage", "url": "https://x/y"}]}
    res = su.update_appimage(rel, opener=_opener(b"neu"), environ={"APPIMAGE": str(image)})
    assert image.read_bytes() == b"neu" and os.access(image, os.X_OK)
    assert res["restart_command"] == [str(image)] and not (tmp_path / "Plutos.AppImage.new").exists()
    with pytest.raises(su.UpdateError):
        su.update_appimage({"assets": []}, environ={"APPIMAGE": str(image)})


def test_only_https_and_download_errors(su, tmp_path):
    with pytest.raises(su.UpdateError):
        su.download("http://example.com/x", str(tmp_path / "x"))

    def boom(request, timeout=None):
        raise OSError("kein Netz")
    with pytest.raises(su.UpdateError):
        su.download("https://example.com/x", str(tmp_path / "x"), opener=boom)


def test_can_self_update(su):
    assert su.can_self_update({"assets": []}, mode="source")
    assert not su.can_self_update({"assets": []}, mode="windows-setup")
    assert su.can_self_update({"assets": [{"name": "a-Setup.exe", "url": "u"}]}, mode="windows-setup")
    assert not su.can_self_update({"assets": []}, mode="manual")


def test_windows_update_downloads_and_starts_installer(su, tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(su.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    monkeypatch.setattr(su.tempfile, "gettempdir", lambda: str(tmp_path))
    rel = {"tag": "v1.3.0", "assets": [{"name": "Plutos-v1.3.0-Setup.exe", "url": "https://x/s.exe"}]}
    res = su.update_windows(rel, opener=_opener(b"MZ-installer"))
    assert res == {"restart": False, "quit": True}
    assert (tmp_path / "Plutos-v1.3.0-Setup.exe").read_bytes() == b"MZ-installer"
    assert started[0][0].endswith("Plutos-v1.3.0-Setup.exe") and "/SILENT" in started[0]
    with pytest.raises(su.UpdateError):
        su.update_windows({"assets": []})


def test_macos_update_saves_dmg_and_opens_it(su, tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(su.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    monkeypatch.setattr(su.os.path, "expanduser", lambda p: str(tmp_path))
    rel = {"tag": "v1.3.0", "assets": [{"name": "Plutos-v1.3.0-macOS-arm64.dmg", "url": "https://x/p.dmg"}]}
    res = su.update_macos(rel, opener=_opener(b"dmg"))
    dest = tmp_path / "Downloads" / "Plutos-v1.3.0-macOS-arm64.dmg"
    assert dest.read_bytes() == b"dmg" and res["manual"] == str(dest)
    assert started == [["open", str(dest)]]


def test_apply_update_dispatch_and_restart_command(su, tmp_path, monkeypatch):
    monkeypatch.setattr(su, "detect_mode", lambda *a, **k: "manual")
    with pytest.raises(su.UpdateError):
        su.apply_update({"tag": "v1.3.0"})
    monkeypatch.setattr(su, "detect_mode", lambda *a, **k: "source")
    monkeypatch.setattr(su, "update_source", lambda rel, **k: {"restart": True, "files": []})
    assert su.apply_update({"tag": "v1.3.0"})["mode"] == "source"
    assert su.restart_command({"restart_command": ["/x/Plutos.AppImage"]}) == ["/x/Plutos.AppImage"]
    assert su.restart_command()[0] == su.sys.executable
