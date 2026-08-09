#!/usr/bin/env bash
# Build / refresh the Onlyboxes pythonExec guest image used by LCA.
# Default tag matches WORKER_PYTHON_EXEC_DOCKER_IMAGE in onlyboxes-worker-docker.service.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
IMAGE_TAG="${ONLYBOXES_PYTHON_IMAGE:-onlyboxes-python-local:3.11}"

echo "==> Building ${IMAGE_TAG}"
docker build \
  --pull \
  -f "${ROOT}/Dockerfile.python" \
  -t "${IMAGE_TAG}" \
  "${ROOT}"

echo "==> Smoke: import preinstalled packages inside image"
docker run --rm "${IMAGE_TAG}" python -c '
import importlib
import warnings
mods = [
    "pandas", "numpy", "openpyxl", "xlsxwriter", "matplotlib",
    "seaborn", "PIL", "scipy", "requests", "tabulate",
]
for m in mods:
    importlib.import_module(m)
    print(f"  {m}: OK")
print("all preinstalled packages importable")
'

echo "==> Smoke: matplotlib CJK glyphs (no DejaVu missing-glyph warning)"
docker run --rm "${IMAGE_TAG}" python -c '
import warnings
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

out = Path("/tmp/lca_cjk_smoke.png")
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    fig, ax = plt.subplots()
    ax.set_title("自动生成图表")
    ax.set_xlabel("自变量")
    ax.set_ylabel("因变量")
    ax.plot([1, 2, 3], [1, 4, 9])
    fig.savefig(out)
    plt.close(fig)
glyph = [w for w in caught if "Glyph" in str(w.message) and "missing" in str(w.message)]
assert not glyph, f"CJK font still missing: {glyph[0].message if glyph else None}"
assert out.is_file() and out.stat().st_size > 0
print("  matplotlib CJK: OK", out.stat().st_size, "bytes")
'

echo "==> Done. Worker picks up the new tag on next pythonExec container start."
echo "    Image: ${IMAGE_TAG}"
echo "    If tasks still miss packages, restart: sudo systemctl restart onlyboxes-worker-docker"
