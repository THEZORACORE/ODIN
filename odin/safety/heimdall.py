"""HEIMDALL — Guardian of the Bifröst.

Enforces:
1. Approval gates on irreversible/high-risk actions
2. Capability / least-privilege checks per agent role
3. Budget limits (tokens, calls, wall-clock)
4. Prompt-injection boundary: external content is DATA, never instructions
5. Recursion-depth caps

Every tool call routes through Heimdall.gate() before execution.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from odin.schemas import (
    ActionRisk,
    AgentRole,
    BudgetState,
    ImprovementProposal,
    ToolRequest,
    ToolResult,
)

# ---------------------------------------------------------------------------
# Capability matrix — which agents can use which tools at which risk
# ---------------------------------------------------------------------------

_AGENT_CAPABILITIES: dict[AgentRole, dict[str, ActionRisk]] = {
    AgentRole.THOR: {
        "code_interpreter": ActionRisk.MEDIUM,
        "web_search": ActionRisk.LOW,
        "memory_read": ActionRisk.LOW,
        "memory_write": ActionRisk.LOW,
    },
    AgentRole.ODIN: {
        "memory_read": ActionRisk.LOW,
        "memory_write": ActionRisk.LOW,
    },
    AgentRole.FREYA: {
        "memory_read": ActionRisk.LOW,
    },
    AgentRole.LOKI: {
        "code_interpreter": ActionRisk.MEDIUM,
        "memory_read": ActionRisk.LOW,
    },
    AgentRole.MIMIR: {
        "memory_read": ActionRisk.LOW,
        "memory_write": ActionRisk.LOW,
    },
    AgentRole.HEIMDALL: {},
}

# ---------------------------------------------------------------------------
# Injection detection patterns
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your\s+instructions)", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+)?different", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous)", re.IGNORECASE),
    re.compile(r"override\s+(safety|rules|constraints)", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
]


class InjectionDetected(Exception):
    """Raised when prompt-injection is detected in untrusted input."""

    def __init__(self, pattern: str, content_snippet: str) -> None:
        self.pattern = pattern
        self.content_snippet = content_snippet
        super().__init__(f"Injection attempt detected: pattern='{pattern}' in '{content_snippet[:80]}'")


class BudgetExhausted(Exception):
    """Raised when resource budget is exhausted."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Budget exhausted: {detail}")


class CapabilityDenied(Exception):
    """Raised when an agent tries to use a tool it lacks permission for."""

    def __init__(self, agent: AgentRole, tool: str) -> None:
        self.agent = agent
        self.tool = tool
        super().__init__(f"Agent {agent.value} lacks capability for tool '{tool}'")


class ApprovalRequired(Exception):
    """Raised when an action needs human/supervisor approval."""

    def __init__(self, request: ToolRequest, reason: str) -> None:
        self.request = request
        self.reason = reason
        super().__init__(f"Approval required for {request.tool_name}: {reason}")


class SelfModificationDenied(Exception):
    """Raised when a self-improvement proposal violates the self-modification policy."""

    def __init__(self, proposal_id: str, reason: str) -> None:
        self.proposal_id = proposal_id
        self.reason = reason
        super().__init__(f"Self-modification denied for {proposal_id}: {reason}")


# ---------------------------------------------------------------------------
# Self-modification policy (Phase 4 — RSIP guardrails)
# ---------------------------------------------------------------------------

# Paths ODIN may NEVER rewrite on its own: the brakes (safety), the exam
# (benchmark), and the engine that enforces gating.  This keeps self-improvement
# from quietly weakening its own constraints (self-degradation).
_PROTECTED_PATHS: tuple[str, ...] = (
    "odin/safety/",
    "odin/improve/benchmark.py",
    "odin/improve/muninn.py",
)


class SelfModificationPolicy(BaseModel):
    """Hard caps on what a self-improvement proposal may change."""

    protected_paths: tuple[str, ...] = _PROTECTED_PATHS
    max_diff_lines: int = 200
    kill_switch: bool = False  # when True, ALL self-modification is denied
    allow_irreversible: bool = False


# ---------------------------------------------------------------------------
# Heimdall gatekeeper
# ---------------------------------------------------------------------------

class Heimdall:
    """Central gatekeeper.  All tool calls pass through gate()."""

    def __init__(
        self,
        budget: BudgetState | None = None,
        auto_approve_up_to: ActionRisk = ActionRisk.MEDIUM,
        capabilities: dict[AgentRole, dict[str, ActionRisk]] | None = None,
        self_mod_policy: SelfModificationPolicy | None = None,
    ) -> None:
        self.budget = budget or BudgetState()
        self._auto_approve_up_to = auto_approve_up_to
        self._capabilities = capabilities or _AGENT_CAPABILITIES
        self.self_mod_policy = self_mod_policy or SelfModificationPolicy()
        self._audit_log: list[dict[str, Any]] = []

    # -- Public API --

    def gate(self, request: ToolRequest) -> ToolRequest:
        """Validate a tool request.  Raises on denial.

        Checks in order:
        1. Budget
        2. Capability / least-privilege
        3. Risk level → approval gate
        4. Argument sanitization (injection check)
        """
        self._check_budget()
        self._check_capability(request)
        self._check_risk(request)
        self._sanitize_arguments(request)
        self.budget.record_tool_call()
        self._log("approved", request)
        return request

    def sanitize_external_content(self, content: str) -> str:
        """Strip injection attempts from retrieved/external text.

        Content is DATA — this escapes or removes instruction-like patterns.
        """
        self._check_injection(content)
        return content

    def check_injection(self, content: str) -> bool:
        """Return True if injection patterns are detected."""
        return any(pattern.search(content) for pattern in _INJECTION_PATTERNS)

    def check_self_modification(self, proposal: ImprovementProposal) -> tuple[bool, str]:
        """Validate a self-improvement proposal against the policy.

        Returns (allowed, reason).  This is the gate that keeps RSIP bounded: it
        cannot touch the safety layer, the benchmark, or the engine itself,
        cannot exceed the diff-size cap, and respects the kill-switch.
        """
        policy = self.self_mod_policy
        target = proposal.target_file.lstrip("./")

        if policy.kill_switch:
            return self._self_mod_verdict(
                proposal, False, "self-improvement kill-switch is engaged"
            )

        for protected in policy.protected_paths:
            if target == protected or target.startswith(protected):
                return self._self_mod_verdict(
                    proposal, False, f"target '{target}' is a protected path ('{protected}')"
                )

        if not policy.allow_irreversible and proposal.risk == ActionRisk.IRREVERSIBLE:
            return self._self_mod_verdict(
                proposal,
                False,
                "irreversible self-modifications require explicit human authorization",
            )

        lines = proposal.diff_line_count()
        if lines > policy.max_diff_lines:
            return self._self_mod_verdict(
                proposal, False, f"diff too large: {lines} lines > cap {policy.max_diff_lines}"
            )

        return self._self_mod_verdict(proposal, True, "within self-modification policy")

    def _self_mod_verdict(
        self, proposal: ImprovementProposal, allowed: bool, reason: str
    ) -> tuple[bool, str]:
        self._audit_log.append(
            {
                "action": "self_mod_allowed" if allowed else "self_mod_denied",
                "detail": reason,
                "target": proposal.target_file,
                "proposal_id": proposal.id,
            }
        )
        return allowed, reason

    def record_llm_call(self, tokens: int) -> None:
        """Record an LLM call against the budget."""
        self.budget.record_llm_call(tokens)
        if self.budget.is_exhausted():
            raise BudgetExhausted("Token/call budget exceeded after LLM call")

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def remaining_budget_summary(self) -> dict[str, Any]:
        b = self.budget
        return {
            "tokens_remaining": b.max_tokens - b.tokens_used,
            "llm_calls_remaining": b.max_llm_calls - b.llm_calls_used,
            "tool_calls_remaining": b.max_tool_calls - b.tool_calls_used,
            "is_exhausted": b.is_exhausted(),
        }

    # -- Internal checks --

    def _check_budget(self) -> None:
        if self.budget.is_exhausted():
            raise BudgetExhausted(
                f"tokens={self.budget.tokens_used}/{self.budget.max_tokens}, "
                f"llm_calls={self.budget.llm_calls_used}/{self.budget.max_llm_calls}, "
                f"tool_calls={self.budget.tool_calls_used}/{self.budget.max_tool_calls}"
            )

    def _check_capability(self, request: ToolRequest) -> None:
        agent_caps = self._capabilities.get(request.requester, {})
        if request.tool_name not in agent_caps:
            self._log("denied_capability", request)
            raise CapabilityDenied(request.requester, request.tool_name)

    def _check_risk(self, request: ToolRequest) -> None:
        risk_order = [ActionRisk.LOW, ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.IRREVERSIBLE]
        request_idx = risk_order.index(request.risk_level)
        threshold_idx = risk_order.index(self._auto_approve_up_to)

        if request_idx > threshold_idx:
            self._log("denied_risk", request)
            raise ApprovalRequired(
                request,
                f"Risk level {request.risk_level.value} exceeds auto-approve threshold "
                f"{self._auto_approve_up_to.value}",
            )

    def _sanitize_arguments(self, request: ToolRequest) -> None:
        for _key, value in request.arguments.items():
            if isinstance(value, str):
                self._check_injection(value)

    def _check_injection(self, content: str) -> None:
        for pattern in _INJECTION_PATTERNS:
            match = pattern.search(content)
            if match:
                self._log("injection_blocked", None, detail=match.group())
                raise InjectionDetected(pattern.pattern, content[:200])

    def _log(
        self,
        action: str,
        request: ToolRequest | None,
        detail: str = "",
    ) -> None:
        entry: dict[str, Any] = {"action": action, "detail": detail}
        if request:
            entry["tool"] = request.tool_name
            entry["agent"] = request.requester.value
            entry["risk"] = request.risk_level.value
        self._audit_log.append(entry)


def make_tool_result_from_error(request: ToolRequest, error: Exception) -> ToolResult:
    """Create a failed ToolResult from a gatekeeper exception."""
    return ToolResult(
        request_id=request.id,
        tool_name=request.tool_name,
        success=False,
        output="",
        error=f"{type(error).__name__}: {error}",
    )
