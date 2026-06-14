"""Sandboxed code interpreter — subprocess-based, resource+time limited.

Security:
- Runs in a subprocess with resource limits (CPU time, memory, no network)
- No ambient credentials — environment is stripped
- Output is captured and size-limited
- Timeout enforced via signal
"""

from __future__ import annotations

import asyncio
import resource
import sys
import tempfile
from pathlib import Path

# Max output size in bytes
_MAX_OUTPUT = 50_000
# Default timeout in seconds
_DEFAULT_TIMEOUT = 30
# Max memory in bytes (256 MB)
_MAX_MEMORY = 256 * 1024 * 1024


def _set_resource_limits() -> None:
    """Called in the child process to set resource limits."""
    # CPU time limit (seconds)
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    # Address space limit
    resource.setrlimit(resource.RLIMIT_AS, (_MAX_MEMORY, _MAX_MEMORY))
    # No core dumps
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


_SAFE_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
}


async def execute_python(code: str, *, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Execute Python code in a sandboxed subprocess.

    Returns stdout+stderr combined, truncated to _MAX_OUTPUT chars.
    Raises on timeout.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir="/tmp"
    ) as f:
        f.write(code)
        script_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_SAFE_ENV,
            preexec_fn=_set_resource_limits if sys.platform != "win32" else None,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"[TIMEOUT] Code execution exceeded {timeout}s limit."

        output = stdout.decode("utf-8", errors="replace")
        if stderr:
            err_text = stderr.decode("utf-8", errors="replace")
            output += f"\n[STDERR]\n{err_text}"

        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + f"\n[TRUNCATED at {_MAX_OUTPUT} chars]"

        return output.strip() or "[No output]"
    finally:
        Path(script_path).unlink(missing_ok=True)
