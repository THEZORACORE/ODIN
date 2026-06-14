"""Core pydantic schemas — the data backbone of ODIN.

Every inter-agent message and persistence record derives from these.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NodeStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class VerifyOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


class MemoryType(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class ActionRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


class AgentRole(StrEnum):
    ODIN = "odin"
    THOR = "thor"
    FREYA = "freya"
    LOKI = "loki"
    MIMIR = "mimir"
    HEIMDALL = "heimdall"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Plan DAG
# ---------------------------------------------------------------------------

class PlanNode(BaseModel):
    """Single node in a plan DAG.  Children are dependency edges."""

    id: str = Field(default_factory=_uid)
    goal: str
    agent: AgentRole = AgentRole.THOR
    status: NodeStatus = NodeStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    tool_hint: str | None = None
    result: str | None = None
    retries: int = 0
    max_retries: int = 2
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class PlanDAG(BaseModel):
    """A directed acyclic graph of PlanNodes representing a decomposed goal."""

    id: str = Field(default_factory=_uid)
    goal: str
    nodes: list[PlanNode] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)

    def ready_nodes(self) -> list[PlanNode]:
        """Return nodes whose dependencies are all completed."""
        completed_ids = {n.id for n in self.nodes if n.status == NodeStatus.COMPLETED}
        return [
            n
            for n in self.nodes
            if n.status == NodeStatus.PENDING
            and all(dep in completed_ids for dep in n.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED) for n in self.nodes
        )

    def has_failed(self) -> bool:
        return any(n.status == NodeStatus.FAILED and n.retries >= n.max_retries for n in self.nodes)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class Provenance(BaseModel):
    """Where a piece of information came from."""
    source_type: str  # "tool", "llm", "user", "memory"
    source_id: str
    timestamp: datetime = Field(default_factory=_now)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class MemoryRecord(BaseModel):
    """A single memory entry stored in MIMIR."""

    id: str = Field(default_factory=_uid)
    memory_type: MemoryType
    content: str
    summary: str | None = None
    provenance: list[Provenance] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None
    access_count: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class VerdictRecord(BaseModel):
    """Outcome of a verification pass on a piece of work."""

    id: str = Field(default_factory=_uid)
    node_id: str
    outcome: VerifyOutcome
    method: str  # "self_consistency", "critic", "tool_grounding"
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Skill (procedural memory, Phase 1 stub interface)
# ---------------------------------------------------------------------------

class Skill(BaseModel):
    """A reusable procedure ODIN has learned. Phase 1: stored but not auto-invoked."""

    id: str = Field(default_factory=_uid)
    name: str
    description: str
    steps: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    usage_count: int = 0
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Inter-agent messages
# ---------------------------------------------------------------------------

class AgentMessage(BaseModel):
    """A message between ODIN agents."""

    id: str = Field(default_factory=_uid)
    sender: AgentRole
    receiver: AgentRole
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)


class ToolRequest(BaseModel):
    """Request to execute a tool, routed through HEIMDALL."""

    id: str = Field(default_factory=_uid)
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requester: AgentRole
    risk_level: ActionRisk = ActionRisk.LOW
    timeout_seconds: float = 30.0
    timestamp: datetime = Field(default_factory=_now)


class ToolResult(BaseModel):
    """Result from a tool execution."""

    request_id: str
    tool_name: str
    success: bool
    output: str
    error: str | None = None
    execution_time_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------

class BudgetState(BaseModel):
    """Tracks resource consumption against hard limits."""

    max_tokens: int = 100_000
    max_llm_calls: int = 50
    max_tool_calls: int = 100
    max_wall_clock_seconds: float = 300.0
    max_recursion_depth: int = 10

    tokens_used: int = 0
    llm_calls_used: int = 0
    tool_calls_used: int = 0
    start_time: datetime = Field(default_factory=_now)
    current_depth: int = 0

    def is_exhausted(self) -> bool:
        elapsed = (datetime.now(UTC) - self.start_time).total_seconds()
        return (
            self.tokens_used >= self.max_tokens
            or self.llm_calls_used >= self.max_llm_calls
            or self.tool_calls_used >= self.max_tool_calls
            or elapsed >= self.max_wall_clock_seconds
        )

    def check_depth(self) -> bool:
        return self.current_depth < self.max_recursion_depth

    def record_llm_call(self, tokens: int) -> None:
        self.tokens_used += tokens
        self.llm_calls_used += 1

    def record_tool_call(self) -> None:
        self.tool_calls_used += 1
