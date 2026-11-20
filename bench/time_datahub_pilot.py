"""Time methods on synthetic DataHub probes. Returned results are discarded."""
import json
from collections import defaultdict
import random
from pathlib import Path
import sys
from statistics import fmean
from time import perf_counter

import networkx as nx

from bench import egpot_eval as ev
from bench.datahub_inputs import GRAPH, ROOT, graph_records, write_json
from bench.egpot_multi_eval import DSB_EDGE_POLICY
from bench.egpot_width_sweep_dev import guard
from eg_pot import EGPOTConfig, GraphView, QueryScorer


PROBES = (('web/', 'render descriptive catalog information'),
          ('ingestion/', 'convert a source record for ingestion'),
          ('graphql/', 'prepare the request execution context'))
BUDGETS = (10, 20, 40)


def load_graph(path=GRAPH):
    graph = nx.MultiDiGraph()
    for kind, key, attrs in graph_records(path):
        if kind == 'node':
            graph.add_node(key[0], **attrs)
        else:
            u, v, key = key
            if key is not None:
                try:
                    key = int(key)
                except ValueError:
                    pass
            graph.add_edge(u, v, key, **attrs)
    return graph


def choose_probes(graph, excluded):
    rng = random.Random(0)
    probes = []
    for number, (prefix, query) in enumerate(PROBES, 1):
        options = sorted(n for n, data in graph.nodes(data=True) if n.startswith(prefix)
                         and n not in excluded and data.get('type') == 'function'
                         and 5 <= graph.degree(n) <= 60)
        probes.append({'id': f'probe-{number}', 'start': rng.choice(options), 'query': query})
    return probes


def pilot():
    audit = json.loads((ROOT / 'bench/results/datahub_coverage_v2.json').read_text(encoding='utf8'))
    excluded = {r[k]['id'] for r in audit['links'] for k in ('caller', 'handler', 'contract')}
    start = perf_counter()
    graph = load_graph()
    graph_seconds = perf_counter() - start
    probes = choose_probes(graph, excluded)
    assert not {r['start'] for r in probes} & excluded
    print('Loaded graph and selected off-cohort probes', round(graph_seconds, 3), flush=True)
    view = GraphView(graph, edge_policy=DSB_EDGE_POLICY)
    start = perf_counter()
    scorer = QueryScorer(view)
    scorer_seconds = perf_counter() - start
    methods = {
        'egpot_full_w4': lambda: ev.EGPOTRetriever(EGPOTConfig(beam_width=4, use_mcts=False), view, scorer),
        'egpot_full_w12': lambda: ev.EGPOTRetriever(EGPOTConfig(beam_width=12, use_mcts=False), view, scorer),
        'egpot_full_mcts_w4': lambda: ev.EGPOTRetriever(EGPOTConfig(beam_width=4, use_mcts=True), view, scorer),
        'community_graphrag': lambda: ev.CommunityGraphRAG(view, scorer),
        'ppr': lambda: ev.PersonalizedPageRank(view, scorer),
        'mcts_standard': lambda: ev.StandardMCTS(view, scorer, seed=0,
            query_ids={(r['query'], r['start']): r['id'] for r in probes}),
    }
    records, constructors = [], {}
    for name, make in methods.items():
        print('Timing', name, flush=True)
        start = perf_counter()
        engine = make()
        constructors[name] = perf_counter() - start
        for row in probes:
            for budget in BUDGETS:
                start = perf_counter()
                engine.retrieve(row['query'], row['start'], budget)
                records.append({'method': name, 'probe': row['id'], 'budget': budget,
                                'seconds': perf_counter() - start})
        del engine
    print('Timing 54-vector study and equal control', flush=True)
    for name, vector in ev.weight_experiment_vectors().items():
        start = perf_counter()
        engine = ev.EGPOTRetriever(EGPOTConfig(use_mcts=False, use_pareto=False, weights=vector), view, scorer)
        constructors[name] = perf_counter() - start
        for row in probes:
            for budget in (10, 20):
                start = perf_counter()
                engine.retrieve(row['query'], row['start'], budget)
                records.append({'method': name, 'probe': row['id'], 'budget': budget,
                                'seconds': perf_counter() - start})
    return dict(probes=probes, records=records, graph_load_seconds=graph_seconds,
                scorer_seconds=scorer_seconds, constructor_seconds=constructors)


def main():
    active = True

    def hook(event, values):
        if active:
            guard(event, values)

    sys.addaudithook(hook)
    try:
        report = pilot()
    finally:
        active = False
    result = Path('bench/results/datahub_timing_pilot.json')
    write_json(result, report)
    result.with_suffix('.md').write_text(render_projection(report), encoding='utf8', newline='\n')


def render_projection(report):
    from bench.datahub_protocol import settings
    from bench.egpot_multi_eval import plan_locked
    from bench.map_datahub_coverage import markdown_table

    slots = defaultdict(list)
    for row in report['records']:
        method = row['method']
        if method.startswith(('emphasis_', 'dirichlet_')):
            method = '54-vector study'
        slots[method, row['budget']].append(row['seconds'])
    pilot_counts = {'54-vector study': 54}
    stochastic = {'egpot_full_mcts_w4', 'mcts_standard'}
    rows, planned_total, blanket_total = [], 0, 0
    for method in sorted({k[0] for k in slots}):
        means = {b: fmean(slots[method, b]) for b in BUDGETS if slots.get((method, b))}
        vectors = pilot_counts.get(method, 1)
        repeats = 6 if method in stochastic else 1
        planned = 52 * repeats * vectors * sum(means.values())
        blanket = 52 * 6 * vectors * sum(means.values())
        planned_total += planned
        blanket_total += blanket
        range_samples = [v for b in means for v in slots[method,b]]
        init = (sum(s for name,s in report['constructor_seconds'].items()
                    if name.startswith(('emphasis_', 'dirichlet_'))) if vectors == 54
                else report['constructor_seconds'][method])
        rows.append((method, *(f'{means[b]:.3f}' if b in means else '—' for b in BUDGETS),
                     f'{min(range_samples):.3f}–{max(range_samples):.3f}', f'{init:.2f}',
                     f'{planned / 3600:.3f}', f'{blanket / 3600:.3f}'))
    dummy = dict(id='config-only',link_id='not-a-real-link',type='explicit',query='',
                 start_node='config-only',gold_nodes=[],gold_path=[])
    jobs, aliases = plan_locked([dummy], settings())
    proxy_total = 0
    for task in jobs:
        method, budget = task['method'], task['budget']
        if (method, budget) not in slots:
            if method.startswith(('emphasis_', 'dirichlet_')):
                method = '54-vector study'
            elif task['spec']['class'] == 'EGPOTRetriever':
                config = task['spec']['config']
                method = ('egpot_full_mcts_w4' if config['use_mcts']
                          else f"egpot_full_w{config['beam_width']}")
            elif method == 'ppr_no_choke':
                method = 'ppr'
            else:
                method = 'mcts_standard'
        proxy_total += 52 * fmean(slots[method, budget])
    lines = ['# DataHub off-cohort timing pilot', '',
             'Three start functions were drawn using `random.Random(0)`, one per listed namespace, from sorted function IDs '
             'with multigraph degree 5–60 after excluding every labeled start, contract, and handler. Each start received one '
             'synthetic prompt. Calls used the whole graph and policy D. Every returned result was discarded.', '']
    lines += markdown_table(['Probe','Start','Synthetic prompt'], (
        (r['id'], f"`{r['start']}`", r['query']) for r in report['probes']))
    lines += [f"Graph load {report['graph_load_seconds']:.2f} s. TF-IDF setup {report['scorer_seconds']:.2f} s. "
              'The columns below show means over the three probes at each budget, and the full observed retrieval range. '
              'Constructor time is shown separately. Weight means are per vector and weight setup is summed over 54 constructors.', '']
    lines += markdown_table(['Method','@10 sec','@20 sec','@40 sec','Range sec','Setup sec',
                             'Declared plan hours','All six repeats hours'], rows)
    lines += [f'Measured methods project to **{planned_total/3600:.2f} serial retrieval hours** on the declared plan, '
              f'or **{blanket_total/3600:.2f} hours** if all were repeated six times. Weights use their two declared budgets. '
              'These totals exclude common setup, worker startup, checkpoint overhead, and unmeasured variants and side runs. '
              f'The full draft job matrix would contain {52*len(jobs):,} unique calls and {52*len(aliases):,} reporting rows. '
              f'A coarse full-plan scenario is **{proxy_total/3600:.2f} serial retrieval hours**. It uses blended width-4 '
              'MCTS as the proxy for untimed lookahead variants, same-width plain EG-POT for other EG-POT ablations, '
              'and standard MCTS for untimed baselines except choke-off PPR, which uses PPR. This is a planning scenario '
              'and omits initialization and I/O. Width-12 lookahead is still an important unknown.', '',
              'Blended EG-POT MCTS is impractical for a short single-worker run. Its measured projection alone is over seven hours, '
              'and the tiebreak and no-Pareto MCTS variants remain untimed. The weight study is roughly 40 serial minutes. '
              'PPR costs several seconds per call. Community GraphRAG has the greatest measured constructor cost. '
              'The small, degree-limited sample cannot bound worst-case calls.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
