"""Offline checks for the repository's documentation and reload contracts."""

from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def check_module_documents() -> None:
    missing = [
        str(source.relative_to(ROOT))
        for source in (ROOT / "src").rglob("*.py")
        if not (ROOT / "docs" / source.relative_to(ROOT / "src").with_suffix(".md")).is_file()
    ]
    assert not missing, f"Missing matching module documents: {missing}"


def check_makefile_paths() -> None:
    paths = re.findall(r"\b(?:tools|tests)/[\w/-]+\.py", (ROOT / "Makefile").read_text())
    missing = sorted({path for path in paths if not (ROOT / path).is_file()})
    assert not missing, f"Makefile references missing local scripts: {missing}"


def check_reload_contract() -> None:
    tree = ast.parse((ROOT / "ui_app.py").read_text())
    imports = {
        alias.asname or alias.name: alias.name
        for node in tree.body if isinstance(node, ast.Import)
        for alias in node.names
    }
    reload_loop = next(
        node for node in tree.body
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
        and node.target.id == "_module"
    )
    reloaded = {imports[node.id] for node in reload_loop.iter.elts}
    required = set()
    for path in [ROOT / "ui_app.py", ROOT / "src/acoustics.py", *(ROOT / "src/ui").glob("*.py")]:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                required.update(
                    alias.name for alias in node.names
                    if (ROOT / "src" / (alias.name.replace(".", "/") + ".py")).is_file()
                )
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                if (ROOT / "src" / (node.module + ".py")).is_file():
                    required.add(node.module)
    assert required - {"acoustics"} <= reloaded, f"Missing backend reloads: {required - reloaded - {'acoustics'}}"
    order = [imports[node.id] for node in reload_loop.iter.elts]
    assert order.index("saas") < order.index("billing")

    # Exercise the actual helper against an edited module in a long-lived process.
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_reload_if_source_changed")
    namespace = {"Path": Path, "importlib": importlib}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "ui_app.py", "exec"), namespace)
    reload_changed = namespace["_reload_if_source_changed"]
    module_name = "_load_forge_contract_fixture"
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / f"{module_name}.py"
        source.write_text("def value(): return 1\n")
        sys.path.insert(0, directory)
        try:
            module = importlib.import_module(module_name)
            assert reload_changed(module)
            original = module.value
            assert not reload_changed(module)
            assert module.value is original
            timestamp = source.stat().st_mtime + 2
            source.write_text("def value(): return 200\n")
            os.utime(source, (timestamp, timestamp))
            assert reload_changed(module)
            assert module.value() == 200
        finally:
            sys.path.remove(directory)
            sys.modules.pop(module_name, None)


class RepositoryContracts(unittest.TestCase):
    def test_module_documents(self):
        check_module_documents()

    def test_makefile_paths(self):
        check_makefile_paths()

    def test_reload_contract(self):
        check_reload_contract()


if __name__ == "__main__":
    unittest.main()
