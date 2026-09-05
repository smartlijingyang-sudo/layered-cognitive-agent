"""LCA 进程唯一入口(对齐 deepseek-harness ``apps/cli/src/profile-boot.ts:runProfile`` 9 步)。

ADR-0119 决定 3 + 决定 4。``python -m lca_kernel serve --profile X --port 8765``
启动的 LCA 进程**严格镜像** deepseek ``runProfile`` 9 步。

9 步对照表
----------
| 步骤 | deepseek ``runProfile`` 做了 | 本模块 ``serve()`` 应做 |
|---|---|---|
| 1. 装 env 快照 | ``loadLayeredEnv('dsh')`` → ``hostCtx.provide(...)`` | :func:`lca_kernel.env.load_layered_env` + ``ctx.provide("env_snapshot", ...)`` |
| 2. 解析 profile | ``composeProfile`` | (由 ``run_kernel_lifespan`` K1 完成) |
| 3. 装 cordis Context | ``new Context() + Loader + mountRootInclude`` | (由 ``run_kernel_lifespan`` K3 完成) |
| 4. host provide 钩子 | ``prepare(hostCtx)`` 在 plugin 装载前 ``hostCtx.provide(...)`` | 进 ``async with`` 拿到 ctx 后**第一行** ``ctx.provide("env_snapshot", ...)`` + ``ctx.provide("cmdline", ...)`` |
| 5. 装 SIGTERM handler | ``process.on('SIGTERM')`` 装在 ``boot()`` 之前 | :func:`install_signal_handlers` 装在 ``run_kernel_lifespan`` **之前** |
| 6. 装 fail-loud | ``installFailLoud`` | :func:`install_fail_loud` |
| 7. 起 webserver 监听 | webserver plugin 自己在 ``Service.init`` 调 ``server.listen`` | K3 完成后,``ctx.inject("web_server")`` 拿 Starlette app,await ``uvicorn.Server.serve()`` |
| 8. 进程挂着 | ``bin.ts:await runProfile(...)`` 不退出 | uvicorn serve 阻塞,等 SIGTERM |
| 9. SIGTERM 退出 | ``app.current?.fiber.dispose() + sys.exit(0)`` | K6 ``DefaultShutdownCoordinator.shutdown(0)`` → ``sys.exit(0)`` |

LCA 进程 = 唯一进程
-------------------
- deepseek 的 ``dsh`` 命令既是 CLI 也是 LCA 进程的入口
- 旧 LCA 是 "uvicorn 进程" 套 "LCA 进程";重构后 uvicorn 是 cli.py 内部细节
- 一个进程 = 一个入口 = 用户的 shell 管生命周期(SIGTERM / Ctrl-C)
- ``scripts/lca-ops gateway restart`` 改为 ``subprocess.Popen(["uv", "run", "python", "-m", "lca_kernel", "serve", ...])``

为什么 ``build_asgi_app`` 简洁
------------------------------
为 ``TestClient`` 异步测试提供纯净入口:不绕 ThreadPoolExecutor(那是短期凑合),
不写 ``app.state.ctx = inner``(那是 hack),不挂 starlette lifespan(那是
plugin 的事)。``pytest-asyncio`` 已经提供 event loop,直接 await build_asgi_app
拿 app + ctx,正常使用 ``async with app.router.lifespan_context(app) as state``
读 ``state["ctx"]`` 即可。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
import warnings
from typing import Any, NoReturn

from lca_kernel import run_kernel_lifespan
from lca_kernel.lifecycle import (
    create_shutdown_coordinator,
    install_fail_loud,
    install_signal_handlers,
)

# ── Test/uvicorn 入口:build_asgi_app(异步,给 TestClient 用)─────────────


async def build_asgi_app(
    profile_path: str | None = None,
    *,
    env_snapshot: Any | None = None,
) -> tuple[Any, Any]:
    """启动 kernel + 装所有 plugin,返回 ``(starlette_app, ctx)``。

    不调 ``uvicorn.Server.serve()``(那在 :func:`serve` 里)。
    ``pytest-asyncio`` 跑 ``async def`` 测试时直接 ``await build_asgi_app(...)``。

    Args:
        profile_path: YAML profile 路径。``None`` 时 fallback 到 ``LCA_PROFILE`` env 或
            ``profiles/web-standard.yaml``(对齐 ``gateway.app:create_app`` 旧行为)。
    """
    from lca_kernel.env import load_layered_env

    if profile_path is None:
        profile_path = os.environ.get("LCA_PROFILE") or "profiles/web-standard.yaml"

    if env_snapshot is None:
        # 测试场景读 .env 可能含未授权 key;allow_unknown=True 不抛 KernelError
        # (生产 serve() 路径仍默认 False,严格)
        env_snapshot = load_layered_env(bin_name="lca_kernel", dir=os.getcwd(), allow_unknown=True)

    state: dict[str, Any] = {}

    async def _build() -> None:
        async with run_kernel_lifespan(profile_path) as s:
            ctx = s["ctx"]
            ctx.provide("env_snapshot", env_snapshot)
            # lca-web-server plugin 已在 K3 setup 里 provide web_server 句柄
            web_server = ctx.inject("web_server")
            state["ctx"] = ctx
            state["app"] = web_server.app
            # 立即 raise 跳出 async with(让 run_kernel_lifespan dispose ctx);
            # web_server 句柄引用 app,app 仍可用(下次 build_asgi_app 调时 run_kernel_lifespan 会重 boot)
            raise BuildCompleteError()

    with contextlib.suppress(BuildCompleteError):
        await _build()

    return state["app"], state["ctx"]


class BuildCompleteError(Exception):
    """测试 helper:跳出 ``run_kernel_lifespan`` 上下文管理器,保留 booted ctx/app。"""


# ── create_app(ASync,TestClient 测试用)──────────────────────────────


async def create_app(
    profile_path: str | None = None,
    **kwargs: Any,
) -> Any:
    """异步入口,兼容旧 ``gateway.app:create_app()`` 调用(改为 async)。

    长期可维护决定(ADR-0119):本函数是 **async**,不绕 ThreadPoolExecutor,
    不写 ``asyncio.new_event_loop()`` 桥接 hack。所有测试改成
    ``await create_app(...)`` + ``TestClient(app)``(``TestClient`` 兼容同步
    调用,内部支持 ASGI 协议)。

    设计理由(为什么不提供同步 wrapper):
    - 同步 wrapper 必须在另一个 thread 跑 asyncio.run,导致:
      (a) plugin 里 ``ctx._runtime()`` 拿到 thread-local context 跟主 loop 错位
      (b) pyproject 引入 thread safety 问题
      (c) 长期维护负担
    - 测试用 ``pytest-asyncio`` 已有 event loop,直接 await 最干净
    - 生产入口请用 :func:`serve`

    实际使用场景:
    - ``app = await create_app(); TestClient(app).get('/health')`` — 异步测试
    - 生产不要用本函数,用 :func:`serve`
    """
    if kwargs:
        warnings.warn(
            f"create_app ignores legacy kwargs: {sorted(kwargs.keys())}",
            DeprecationWarning,
            stacklevel=2,
        )
    app, _ctx = await build_asgi_app(profile_path)
    return app


# ── Production 入口:serve(对齐 deepseek runProfile 9 步)────────────────


async def _serve_async(
    profile_path: str,
    host: str,
    port: int,
    coordinator: Any,
    allow_unknown_env: bool = False,
) -> int:
    """LCA 进程主体。镜像 deepseek runProfile 9 步。

    Args:
        allow_unknown_env: 允许 .env 含 BOOTSTRAP_NAMES 之外的 key。``serve()`` 入口通过
            ``--allow-unknown-env`` CLI flag 传入;默认 False(K6 fail-loud 守护严格性)。
    """
    # 步骤 1: 装 env 快照
    from lca_kernel.env import load_layered_env

    env_snapshot = load_layered_env(
        bin_name="lca_kernel", dir=os.getcwd(), allow_unknown=allow_unknown_env
    )
    # Profile resolve reads os.environ for {from_env: ...}; apply filtered .env first.
    os.environ.update(dict(env_snapshot.dotenv))

    async def main() -> int:
        async with run_kernel_lifespan(profile_path) as state:  # 步骤 2+3: K1-K6 装 plugin 树
            ctx = state["ctx"]
            # 步骤 4: host provide(env_snapshot + cmdline + bounded exit,跟 deepseek prepare 一样)
            ctx.provide("env_snapshot", env_snapshot)
            ctx.provide(
                "cmdline",
                {
                    "profile": profile_path,
                    "host": host,
                    "port": port,
                    "exit": lambda code: sys.exit(code),
                },
            )
            # bind kernel 给 coordinator(供 SIGTERM 触发 LIFO dispose)
            coordinator._kernel = ctx  # type: ignore[attr-defined]

            # 步骤 7: lca-web-server plugin 已在 K3 装好 Starlette + 装 routes + 装 ASGI state;
            # 这里从 ctx 拿 web_server 句柄,await 触发 uvicorn 监听
            web_server = ctx.inject("web_server")
            import uvicorn

            uconfig = uvicorn.Config(
                web_server.app,
                host=host,
                port=port,
                log_level="info",
                lifespan="on",  # 用 web_server.handle 自带的 lifespan(已 yield ctx)
            )
            server = uvicorn.Server(uconfig)
            ctx.effect(server.shutdown, label="lca-cli.uvicorn.shutdown")

            # 步骤 8: 进程挂着不退;web_server.serve() 阻塞
            await server.serve()
            # 步骤 9: SIGTERM → K6 DefaultShutdownCoordinator.shutdown → ctx.dispose → sys.exit
        return 0

    return await main()


def serve(profile_path: str, host: str, port: int, *, allow_unknown_env: bool = False) -> int:
    """LCA 进程入口(对齐 deepseek ``runProfile`` 9 步)。

    步骤 5+6(装 SIGTERM/fail-loud)**在 run_kernel_lifespan 之前**(覆盖 startup
    window,跟 deepseek runProfile 一致)。K6 内部 ``run_kernel_lifespan`` 会
    再装一次(同 coordinator,idempotent)。

    Args:
        profile_path: YAML profile 路径(必填)。
        host: 监听 host,默认 127.0.0.1。
        port: 监听端口,默认 8765。
        allow_unknown_env: 允许 ``.env`` 含 ``BOOTSTRAP_NAMES`` 之外的 key。
            开发 / 集成场景用;生产建议保持 ``False``(K6 fail-loud 守护)。
    """
    # 步骤 5+6: 装 SIGTERM/SIGINT + fail-loud(在 boot 之前)
    coordinator = create_shutdown_coordinator(kernel=None)
    install_signal_handlers(coordinator)
    install_fail_loud(coordinator)

    return asyncio.run(_serve_async(profile_path, host, port, coordinator, allow_unknown_env))


# ── CLI parser(``python -m lca_kernel serve ...``)────────────────────────


def main() -> NoReturn:
    parser = argparse.ArgumentParser(
        prog="lca_kernel",
        description="LCA 进程入口(对齐 deepseek-harness runProfile 9 步)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve_p = sub.add_parser("serve", help="启动 LCA 进程(前台挂起,Ctrl-C 退)")
    serve_p.add_argument("--profile", required=True, help="YAML profile 路径")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)
    serve_p.add_argument(
        "--allow-unknown-env",
        action="store_true",
        help=(
            "允许 .env 含 BOOTSTRAP_NAMES 之外的 key(开发 / 集成场景用;"
            "生产建议保持严格,由 K6 fail-loud 守护)"
        ),
    )

    args = parser.parse_args()
    if args.cmd == "serve":
        with contextlib.suppress(KeyboardInterrupt):
            sys.exit(
                serve(
                    args.profile,
                    args.host,
                    args.port,
                    allow_unknown_env=args.allow_unknown_env,
                )
            )
        sys.exit(130)  # Ctrl-C exit 130
    raise SystemExit(f"unknown cmd: {args.cmd}")


__all__ = ["build_asgi_app", "create_app", "main", "serve"]
