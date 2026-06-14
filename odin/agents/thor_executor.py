"""THOR — The Executor.

Receives PlanNodes from ODIN, executes them using tools (via HEIMDALL),
and returns results.  THOR never approves its own actions — that's
HEIMDALL's job.  THOR never plans — that's ODIN's job.

Phase 1 tools: code_interpreter, web_search.
"""

from __future__ import annotations

from odin.agents.base import BaseAgent
from odin.routing.llm_adapter import LLMAdapter, LLMMessage
from odin.schemas import AgentMessage, AgentRole, PlanNode
from odin.tools.registry import ToolRegistry

_SYSTEM_PROMPT = """\
You are THOR, an executor agent. You receive a task and must complete it using
available tools. You respond with:
1. Your reasoning about how to approach the task.
2. If a tool is needed, specify which tool and what arguments.
3. Your final answer/output after tool execution.

Available tools: code_interpreter (run Python code), web_search (search the web).

Format your response as:
REASONING: <your step-by-step thinking>
TOOL: <tool_name> (or "none" if no tool needed)
TOOL_INPUT: <input for the tool>
ANSWER: <your final answer>

Be precise and thorough.  Your output will be verified.
"""


class ThorExecutor(BaseAgent):
    """Executes plan steps using tools, gated through HEIMDALL."""

    role = AgentRole.THOR
    system_prompt = _SYSTEM_PROMPT

    def __init__(self, llm: LLMAdapter, tools: ToolRegistry) -> None:
        super().__init__(llm)
        self._tools = tools

    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Execute a delegated task."""
        result = await self.execute_step(message.content)
        return self._make_response(to=AgentRole.ODIN, content=result)

    async def execute_step(self, task: str, tool_hint: str | None = None) -> str:
        """Execute a single plan step.

        1. Ask LLM how to approach the task
        2. If tool is needed, execute it through the registry (HEIMDALL gates)
        3. Synthesize the answer
        """
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=f"Execute this task:\n\n{task}"),
        ]

        resp = await self._llm.complete(messages, temperature=0.2)
        output = resp.content

        # Parse tool request from LLM output
        tool_name = self._extract_field(output, "TOOL")
        tool_input = self._extract_field(output, "TOOL_INPUT")

        if tool_name and tool_name.lower() not in ("none", ""):
            actual_tool = tool_hint if tool_hint and tool_hint != "none" else tool_name

            if actual_tool == "code_interpreter" and tool_input:
                result = await self._tools.execute(
                    "code_interpreter",
                    {"code": tool_input},
                    AgentRole.THOR,
                )
                if result.success:
                    # Re-prompt with tool output
                    messages.append(LLMMessage(role="assistant", content=output))
                    messages.append(
                        LLMMessage(
                            role="user",
                            content=f"Tool output:\n{result.output}\n\nProvide your final ANSWER based on this output.",
                        )
                    )
                    final = await self._llm.complete(messages, temperature=0.1)
                    return final.content
                else:
                    return f"Tool execution failed: {result.error}\n\nOriginal reasoning:\n{output}"

            elif actual_tool == "web_search" and tool_input:
                result = await self._tools.execute(
                    "web_search",
                    {"query": tool_input},
                    AgentRole.THOR,
                )
                if result.success:
                    messages.append(LLMMessage(role="assistant", content=output))
                    messages.append(
                        LLMMessage(
                            role="user",
                            content=f"Search results:\n{result.output}\n\nProvide your final ANSWER based on these results.",
                        )
                    )
                    final = await self._llm.complete(messages, temperature=0.1)
                    return final.content
                else:
                    return f"Search failed: {result.error}\n\nOriginal reasoning:\n{output}"

        # No tool needed or tool not recognized — return LLM output directly
        answer = self._extract_field(output, "ANSWER")
        return answer if answer else output

    async def execute_node(self, node: PlanNode) -> str:
        """Execute a PlanNode — convenience wrapper."""
        return await self.execute_step(node.goal, tool_hint=node.tool_hint)

    @staticmethod
    def _extract_field(text: str, field: str) -> str:
        """Extract a field value from structured LLM output."""
        marker = f"{field}:"
        lines = text.split("\n")
        collecting = False
        parts: list[str] = []
        for line in lines:
            if line.strip().upper().startswith(marker.upper()):
                collecting = True
                # Take the rest of the line after the marker
                rest = line.strip()[len(marker):].strip()
                if rest:
                    parts.append(rest)
            elif collecting:
                # Stop at the next field marker
                if any(line.strip().upper().startswith(f"{f}:") for f in ("REASONING", "TOOL", "TOOL_INPUT", "ANSWER")):
                    if line.strip().upper().startswith(f"{field}:".upper()):
                        continue
                    break
                parts.append(line)
        return "\n".join(parts).strip()
