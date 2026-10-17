"""Browser infrastructure package."""

from lca.infrastructure.browser.arbitration import (
    ArbitrationDecision,
    BrowserArbitrationEngine,
)
from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver
from lca.infrastructure.browser.screencast_relay import CDPScreencastRelay
from lca.infrastructure.browser.subagent import BrowserSubagent

__all__ = [
    "ArbitrationDecision",
    "BrowserArbitrationEngine",
    "BrowserSubagent",
    "CDPScreencastRelay",
    "PlaywrightCDPDriver",
]
