from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fs_diloco.storage import InMemoryStorageBackend
from fs_diloco.syncer_core.capabilities import PrepareObjectFacade


def test_prepare_facade_exposes_only_scoped_immutable_io():
    backend = InMemoryStorageBackend()
    facade = PrepareObjectFacade(
        backend,
        read_prefixes=("immutable/",),
        write_prefixes=("prepared/",),
    )
    facade.put_immutable("prepared/result", b"result")
    backend.put_immutable("immutable/input", b"input")
    assert facade.get("immutable/input") == b"input"
    assert not hasattr(facade, "conditional_replace")
    assert not hasattr(facade, "list_prefix")
    assert not hasattr(facade, "head")
    with pytest.raises(PermissionError):
        facade.get("control/head.json")
    with pytest.raises(PermissionError):
        facade.put_immutable("control/head.json", b"forbidden")


def test_future_executor_modules_cannot_statically_import_authority_apis():
    root = Path(__file__).resolve().parents[2] / "fs_diloco" / "syncer_core"
    tree = ast.parse((root / "capabilities.py").read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(name.startswith("fs_diloco.coordination") for name in imports)
    assert not any(name.startswith("fs_diloco.log.production") for name in imports)

