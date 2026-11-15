"""Strictly token-bounded, deterministic context assembly.

The unit of the budget is cl100k_base tokens, not a whitespace estimate.
No network requests or model calls are made. Context can be truncated only
at the root when the requested budget is smaller than the root header.
"""
from __future__ import annotations


def pack_context(graph, root, candidates, relations, max_tokens, *,
                 encoding_name="cl100k_base"):
    if not isinstance(max_tokens, int) or max_tokens < 1:
        raise ValueError("max_tokens must be a positive integer")
    import tiktoken
    encoder = tiktoken.get_encoding(encoding_name)
    root_data = graph.nodes[root]
    source = root_data.get("code") or root_data.get("docstring") or root
    prefix = (
        f"=== TARGET FOCUS [{root_data.get('type', 'entity').upper()}] {root} ===\n"
        f"File: {root_data.get('file', 'unknown')}:{root_data.get('line_no', '?')}\n"
        f"Docstring: {root_data.get('docstring', 'None')}\n"
    )
    root_block = prefix + str(source)
    original_root_tokens = len(encoder.encode(root_block))
    if original_root_tokens > max_tokens:
        # An exact BPE budget, including the root node when only a prefix fits.
        root_block = encoder.decode(encoder.encode(root_block)[:max_tokens])
        while len(encoder.encode(root_block)) > max_tokens and root_block:
            root_block = root_block[:-1]
    blocks = [root_block]
    selected = {root}
    skipped = []
    for node_id in sorted(set(candidates) - {root}):
        if node_id not in graph:
            continue
        node = graph.nodes[node_id]
        kind = node.get("type", "node")
        code = node.get("code") or ""
        if not code and kind.endswith("_contract"):
            code = (f"rpc {node.get('name')}({node.get('request_type', '')}) "
                    f"returns ({node.get('response_type', '')})")
        snippet = str(code)[:400]
        block = f"--- [{kind.upper()}] {node_id} ---\n{snippet}"
        candidate_text = "\n\n".join([*blocks, block])
        if len(encoder.encode(candidate_text)) <= max_tokens:
            blocks.append(block)
            selected.add(node_id)
        else:
            skipped.append(node_id)
    context = "\n\n".join(blocks)
    actual = len(encoder.encode(context))
    if actual > max_tokens:
        raise AssertionError("Grafting exceeded exact encoded token budget")
    included_edges = [
        entry for entry in relations
        if entry["source"] in selected and entry["target"] in selected
    ]
    # Preserve discovery order but eliminate duplicate relationships.
    seen, unique_edges = set(), []
    for edge in included_edges:
        key = (edge["source"], edge["target"],
               edge.get("relation"), edge.get("layer"))
        if key not in seen:
            seen.add(key)
            unique_edges.append(edge)
    unique_edges.sort(key=lambda edge: (
        edge["source"], edge["target"], str(edge.get("relation", "")),
        str(edge.get("layer", "")),
    ))
    return {
        "root": root,
        "selected_nodes": sorted(selected),
        "node_count": len(selected),
        "edge_count": len(unique_edges),
        "approx_tokens": actual,  # legacy field; actual count is now exact
        "bpe_tokens": actual,
        "token_budget": max_tokens,
        "relations": unique_edges,
        "grafted_context": context,
        "truncated": original_root_tokens > max_tokens or bool(skipped),
        "omitted_nodes": skipped,
        "encoding": encoding_name,
    }
