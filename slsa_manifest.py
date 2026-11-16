"""Conservative, unverified SLSA provenance v1 to Build manifest adapter.

This parses source/build/artifact claims; it does NOT validate DSSE signatures,
trusted builder identity, source ownership or provenance completeness.
"""
from __future__ import annotations

import re

_SHA1 = re.compile(r"^[a-fA-F0-9]{40}$")
_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")


def slsa_to_builds(statement: dict, *, repo_id: str, service_name: str,
                   build_id: str) -> list[dict]:
    """Convert a SLSA v1 in-toto statement to manifest build rows.

    Requires exactly one explicit Git source revision in resolvedDependencies.
    Multiple output artifact digests produce distinct, fully specified rows.
    Accepting a statement does not establish its authenticity.
    """
    if not isinstance(statement, dict):
        raise ValueError("SLSA statement must be an object")
    if statement.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise ValueError("expected SLSA provenance v1 predicateType")
    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        raise ValueError("missing SLSA predicate")
    details = predicate.get("runDetails", {})
    builder = details.get("builder", {})
    builder_id = builder.get("id") if isinstance(builder, dict) else None
    metadata = details.get("metadata", {})
    finished = metadata.get("finishedOn") if isinstance(metadata, dict) else None
    definition = predicate.get("buildDefinition", {})
    if not isinstance(definition, dict):
        raise ValueError("invalid buildDefinition")
    deps = definition.get("resolvedDependencies", [])
    if not isinstance(deps, list):
        raise ValueError("invalid resolvedDependencies")
    candidates = set()
    for dependency in deps:
        if not isinstance(dependency, dict):
            raise ValueError("invalid resolved dependency")
        uri = dependency.get("uri", "")
        digest = dependency.get("digest", {})
        if not isinstance(uri, str) or not isinstance(digest, dict):
            raise ValueError("invalid dependency URI or digest")
        # Only accept explicit Git URI, never infer a revision from a tag or branch.
        if "git" in uri.lower():
            revision = digest.get("gitCommit") or digest.get("sha1")
            if isinstance(revision, str) and _SHA1.fullmatch(revision):
                candidates.add(revision.lower())
    if len(candidates) != 1:
        raise ValueError("expected exactly one explicit Git SHA-1 revision")
    if not all(isinstance(x, str) and x.strip() for x in (repo_id, service_name, build_id, builder_id, finished)):
        raise ValueError("missing explicit repository/service/build/builder/timestamp")
    subjects = statement.get("subject", [])
    if not isinstance(subjects, list) or not subjects:
        raise ValueError("SLSA statement requires subjects")
    builds = []
    for idx, subject in enumerate(subjects):
        if not isinstance(subject, dict) or not isinstance(subject.get("digest"), dict):
            raise ValueError("invalid SLSA subject")
        sha = subject["digest"].get("sha256")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise ValueError("subject must have SHA-256 digest")
        builds.append({"id": f"{build_id}-{idx}", "repo_id": repo_id,
                       "service_name": service_name, "commit_sha": next(iter(candidates)),
                       "artifact_digest": "sha256:"+sha.lower(),
                       "builder_id": builder_id, "timestamp": finished})
    return builds
