"""Die Installationsskripte müssen alle Programm-Module kopieren."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_installers_copy_every_module():
    for variant, scripts in (("qt", ["install-linux.sh", "install-macos.sh", "install-windows.bat"]),
                             ("gtk", ["install.sh"])):
        modules = [p.name for p in (ROOT / variant).glob("*.py")]
        assert "sync_tools.py" in modules
        for script in scripts:
            text = (ROOT / variant / script).read_text()
            for name in modules:
                assert name in text, f"{script} kopiert {name} nicht"
