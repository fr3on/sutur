"""Stage ordering: a dependency graph over task names."""

from __future__ import annotations

from collections.abc import Iterable

from ..errors import GraphError
from ..tasks.registry import Registry


def _ancestors(name: str, registry: Registry) -> list[str]:
    seen: list[str] = []
    stack = list(registry.get(name).requires)
    while stack:
        dep = stack.pop(0)
        if dep not in seen:
            registry.get(dep)
            seen.append(dep)
            stack.extend(registry.get(dep).requires)
    return seen


def order(names: Iterable[str], registry: Registry, with_deps: bool = False) -> list[str]:
    """The stages to run, prerequisites first.

    Only the selected stages run; a `requires` edge to a stage that is not selected is assumed satisfied (its output is on disk) unless
    `with_deps` is set, which pulls the missing prerequisites in. Ties keep the order the caller gave. Cycles are an error.
    """
    wanted = list(dict.fromkeys(names))
    for n in wanted:
        registry.get(n)   # unknown stage -> GraphError
    nodes = list(wanted)
    if with_deps:
        i = 0
        while i < len(nodes):
            for dep in registry.get(nodes[i]).requires:
                registry.get(dep)
                if dep not in nodes:
                    nodes.append(dep)
            i += 1
    # an edge runs from a stage to every selected stage it needs, directly or through stages that are not selected (vision needs textscan needs draw)
    edges = {n: [d for d in _ancestors(n, registry) if d in nodes] for n in nodes}
    done: list[str] = []
    visiting: set[str] = set()

    def visit(n: str) -> None:
        if n in done:
            return
        if n in visiting:
            raise GraphError(f"stages depend on each other in a loop at {n!r}")
        visiting.add(n)
        for d in edges[n]:
            visit(d)
        visiting.discard(n)
        done.append(n)

    for n in nodes:
        visit(n)
    return done
