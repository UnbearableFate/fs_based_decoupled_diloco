from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_FILES = [
    ROOT / "fs_diloco/storage/memory.py",
    ROOT / "fs_diloco/log/model.py",
    ROOT / "fs_diloco/testing/deterministic_reference.py",
    ROOT / "fs_diloco/testing/reference_simulator.py",
    ROOT / "fs_diloco/testing/trace.py",
    ROOT / "fs_diloco/testing/model_checker.py",
]
FORBIDDEN = {"torch", "transformers", "datasets", "numpy", "pathlib", "socket", "requests"}


def test_reference_model_has_no_runtime_filesystem_ml_or_network_dependencies():
    for path in REFERENCE_FILES:
        tree = ast.parse(path.read_text(), filename=str(path))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert not (imports & FORBIDDEN), f"{path.name}: forbidden imports {imports & FORBIDDEN}"
