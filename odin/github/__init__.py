"""BIFRÖST — the bridge to GitHub.

The only sanctioned path by which ODIN's self-improvement reaches the outside
world: scoped, atomic, and (by design) it opens a PR for human review rather
than pushing to a protected branch.
"""

from odin.github.bifrost import Bifrost, FakeBifrost, GhBifrost, PullRequest

__all__ = ["Bifrost", "FakeBifrost", "GhBifrost", "PullRequest"]
