"""model_visible layer nodes — messages_merge, history_attach, manifest_commit."""
from agent_lab.nodes.model_visible.messages_merge.plugin import MessagesMerge
from agent_lab.nodes.model_visible.history_attach.plugin import HistoryAttach
from agent_lab.nodes.model_visible.manifest_commit.plugin import ManifestCommit

__all__ = ["MessagesMerge", "HistoryAttach", "ManifestCommit"]
