# cordis Public Contract

This document describes the public API contract that `cordis.invariant` re-exports
and that all consumers of the framework can rely on.

## Overview

cordis is a 1:1 Python port of `@deepseek-ai/cordis` (the TypeScript plugin framework).
Every package in the taiyi-agent workspace depends on cordis; this contract
defines what cordis promises.

## Lifecycle Guarantees

- **`Context`** is a hierarchical DI container. Child contexts inherit bindings
  from their parent chain (`Context.fork()`).
- **`Service`** instances registered via `ctx.effect(dispose_fn)` are disposed
  in **LIFO order** when their owning context disposes. Errors in individual
  disposers are **logged but swallowed** so all disposers still run.
- **`Fiber`** is a lifecycle primitive for plugins with a 6-state machine:
  `PENDING → LOADING → ACTIVE → UNLOADING → DISPOSED` (plus `FAILED`).
- **`Effect`** is a single or iterable disposer with **reverse-order** execution
  and **dedup** by function identity.

## Event System (5 dispatch modes)

| Mode | Behavior |
|---|---|
| `emit` | Synchronous fire-and-forget; listeners called but not awaited |
| `parallel` | `asyncio.gather` all listeners; aggregate errors |
| `serial` | Await listeners in order; stop on first bail value |
| `bail` | Synchronous in order; stop on first bail value |
| `waterfall` | Onion model; each listener wraps the next via `next()` |

A listener is considered "bail" when its return value is **not None/False**.

## DI System (Fiber)

- `inject: list[str]` declares dependencies; `_check_impl()` resolves them.
- `store: dict[str, Impl]` caches resolved implementations.
- `inertia` is a `Future`-like awaiting reactivation.
- `_refresh()` recomputes the epoch and triggers `_reload()` when deps change.
- `_set_epoch()` invalidates the current fiber state if the dependency set changed.

## Reflect Protocol (Proxy)

- `ctx[name]` reads via the `ReflectService.handler` walking `fiber.store`
  + isolation scope + inject map.
- `ctx[name] = value` writes via the handler, emits `internal/set` waterfall.
- `notify()` walks the registry and triggers `_check_impl` + `_refresh`
  for any fiber whose dependencies may have changed.

## Logger

- 4 levels: `ERROR=0`, `INFO=1`, `WARN=2`, `DEBUG=3` (lower number = higher severity).
- Per-exporter `levels: dict[name_or_default, threshold]` filters messages.
- Threshold semantic: emit messages with `level <= threshold` (i.e., the
  threshold is a **maximum level number** that gets emitted).
- printf-style formatters: `%s`, `%d`, `%i`, `%f`, `%o`, `%O`, `%c`, `%C`.
- ANSI color codes via `Logger.color()` and `Logger.code()`.

## Loader

- `load_config(data)` accepts dict / list / YAML string → `EntryTree`.
- `load_yaml(path)` reads a YAML file from disk.
- `dump_config(tree)` round-trips back to a dict.
- `interpolate(value, scope)` substitutes `${path}` tokens.
- `merge_bundles(*bundles)` overlays bundles by entry id (later wins).

## Plugin Decorator

- `@plugin` (bare) wraps an async setup function.
- `@plugin(name=..., inject=..., Config=..., meta=...)` parameterizes.
- Returns a `Plugin` instance with metadata.

## Stability Guarantees

All symbols exported from `cordis.invariant` are **stable** and will not change
in breaking ways without a major version bump. Symbols not exported there are
**internal** and may change at any time.

## Testing

- Per-file 100% coverage is enforced (with documented exceptions).
- `pyright strict` 0 errors.
- `ruff` clean.