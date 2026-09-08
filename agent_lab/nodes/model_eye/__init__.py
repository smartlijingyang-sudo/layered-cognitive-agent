"""model_eye — perceive's sub-graph that builds the model's field of view.

Owned by the perceive phase: sense → aggregate(bundle) → model_eye →
ContextManifest. Think consumes that manifest; it does not mount this graph.

Nodes (all in model_eye.yaml):
  - see    : Session derive + this-turn feeds → sight
  - guard  : trust / dedup / keep / redact → safe_sight
  - shape  : fold into OpenAI messages
  - freeze : validate + digest → frozen ContextManifest

``trust_classify`` remains registered here for toolbox.yaml reuse; it is
not a member of the model_eye graph.
"""

from agent_lab.nodes.model_eye.freeze.plugin import ModelEyeFreeze
from agent_lab.nodes.model_eye.guard.plugin import ModelEyeGuard
from agent_lab.nodes.model_eye.see.plugin import ModelEyeSee
from agent_lab.nodes.model_eye.shape.plugin import ModelEyeShape
from agent_lab.nodes.model_eye.trust_classify.plugin import TrustClassify

__all__ = [
    "ModelEyeFreeze",
    "ModelEyeGuard",
    "ModelEyeSee",
    "ModelEyeShape",
    "TrustClassify",
]
