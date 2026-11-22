from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig


def test_hook_operation_and_captured_mutation_callback(tmp_path):
    (tmp_path / 'ui').mkdir()
    (tmp_path / 'schema.graphql').write_text('type Query { status: String }\ntype Mutation { flush: Boolean, reset: Boolean }')
    (tmp_path / 'ui' / 'card.graphql').write_text('query ReadStatus { status }\nmutation FlushCache { flush }\nmutation ResetCache { reset }')
    (tmp_path / 'ui' / 'card.tsx').write_text('''import {useCallback as memo} from "react";
import {useReadStatusQuery, useFlushCacheMutation as useFlush, useResetCacheMutation} from "./card.generated";
function Card() {
    useReadStatusQuery();
    const [flush] = useFlush();
    const [reset] = useResetCacheMutation();
    const submit = memo(() => {
        const mutation = flag ? flush : reset;
        mutation();
    }, [flush, reset]);
    function unrelated(flush: () => void) { flush(); }
    return submit;
}
''')
    def build(enabled):
        return WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(tmp_path),
            repositories=[RepoConfig('web', 'ui')], contract_bindings_v2=enabled)).build()

    old, graph = build(False), build(True)
    parent = 'web/card.tsx:Card'
    submit = parent + '.submit'
    operation = 'graphqlop::ui/card.graphql:mutation:FlushCache'
    assert submit not in old and graph.nodes[submit]['type'] == 'function'
    assert parent + '.var::submit' in old and parent + '.var::submit' in graph
    assert graph.edges[submit, operation, 'apollo::' + operation]['relation'] == 'USES_OPERATION'
    assert graph.edges[submit, 'contract::graphql::Mutation::flush', 'apollo::' + operation]['relation'] == 'CONSUMES'
    assert graph.edges[submit, 'contract::graphql::Mutation::flush', 'apollo::' + operation]['conditional']
    assert graph.has_edge(submit, 'contract::graphql::Mutation::reset')
    assert not graph.has_edge(parent + '.unrelated', operation)
    assert not old.has_edge(parent, 'contract::graphql::Query::status')
    assert graph.has_edge(parent, 'contract::graphql::Query::status')


def test_ambiguous_generated_barrel_is_unbound(tmp_path):
    (tmp_path / 'schema.graphql').write_text('type Query { status: String }')
    for file in ('one.graphql', 'two.graphql'):
        (tmp_path / file).write_text('query ReadStatus { status }')
    (tmp_path / 'panel.tsx').write_text('''import {useReadStatusQuery} from "./generated/graphql";
function Panel() { useReadStatusQuery(); }
''')
    graph = WorkspaceCKGBuilder(WorkspaceConfig(base_dir=str(tmp_path),
        repositories=[RepoConfig('web', '.')], contract_bindings_v2=True)).build()
    assert not graph.has_edge('web/panel.tsx:Panel', 'contract::graphql::Query::status')
