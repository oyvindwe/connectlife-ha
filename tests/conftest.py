"""Shared test fixtures."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import custom_components.connectlife.dictionaries as dictmod


@pytest.fixture
def build_dictionary():
    """Factory to build a ``Dictionary`` from inline mapping data.

    Runs the real ``Dictionaries.get_dictionary`` parser/merge over data passed
    in-process instead of reading any shipped YAML file, so tests exercise the
    parsing and inheritance logic without coupling to specific device mappings.

    Pass already-parsed mapping dicts (as ``yaml.safe_load`` would return):
    ``base`` for ``{type_code}.yaml`` and/or ``sub`` for the
    ``{type_code}-{feature}.yaml`` feature override.
    """
    created: list[str] = []

    def _build(*, base=None, sub=None, type_code="999", feature="000"):
        files: dict[str, object] = {}
        if base is not None:
            files[f"data_dictionaries/{type_code}.yaml"] = base
        if sub is not None:
            files[f"data_dictionaries/{type_code}-{feature}.yaml"] = sub

        def fake_load(path):
            if path in files:
                return True, files[path]
            return False, None

        key = f"{type_code}-{feature}"
        dictmod.Dictionaries.dictionaries.pop(key, None)
        created.append(key)
        with patch.object(dictmod, "_load_yaml", side_effect=fake_load):
            return dictmod.Dictionaries.get_dictionary(
                SimpleNamespace(
                    device_type_code=type_code,
                    device_feature_code=feature,
                    device_nickname="test",
                )
            )

    yield _build
    for key in created:
        dictmod.Dictionaries.dictionaries.pop(key, None)
