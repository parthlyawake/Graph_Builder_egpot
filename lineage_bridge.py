"""Evidence-bounded bridge between existing Git lineage and operational revisions.

Checks *local git object existence*, not author identity, CI attestation,
deployment provenance, or telemetry authenticity. The bridge is explicit:
a commit from an unrelated repository must not be matched solely by a short
prefix or a filename.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import networkx as nx

FULL_SHA1 = re.compile(r"^[a-f0-9]{40}$")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode:
        raise ValueError("git repository/commit verification failed: " +
                         (result.stderr or "").strip()[:200])
    return result.stdout.strip()


def bridge_git_lineage(
    graph: nx.MultiDiGraph, *,
    repo_id: str, checkout: str | Path,
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Link a locally existing Git commit to an operational source revision.

    The checkout must be the root of one Git worktree; the caller must provide
    its repository identity. Full (40-char) Git object IDs are checked with
    git cat-file -t; short SHA prefixes are never a proof of identity.
    """
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError("expected networkx.MultiDiGraph")
    if not isinstance(repo_id, str) or not repo_id.strip():
        raise ValueError("repo_id is required")
    root = Path(checkout).resolve(strict=True)
    toplevel = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if root != toplevel:
        raise ValueError("checkout must be the Git worktree root")
    if _git(root, "rev-parse", "--is-shallow-repository") == "true":
        raise ValueError("shallow checkouts cannot establish complete Git ancestry")
    revisions = []
    commits = {}
    for nid, data in graph.nodes(data=True):
        if data.get("type") == "source_revision" and data.get("repo_id") == repo_id:
            sha = data.get("sha")
            if not isinstance(sha, str) or not FULL_SHA1.fullmatch(sha):
                raise ValueError(f"invalid operational Git SHA on {nid}")
            revisions.append((nid, sha))
        if data.get("type") == "commit":
            sha = data.get("sha")
            if not isinstance(sha, str) or not FULL_SHA1.fullmatch(sha.lower()):
                continue
            sha = sha.lower()
            explicit_repo = data.get("repo_id") or data.get("repo")
            if explicit_repo and explicit_repo != repo_id:
                continue
            commits.setdefault(sha, []).append(nid)
    result = graph.copy()
    # This bridge intentionally leaves all unsigned CI and telemetry metadata
    # at their existing reported_unverified labels.
    linked, unmatched = [], []
    for nid, sha in sorted(revisions):
        matches = commits.get(sha, [])
        if len(matches) != 1:
            unmatched.append({"source_revision": nid, "reason": "no_unique_commit_node",
                              "candidate_count": len(matches)})
            continue
        typ = _git(root, "cat-file", "-t", sha)
        if typ != "commit":
            raise ValueError(f"Git object {sha} is not a commit")
        # Do not add a path identity from a different worktree or unverified
        # source location. The supplied checkout and the commit object are the
        # explicit source evidence for this limited identity link.
        commit_nid = matches[0]
        key = f"Loperational:EXACT_GIT_OBJECT:{commit_nid}"
        result.add_edge(nid, commit_nid, key=key,
                        relation="EXACT_GIT_OBJECT", layer="Loperational",
                        verification="git_commit_object_present",
                        repo_id=repo_id, sha=sha)
        linked.append({"source_revision": nid, "commit_node": commit_nid,
                       "sha": sha, "verification": "git_commit_object_present"})
    return result, {"linked": linked, "unmatched": unmatched,
                    "git_checkout": str(root),
                    "limitations": ["Git object existence does not verify build attestation, "
                                    "commit signer, deployment or telemetry authenticity."]}
