"""graphs — config-driven graph definitions + thin loader.

Every graph lives as YAML under graphs/configs/. The loader converts
the YAML to a frozen InfoEdgeSpec. No business logic here.
"""

from agent_lab.graphs.loader import load_closure, load_graph_manifest, load_registry, load_spec

__all__ = ["load_closure", "load_graph_manifest", "load_registry", "load_spec"]
