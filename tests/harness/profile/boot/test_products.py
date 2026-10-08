"""Seam pins for the profile boot products attachment (RA-069).

The products mount through the public cordis ``Context.provide`` /
``Context.get`` bindings (same idiom as the observability seam), and
the seam rejects re-interpretation: attaching a *different* products
object to an already-attached scope raises.
"""

from __future__ import annotations

import pytest
from cordis import Context

from lca.harness.profile.boot.products import (
    ProfileBootProducts,
    attach_profile_boot_products,
    profile_boot_products_from_scope,
)


def _products() -> ProfileBootProducts:
    return ProfileBootProducts()


class TestAttachReadRoundTrip:
    def test_attach_then_read_back(self) -> None:
        scope = Context()
        products = _products()
        assert attach_profile_boot_products(scope, products) is products
        assert profile_boot_products_from_scope(scope) is products

    def test_read_from_empty_scope_is_none(self) -> None:
        assert profile_boot_products_from_scope(Context()) is None

    def test_attach_same_products_twice_is_idempotent(self) -> None:
        scope = Context()
        products = _products()
        attach_profile_boot_products(scope, products)
        # Equal (dataclass) products: second attach returns the existing one.
        assert attach_profile_boot_products(scope, _products()) is products

    def test_attach_different_products_raises(self) -> None:
        scope = Context()
        attach_profile_boot_products(
            scope, ProfileBootProducts(resolved_profile=None)
        )
        with pytest.raises(RuntimeError, match="already attached"):
            attach_profile_boot_products(
                scope, ProfileBootProducts(compiled_run_plan=object())
            )

    def test_invalid_stored_type_raises(self) -> None:
        scope = Context()
        scope.provide("_lca_profile_boot_products", "not-products")
        with pytest.raises(RuntimeError, match="invalid type"):
            profile_boot_products_from_scope(scope)

    def test_mount_uses_public_provide_not_dunder_dict(self) -> None:
        """RA-069: the seam must not touch ``Context.__dict__`` directly."""
        scope = Context()
        attach_profile_boot_products(scope, _products())
        assert "_lca_profile_boot_products" not in scope.__dict__
        # ...but the binding is visible through the public read idiom.
        # NOTE: Context.get routes through Reflect's service store and does
        # NOT see provide()d bindings; the public read idiom is inject.
        assert scope.inject("_lca_profile_boot_products") is not None
