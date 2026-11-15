"""Resolve Spring AMQP @Bean wiring with method parameters and local constants."""
from __future__ import annotations

import re


def _string(expr, values):
    expr = expr.strip()
    if len(expr) >= 2 and expr[0] == expr[-1] == '"':
        return expr[1:-1]
    return values.get(expr)


def spring_bindings(clean):
    """Yield queue/exchange/routing/line for explicit Bean construction paths."""
    constants = {}
    for m in re.finditer(
        r"\b(?:final\s+)?(?:static\s+)?(?:final\s+)?String\s+"
        r"([A-Za-z_]\w*)\s*=\s*\"([^\"]+)\"\s*;", clean
    ):
        if m[1] in constants and constants[m[1]] != m[2]:
            constants[m[1]] = None
        else:
            constants[m[1]] = m[2]
    beans = {}
    pattern = (r"\b(Queue|TopicExchange|DirectExchange|FanoutExchange)\s+"
               r"([a-zA-Z_]\w*)\s*\(\s*\)\s*\{\s*"
               r"return\s+new\s+\1\s*\(\s*(\"[^\"]*\"|[A-Za-z_]\w*)")
    for m in re.finditer(pattern, clean):
        value = _string(m[3], constants)
        if value:
            beans[m[2]] = (m[1], value)
    if not beans:
        return
    p = re.compile(
        r"\bBinding\s+\w+\s*\(\s*(?P<params>[^)]{0,200})\)\s*\{\s*"
        r"return\s+BindingBuilder\s*\.\s*bind\s*\(\s*(?P<q>\w+)\s*\)"
        r"\s*\.\s*to\s*\(\s*(?P<ex>\w+)\s*\)"
        r"\s*\.\s*with\s*\(\s*(?P<route>\"[^\"]*\"|[A-Za-z_]\w*)\s*\)",
        re.DOTALL,
    )
    for m in p.finditer(clean):
        parameters = {}
        for typ, identifier in re.findall(
            r"\b(Queue|TopicExchange|DirectExchange|FanoutExchange)\s+(\w+)",
            m["params"]
        ):
            parameters[identifier] = typ

        def bean(name, kind):
            direct = beans.get(name)
            if direct and direct[0] == kind:
                return direct[1]
            if parameters.get(name) != kind:
                return None
            # Typed Bean parameters bind only if a single candidate exists.
            candidates = {v for t, v in beans.values() if t == kind}
            return next(iter(candidates)) if len(candidates) == 1 else None

        queue = bean(m["q"], "Queue")
        exchange_candidates = [bean(m["ex"], t) for t in
                               ("TopicExchange", "DirectExchange", "FanoutExchange")]
        exchange_candidates = {x for x in exchange_candidates if x}
        exchange = (next(iter(exchange_candidates))
                    if len(exchange_candidates) == 1 else None)
        route = _string(m["route"], constants)
        if queue and exchange and route is not None:
            yield queue, exchange, route, clean.count("\n", 0, m.start())+1, "spring_typed_bean_binding"
