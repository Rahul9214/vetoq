"""Pure, bounded in-memory graph analysis for one run's content lineage.

Every function works on rows already loaded under the node and edge caps, so the work is
bounded by those caps. There is no recursion, no database access, and no content body.
"""

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from vetoq.lineage_model import IntegrityCode, Traversal

Edge = tuple[str, str]


@dataclass(frozen=True, slots=True)
class GraphAnalysis:
    anomalies: tuple[tuple[IntegrityCode, str], ...]
    max_depth: int


def _adjacency(
    nodes: Iterable[str], edges: Sequence[Edge]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    known = set(nodes)
    children: dict[str, list[str]] = {node: [] for node in known}
    parents: dict[str, list[str]] = {node: [] for node in known}
    for parent, child in edges:
        if parent in known and child in known:
            children[parent].append(child)
            parents[child].append(parent)
    return children, parents


def _cyclic(children: Mapping[str, Sequence[str]]) -> set[str]:
    """Members of a cycle, by an iterative Tarjan strongly-connected-components pass."""

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    members: set[str] = set()
    counter = 0
    for start in sorted(children):
        if start in index:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            node, cursor = work.pop()
            if cursor == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            successors = children[node]
            descended = False
            while cursor < len(successors):
                successor = successors[cursor]
                cursor += 1
                if successor not in index:
                    work.append((node, cursor))
                    work.append((successor, 0))
                    descended = True
                    break
                if successor in on_stack:
                    low[node] = min(low[node], index[successor])
            if descended:
                continue
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in children[node]:
                    members.update(component)
    return members


def analyze_graph(
    derived: Mapping[str, bool],
    edges: Sequence[Edge],
    root: str | None,
) -> GraphAnalysis:
    """Find orphan, cyclic, and unreachable nodes. `derived` maps node id to is-derived."""

    children, parents = _adjacency(derived, edges)
    anomalies: list[tuple[IntegrityCode, str]] = []
    flagged: set[str] = set()
    for node in sorted(derived):
        if derived[node] and not parents[node]:
            anomalies.append(("orphan_derived_node", node))
            flagged.add(node)
    for node in sorted(_cyclic(children)):
        anomalies.append(("edge_cycle", node))
        flagged.add(node)
    depth = 0
    if root is not None and root in derived:
        seen = {root: 0}
        queue: deque[str] = deque([root])
        while queue:
            node = queue.popleft()
            for child in children[node]:
                if child not in seen:
                    seen[child] = seen[node] + 1
                    queue.append(child)
        depth = max(seen.values())
        for node in sorted(set(derived) - set(seen) - flagged):
            anomalies.append(("unreachable_node", node))
    return GraphAnalysis(anomalies=tuple(anomalies), max_depth=depth)


def traverse(
    edges: Sequence[Edge],
    nodes: Iterable[str],
    start: str,
    direction: Literal["ancestors", "descendants"],
    max_depth: int,
    max_nodes: int,
) -> Traversal:
    """Walk ancestors or descendants with a visited set, a depth bound, and a node cap.

    The start node is not part of the result. `truncated` is true whenever the bound left
    a reachable node out, so a caller can never mistake a clipped walk for a complete one.
    """

    children, parents = _adjacency(nodes, edges)
    step = parents if direction == "ancestors" else children
    seen = {start}
    found: list[tuple[str, int]] = []
    truncated = False
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        for neighbour in step.get(node, ()):
            if neighbour in seen:
                continue
            if depth + 1 > max_depth or len(found) >= max_nodes:
                truncated = True
                continue
            seen.add(neighbour)
            found.append((neighbour, depth + 1))
            queue.append((neighbour, depth + 1))
    return Traversal(start=start, direction=direction, nodes=tuple(found), truncated=truncated)
