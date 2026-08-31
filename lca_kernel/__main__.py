"""``python -m lca_kernel ...`` 入口。ADR-0119 决定 3。委托给 :mod:`lca_kernel.cli`。"""

from lca_kernel.cli import main

if __name__ == "__main__":
    main()
