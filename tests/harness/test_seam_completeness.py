"""Tests for Loader._check_seam_completeness — seam triangle validation.

Spec reference: §3.7 of harness-spine-spec.
"""
from __future__ import annotations

import pytest

from lca.contracts.harness.plugin import ExtensionPoint, PluginKind, PluginManifest


class TestSeamCompleteness:
    """Loader reconcile 自动校验 Seam 三角完整性"""

    def test_definition_without_provider_raises(self) -> None:
        """有 DEFINITION 但没有 PROVIDER → 报错"""
        from lca.layer0_infra.plugin.loader._loader import Loader

        handles = [
            _make_handle(
                PluginManifest(
                    id="defn",
                    version="1.0.0",
                    api_version="lca-harness/1",
                    kind=PluginKind.DEFINITION,
                    seam_key="llm",
                    extension_points=(ExtensionPoint(seam_key="llm"),),
                )
            )
        ]
        loader = Loader()
        with pytest.raises(Exception, match="no provider"):
            loader._check_seam_completeness(handles)

    def test_provider_without_definition_raises(self) -> None:
        """PROVIDER 引用不存在的 DEFINITION → 报错"""
        from lca.layer0_infra.plugin.loader._loader import Loader

        handles = [
            _make_handle(
                PluginManifest(
                    id="prov",
                    version="1.0.0",
                    api_version="lca-harness/1",
                    kind=PluginKind.PROVIDER,
                    seam_key="unknown_seam",
                )
            )
        ]
        loader = Loader()
        with pytest.raises(Exception, match="unknown seam"):
            loader._check_seam_completeness(handles)

    def test_complete_triangle_passes(self) -> None:
        """DEFINITION + PROVIDER + CONSUMER → 通过"""
        from lca.layer0_infra.plugin.loader._loader import Loader

        handles = [
            _make_handle(
                PluginManifest(
                    id="defn",
                    version="1.0.0",
                    api_version="lca-harness/1",
                    kind=PluginKind.DEFINITION,
                    seam_key="llm",
                    extension_points=(ExtensionPoint(seam_key="llm"),),
                )
            ),
            _make_handle(
                PluginManifest(
                    id="prov",
                    version="1.0.0",
                    api_version="lca-harness/1",
                    kind=PluginKind.PROVIDER,
                    seam_key="llm",
                )
            ),
            _make_handle(
                PluginManifest(
                    id="cons",
                    version="1.0.0",
                    api_version="lca-harness/1",
                    kind=PluginKind.CONSUMER,
                    seam_key="llm",
                )
            ),
        ]
        loader = Loader()
        loader._check_seam_completeness(handles)  # should not raise

    def test_definition_without_consumer_warns(self) -> None:
        """有 DEFINITION + PROVIDER 但无 CONSUMER → warning，不报错"""
        from lca.layer0_infra.plugin.loader._loader import Loader

        handles = [
            _make_handle(
                PluginManifest(
                    id="defn",
                    version="1.0.0",
                    api_version="lca-harness/1",
                    kind=PluginKind.DEFINITION,
                    seam_key="llm",
                    extension_points=(ExtensionPoint(seam_key="llm"),),
                )
            ),
            _make_handle(
                PluginManifest(
                    id="prov",
                    version="1.0.0",
                    api_version="lca-harness/1",
                    kind=PluginKind.PROVIDER,
                    seam_key="llm",
                )
            ),
        ]
        loader = Loader()
        loader._check_seam_completeness(handles)  # should not raise, just warn


def _make_handle(manifest: PluginManifest):
    """创建最小 mock PluginHandle"""
    from unittest.mock import MagicMock

    h = MagicMock()
    h.manifest = manifest
    h.entry_id = manifest.id
    h.state = "ACTIVE"
    return h
