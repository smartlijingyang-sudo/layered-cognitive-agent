"""CallId type alias for the run session writer Protocol.

A tool-call identifier carried alongside tool execution data. The wire shape
is opaque to the writer; the value is forwarded to ``Session.append`` data
and to the ``surface/tool_result`` linking field.
"""

from typing import NewType

CallId = NewType("CallId", str)

__all__ = ["CallId"]
