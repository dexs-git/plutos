"""Tests für die Übersetzungsschicht (i18n.py) – gtk- und qt-Kopie."""
import ast
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(variant):
    spec = importlib.util.spec_from_file_location(f"i18n_{variant}", ROOT / variant / "i18n.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("variant", ["gtk", "qt"])
def test_tr_german_is_identity_and_english_translates(variant, monkeypatch):
    monkeypatch.delenv("PLUTOS_LANG", raising=False)
    m = _load(variant)
    m.set_language("de")
    assert m.tr("Speichern") == "Speichern"
    m.set_language("en")
    assert m.tr("Speichern") == "Save"
    assert m.tr("Unbekannter Text") == "Unbekannter Text"  # Fallback, kein Fehler
    assert m.months()[2] == "March" and m.months_short()[2] == "Mar"
    m.set_language("xx")
    assert m.get_language() == "de"


def test_both_copies_identical():
    assert (ROOT / "gtk" / "i18n.py").read_text() == (ROOT / "qt" / "i18n.py").read_text()


@pytest.mark.parametrize("variant", ["gtk", "qt"])
def test_translation_placeholders_and_tags_match(variant):
    m = _load(variant)
    ph = lambda s: sorted(re.findall(r"\{\d+[^}]*\}", s))
    tags = lambda s: sorted(re.findall(r"</?\w+", s))
    for de, en in m.EN.items():
        assert ph(de) == ph(en), de
        assert tags(de) == tags(en), de


@pytest.mark.parametrize("variant,files", [("qt", ["main.py", "dialogs.py", "charts.py", "theme.py"]), ("gtk", ["main.py", "theme.py"])])
def test_every_tr_key_has_english(variant, files):
    m = _load(variant)
    missing = []
    for f in files:
        for n in ast.walk(ast.parse((ROOT / variant / f).read_text())):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tr"
                    and n.args and isinstance(n.args[0], ast.Constant)):
                key = n.args[0].value
                if key not in m.EN:
                    missing.append(key)
    assert not missing, missing[:5]
