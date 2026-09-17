"""Matplotlib CJK as a guest fact, not a prompt shopping list.

Model code often overwrites ``font.sans-serif`` with families that are not
installed. ``Figure.savefig`` then restores a working face when none of the
requested names exist in the font manager.
"""

from __future__ import annotations


def apply_matplotlib_cjk() -> str | None:
    """Register the first existing CJK font file and wrap ``Figure.savefig``."""
    from pathlib import Path

    font_files = (
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/google-droid/DroidSansFallback.ttf",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    )
    try:
        import matplotlib
        from matplotlib import font_manager as fm
        from matplotlib.figure import Figure
    except ImportError:
        return None

    if getattr(Figure.savefig, "_lca_cjk", False):
        return str(matplotlib.rcParams.get("font.sans-serif", [""])[0] or "") or None

    chosen_name: str | None = None
    for raw in font_files:
        path = Path(raw)
        if not path.is_file():
            continue
        try:
            fm.fontManager.addfont(str(path))
            chosen_name = fm.FontProperties(fname=str(path)).get_name()
            break
        except (OSError, ValueError):
            continue
    if not chosen_name:
        return None

    matplotlib.rcParams["font.sans-serif"] = [chosen_name]
    matplotlib.rcParams["axes.unicode_minus"] = False
    original = Figure.savefig

    def savefig(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        requested = [str(name) for name in (matplotlib.rcParams.get("font.sans-serif") or [])]
        available = {font.name for font in fm.fontManager.ttflist}
        if not any(name in available for name in requested):
            matplotlib.rcParams["font.sans-serif"] = [chosen_name]
            matplotlib.rcParams["axes.unicode_minus"] = False
        return original(self, *args, **kwargs)

    savefig._lca_cjk = True  # type: ignore[attr-defined]
    Figure.savefig = savefig  # type: ignore[method-assign]
    return chosen_name


def install_matplotlib_cjk_hook() -> None:
    """Wrap ``__import__`` so CJK binding runs on first matplotlib import."""
    import builtins

    if getattr(builtins, "_lca_mpl_cjk_hook", False):
        return
    orig = builtins.__import__
    applying = False

    def _import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        nonlocal applying
        matplotlib_import = name == "matplotlib" or name.startswith("matplotlib.")
        if matplotlib_import and not applying:
            applying = True
            try:
                module = orig(name, globals, locals, fromlist, level)
                apply_matplotlib_cjk()
                return module
            finally:
                applying = False
        return orig(name, globals, locals, fromlist, level)

    builtins.__import__ = _import  # type: ignore[method-assign]
    builtins._lca_mpl_cjk_hook = True  # type: ignore[attr-defined]


def guest_bootstrap_source() -> str:
    """Python prepended to sandbox execute so CJK survives model rcParams."""
    import inspect

    return (
        inspect.getsource(apply_matplotlib_cjk)
        + "\n"
        + inspect.getsource(install_matplotlib_cjk_hook)
        + "\ninstall_matplotlib_cjk_hook()\n"
    )
