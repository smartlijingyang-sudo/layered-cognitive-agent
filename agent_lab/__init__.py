"""agent_lab — single executable graph + nested sub-graphs (ADR-0206 prototype).

Six layers (no behavior at the framework level):
  primitives/  frozen data contracts (Artifact, Port, Edge)
  graph/       declarative spec + C1-C14 validate + compile
  nodes/       ant-worker node library (each < 50 LOC, config-driven)
  runtime/     scheduler + joiner + runner (recursive interpreter)
  graphs/      three core graphs: agent_loop, mv.assemble, effect.dispatch
  run.py       entry point
"""

__version__ = "0.1.0-prototype"
