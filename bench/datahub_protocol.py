"""The DataHub draft job matrix, constructed without DataHub inputs."""
from copy import deepcopy

import networkx as nx

from bench import egpot_eval as ev, egpot_multi_eval as locked
from bench.egpot_test_splits import configs_for


def settings():
    # The existing mixed-width spec factory needs only a graph to introspect
    # constructor defaults. No methods run and there are no queries here.
    graph = nx.MultiDiGraph()
    graph.add_node('protocol-config')
    result = configs_for(graph)
    main = result['main']
    main['egpot_no_pareto_mcts_w4'] = locked._override_config(main['egpot_full_mcts_w4'], use_pareto=False)
    result['seeds']['egpot_no_pareto_mcts_w4'] = {
        str(seed): locked._override_config(main['egpot_no_pareto_mcts_w4'], seed=seed) for seed in range(6)}
    reference = deepcopy(main['egpot_full_w4'])
    reference['budgets'] = [10, 20]
    result['pareto_reference'] = reference
    result['pareto_reference_method'] = 'egpot_full_w4'
    result['weights'] = {name: locked._override_config(reference, weights=vector, use_pareto=False)
                         for name, vector in ev.weight_experiment_vectors().items()}
    return result
