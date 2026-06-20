"""Multi-agent society: debate, consensus & ensembles (Phase 8).

RATATOSKR — message bus
VÉ & VILI — ensemble reasoners
FORSETI — debate & consensus judge
DRAUPNIR — sub-agent lifecycle
SLEIPNIR — parallel execution
"""

from odin.society.agents import AgentPool, SubAgent
from odin.society.debate import DebateJudge, DebateResult, DebateRound
from odin.society.ensemble import EnsembleResult, EnsembleRunner
from odin.society.ratatoskr import AgentMessage, MessageBus

__all__ = [
    "AgentMessage",
    "AgentPool",
    "DebateJudge",
    "DebateResult",
    "DebateRound",
    "EnsembleResult",
    "EnsembleRunner",
    "MessageBus",
    "SubAgent",
]
