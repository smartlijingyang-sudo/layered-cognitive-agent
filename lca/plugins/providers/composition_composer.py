"""CordisComposer —— Creator §13.3 Composer 的默认 cordis 实现。

本文件聚焦 Composer 类本身（mount / unmount / inspect / list_presets）
与其依赖的 §23.2 默认 invariant。Tier-2 plugin 注册（``@plugin`` +
``build_composer_factory``）见 :mod:`composition_provider`。
"""

from __future__ import annotations

import inspect
from contextlib import suppress
from typing import Any

from lca.contracts.atoms.artifact_state import ArtifactState
from lca.contracts.harness.journal.artifact import (
    ArtifactController,
    CapabilityArtifact,
    controller_migrate,
    make_capability_artifact,
)
from lca.contracts.harness.composition.plugin_meta import PluginMeta
from lca.contracts.mechanisms.composition import (
    CapabilityGrantExceeded,
    Composer,
    ComposerError,
    ComposerErrorCode,
    InspectEntry,
    InspectResult,
    InvariantChecker,
    InvariantViolation,
    MountResult,
    NameConflict,
    NotMounted,
    PluginFactory,
    PluginMetaMissing,
    UnmountResult,
)

# ── §23.2 默认 invariant ───────────────────────────────────────


def build_default_invariant_checker() -> InvariantChecker:
    """§23.2 默认 invariant —— ``policy_class != "control"`` 之外的 plugin 都允许 mount。

    Plugin-thinking：把 §23.2 invariant 实现为可注入 Protocol，默认实现遵循
    宪法 §13.3.1「invariant 检查必跑」 + 「缺省最小化（§C7）」；测试可注入
    自定义 checker 模拟失败路径。
    """

    class _DefaultInvariantChecker:
        def check_mount(self, name: str, meta: PluginMeta) -> None:
            if meta.get("policy_class") == "control":
                raise InvariantViolation(
                    f"plugin {name!r} policy_class='control' 必须经人工审批才能挂载",
                    plugin_name=name,
                    check_name="policy_class_control",
                )

        def check_unmount(self, name: str, meta: PluginMeta) -> None:
            return None

    return _DefaultInvariantChecker()


# ── Composer 实现 ─────────────────────────────────────────────


class CordisComposer(Composer):
    """Creator §13.3 Composer 的 cordis 默认实现（纯逻辑）。

    所有 mount / unmount / inspect 操作的副作用仅限 cordis Context（own_bindings
    + 内部 meta / factory 索引）；不调 ``record(...)``，不写 AgentState。
    调用方在接住结果 / 异常后自行决定是否写 journal。
    """

    def __init__(
        self,
        ctx: Any,
        *,
        invariant_checker: InvariantChecker | None = None,
    ) -> None:
        self._ctx = ctx
        self._invariant = invariant_checker or build_default_invariant_checker()
        self._meta_by_key: dict[str, PluginMeta] = {}
        self._factory_by_key: dict[str, PluginFactory] = {}
        self._artifact_controller = ArtifactController(name="cordis-composer")
        self._artifact_by_key: dict[str, CapabilityArtifact] = {}
        self._retired_artifact_by_key: dict[str, CapabilityArtifact] = {}

    # ── Public API ──

    def mount(
        self,
        factory: PluginFactory,
        *,
        caller_grant: tuple[str, ...] = (),
        actor_role: str = "",
        step: int = 0,
    ) -> MountResult:
        meta = factory.plugin_meta
        # ── PR12 闸 ──
        if not meta:
            raise PluginMetaMissing(
                f"plugin {factory.name!r} 缺少 plugin_meta (PR12 强制)",
                plugin_name=factory.name,
            )

        capabilities: tuple[str, ...] = tuple(meta.get("capabilities") or ())
        # ── C5 闸：grant ⊇ capabilities（空 capabilities 视为不需要 grant）──
        if capabilities:
            granted_set = set(caller_grant)
            required_set = set(capabilities)
            if not required_set.issubset(granted_set):
                missing = tuple(sorted(required_set - granted_set))
                raise CapabilityGrantExceeded(
                    f"plugin {factory.name!r} 缺少 capability grant {missing!r}",
                    granted=caller_grant,
                    required=capabilities,
                )

        # ── §23.2 闸 ──
        self._invariant.check_mount(factory.name, meta)

        artifact = make_capability_artifact(
            logical_id=factory.name,
            content=_artifact_fingerprint(factory),
            grants=capabilities,
            metadata={"source_path": factory.source_path, "plugin_meta": dict(meta)},
        )
        artifact = controller_migrate(self._artifact_controller, artifact, ArtifactState.VERIFIED)

        # ── 重复名校验 ──
        ctx_key = f"plugin:{factory.name}"
        if ctx_key in self._meta_by_key:
            raise NameConflict(
                f"plugin {factory.name!r} 已在 Context",
                plugin_name=factory.name,
            )

        # ── 实例化 ──
        try:
            instance = self._instantiate(factory.factory)
        except ComposerError:
            raise
        except Exception as exc:
            raise ComposerError(
                f"plugin {factory.name!r} factory() 抛出 {type(exc).__name__}: {exc}",
                code=ComposerErrorCode.INVALID_PAYLOAD,
            ) from exc

        # ── ctx.provide ──
        self._ctx.provide(ctx_key, instance)
        self._meta_by_key[ctx_key] = meta
        self._factory_by_key[ctx_key] = factory
        self._artifact_by_key[ctx_key] = controller_migrate(
            self._artifact_controller, artifact, ArtifactState.ACTIVE
        )

        return MountResult(
            plugin_name=factory.name,
            plugin_id=factory.name,
            context_key=ctx_key,
            capabilities=capabilities,
            capability_grant=caller_grant,
            meta_snapshot=dict(meta),
        )

    def unmount(
        self,
        plugin_name: str,
        *,
        actor_role: str = "",
        step: int = 0,
    ) -> UnmountResult:
        ctx_key = f"plugin:{plugin_name}"
        if ctx_key not in self._meta_by_key:
            raise NotMounted(
                f"plugin {plugin_name!r} 未挂载",
                plugin_name=plugin_name,
            )

        self._meta_by_key.pop(ctx_key, None)
        self._factory_by_key.pop(ctx_key, None)
        artifact = self._artifact_by_key.pop(ctx_key, None)
        if artifact is not None:
            self._retired_artifact_by_key[ctx_key] = controller_migrate(
                self._artifact_controller, artifact, ArtifactState.RETIRED
            )
        with suppress(Exception):
            self._ctx.own_bindings.pop(ctx_key, None)

        return UnmountResult(plugin_name=plugin_name, context_key=ctx_key)

    def artifact_for(self, plugin_name: str) -> CapabilityArtifact | None:
        """Return the active artifact tracked for a mounted plugin, if any."""
        return self._artifact_by_key.get(f"plugin:{plugin_name}")

    def retired_artifact_for(self, plugin_name: str) -> CapabilityArtifact | None:
        """Return the retained immutable artifact evidence after unmount."""
        return self._retired_artifact_by_key.get(f"plugin:{plugin_name}")

    def inspect(self, *, actor_role: str = "") -> InspectResult:
        entries: list[InspectEntry] = []
        for key in sorted(self._meta_by_key.keys()):
            meta = self._meta_by_key.get(key, {})
            name = key.split(":", 1)[-1] if key.startswith("plugin:") else key
            entries.append(
                InspectEntry(
                    name=name,
                    context_key=key,
                    plugin_id=name,
                    meta=dict(meta),
                    implements=tuple(meta.get("implements") or ()),
                    capabilities=tuple(meta.get("capabilities") or ()),
                    policy_class=str(meta.get("policy_class") or ""),
                    side_effects=str(meta.get("side_effects") or ""),
                )
            )
        context_keys = self._safe_context_keys()
        return InspectResult(
            entries=tuple(entries),
            context_keys=context_keys,
        )

    def list_presets(self) -> tuple[str, ...]:
        """返回当前进程可见的 preset id 列表（§13.3 publish 持久化层）。

        实现委托给 :class:`PresetAuthoring`，避免本模块硬编码 I/O 路径。
        委托失败（如 PresetAuthoring 尚未装配）返回空 tuple，调用方按
        空集合优雅降级（inspect 不依赖 preset 列表）。
        """
        try:
            from lca.application.preset_authoring import PresetAuthoring
        except Exception:
            return ()
        try:
            return PresetAuthoring.list_visible_presets()
        except Exception:
            return ()

    # ── Internal helpers ──

    def _safe_context_keys(self) -> tuple[str, ...]:
        try:
            keys = list(getattr(self._ctx, "own_bindings", {}).keys())
        except Exception:
            keys = []
        return tuple(sorted(keys))

    def _instantiate(self, factory: Any) -> Any:
        """调用 factory 创建 plugin 实例；接受 sync factory。

        只允许零必填位置参数；额外参数通过 factory 闭包注入（PR12
        PluginMeta 不允许传 args，因为 plugin meta 应能静态校验）。
        """
        sig = inspect.signature(factory)
        required_params = [
            p
            for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if required_params:
            raise ComposerError(
                f"plugin factory {getattr(factory, '__name__', factory)!r} "
                f"必填位置参数 {[p.name for p in required_params]} 违反 PluginMeta 静态语义",
                code=ComposerErrorCode.INVALID_PAYLOAD,
            )
        return factory()


def _artifact_fingerprint(factory: PluginFactory) -> str:
    """Produce deterministic artifact content from the mountable declaration."""
    meta_items = tuple(
        sorted((str(key), repr(value)) for key, value in factory.plugin_meta.items())
    )
    return repr((factory.name, factory.source_path, meta_items))


__all__ = ["CordisComposer", "build_default_invariant_checker"]
