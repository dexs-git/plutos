"""Tests für update_check.py (kein echter Netzwerkzugriff)."""
import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(variant):
    spec = importlib.util.spec_from_file_location(f"uc_{variant}", ROOT / variant / "update_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["gtk", "qt"])
def uc(request):
    return _load(request.param)


def test_identical_copies_and_version_files():
    assert (ROOT / "gtk" / "update_check.py").read_text() == (ROOT / "qt" / "update_check.py").read_text()
    assert (ROOT / "gtk" / "version.py").read_text() == (ROOT / "qt" / "version.py").read_text()


def test_version_compare(uc):
    assert uc.is_newer("v1.2.0", "1.1.8")
    assert uc.is_newer("v1.10.0", "1.9.9")
    assert not uc.is_newer("v1.1.8", "1.1.8")
    assert not uc.is_newer("v1.1.7", "1.1.8")
    assert uc.is_newer("v1.2", "1.1.9")
    assert not uc.is_newer("unsinn", "1.1.8")


def _opener(payload):
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return lambda request, timeout=None: R(json.dumps(payload).encode())


def test_check_for_update(uc):
    ok = _opener({"tag_name": "v1.3.0", "html_url": "https://example/x"})
    assert uc.check_for_update("1.2.0", opener=ok)["tag"] == "v1.3.0"
    assert uc.check_for_update("1.3.0", opener=ok) is None
    assert uc.check_for_update("1.2.0", skipped_tag="v1.3.0", opener=ok) is None
    assert uc.check_for_update("1.2.0", opener=_opener({"tag_name": "v1.3.0", "prerelease": True})) is None

    def boom(request, timeout=None):
        raise OSError("kein Netz")
    assert uc.check_for_update("1.2.0", opener=boom) is None
