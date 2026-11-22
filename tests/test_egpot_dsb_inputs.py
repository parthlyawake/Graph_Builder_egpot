"""Validate the locked DeathStarBench inputs without running any retriever."""

from collections import Counter, defaultdict
from dataclasses import replace

import networkx as nx
import pytest

from bench import egpot_multi_eval as multi


DRAFT_SHA = "2824117d02311d45b8b700c8aa7c93c7c1db20e1b2b04d2cb9e52118803e3945"


def test_query_pairs_and_exact_directed_gold_paths():
    total, all_ids = 0, set()
    for name, prefix, links in (("dsb_social", "sn", 14), ("dsb_media", "mm", 9)):
        repo = multi.REGISTRY[name]
        graph = nx.read_graphml(repo.graph, force_multigraph=True)
        rows = multi.read_json(repo.labels)
        total += len(rows)
        assert len(rows) == 2 * links
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["link_id"]].append(row)
            assert row["id"] == f"{row['link_id']}_{row['type']}"
            assert row["id"] not in all_ids
            all_ids.add(row["id"])
            start, contract, handler = row["gold_path"]
            assert all(node in graph for node in (start, contract, handler))
            assert (start, contract, handler) == (
                row["start_node"], row["contract_node"], row["handler_node"])
            assert row["gold_nodes"] == [contract, handler]
            assert row["path_relations"] == ["CONSUMES->", "<-IMPLEMENTS"]
            assert graph.nodes[contract]["type"] == "rpc_contract"
            assert any(attrs["relation"] == "CONSUMES"
                       for attrs in graph.get_edge_data(start, contract, default={}).values())
            assert any(attrs["relation"] == "IMPLEMENTS"
                       for attrs in graph.get_edge_data(handler, contract, default={}).values())
            assert not row["accepted_alternatives"]
            lookalikes = row.get("lookalike_nodes", [])
            assert lookalikes == sorted(set(lookalikes))
            assert all(node in graph and node not in row["gold_nodes"] for node in lookalikes)
        assert set(grouped) == {f"{prefix}{i:02d}" for i in range(1, links + 1)}
        for pair in grouped.values():
            assert Counter(row["type"] for row in pair) == {"explicit": 1, "indirect": 1}
            assert {tuple(row["gold_path"]) for row in pair} == {tuple(pair[0]["gold_path"])}
    assert total == len(all_ids) == 46


@pytest.mark.parametrize("name", multi.DSB_DATASETS)
def test_provenance_matches_frozen_inputs(name):
    repo = multi.REGISTRY[name]
    hashes = multi.verify_inputs(repo)
    provenance = multi.read_json(repo.provenance)
    label_provenance = multi.read_json(repo.label_provenance)
    config_path = multi.ROOT / provenance["build_config"]
    config = multi.read_json(config_path)
    prereg = repo.preregistration.read_text(encoding="utf-8")
    assert provenance["build_config_sha256"] == multi.sha256(config_path)
    assert config["graphml_sha256"] == hashes["graph"]
    assert config["exclude_nonproduction"] is True
    assert provenance["independent_builds"] == 2
    graph = nx.read_graphml(repo.graph, force_multigraph=True)
    assert (len(graph), graph.number_of_edges()) == (provenance["nodes"], provenance["edges"])
    assert all(meta["label_draft_sha256"] == DRAFT_SHA
               for meta in (provenance, label_provenance, config))
    assert label_provenance["query_sheet_sha256"] == DRAFT_SHA
    assert label_provenance["label_status"] == "source_checked_by_second_model_pending_human_review"
    assert all(checksum in prereg for checksum in (*hashes.values(), DRAFT_SHA))


@pytest.mark.parametrize("name", multi.DSB_DATASETS)
@pytest.mark.parametrize("mode", ("comparison", "regress-ob-dev", "smoke"))
def test_only_the_locked_mode_is_allowed(name, mode, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Mode refusal accessed settings or attempted a run")

    for fn in ("load_settings", "run_locked", "regress_ob_dev", "smoke"):
        monkeypatch.setattr(multi, fn, forbidden)
    with pytest.raises(SystemExit) as exc:
        multi.main(["--repo", name, "--mode", mode])
    assert exc.value.code == 2
    expected = "invalid choice" if mode == "comparison" else "available only in --mode run-locked"
    assert expected in capsys.readouterr().err


@pytest.mark.parametrize("name", multi.DSB_DATASETS)
@pytest.mark.parametrize("untracked", (False, True))
def test_locked_run_requires_a_tracked_preregistration_before_inputs(name, untracked, tmp_path, monkeypatch):
    prereg = tmp_path / "preregistration.md"
    if untracked:
        prereg.touch()
    repo = replace(multi.REGISTRY[name], preregistration=prereg)

    def fake_git(command, *args, **kwargs):
        if command == "ls-files":
            raise multi.subprocess.CalledProcessError(1, "git")
        return "" if command == "status" else "a" * 40

    def forbidden(*args, **kwargs):
        pytest.fail("Missing preregistration reached input verification or evaluation")

    monkeypatch.setattr(multi, "git", fake_git)
    for fn in ("verify_inputs", "load_settings", "run_jobs"):
        monkeypatch.setattr(multi, fn, forbidden)
    message = "must be tracked" if untracked else f"Missing {name} preregistration"
    with pytest.raises(ValueError, match=message):
        multi.run_locked(name, None, workers=1, checkpoint=tmp_path / "jobs",
                         registry={name: repo}, output_dir=tmp_path)
    assert not (tmp_path / "jobs").exists()


def test_locked_plan_has_frozen_policy_methods_budgets_and_seeds():
    locked = multi.load_settings()
    configs = multi.dsb_settings(locked)
    assert configs["edge_policy"] == {
        "excluded_relations": [],
        "no_contract_match_relations": ["ACCEPTS_SCHEMA", "INVOKES", "POSSIBLE_HTTP_TARGET", "RETURNS_SCHEMA"],
        "entropy_over_eligible_only": False,
    }
    assert set(configs["main"]) == {*multi.frozen.FINAL_METHODS, "egpot_full_tiebreak"}
    assert {name: configs["main"][name] for name in locked["main"]} == locked["main"]
    assert all(spec["budgets"] == [10, 20, 40] for spec in configs["main"].values())
    assert configs["main"]["egpot_full_mcts"]["config"].get("lookahead_mode", "blend") == "blend"
    assert configs["main"]["egpot_full_mcts"]["config"]["lookahead_weight"] == 0.5
    for budget in (10, 20, 40):
        assert multi.spec_at(configs["main"]["egpot_full_tiebreak"], budget)["config"] == {
            **multi.spec_at(locked["main"]["egpot_full_mcts"], budget)["config"],
            "lookahead_mode": "tiebreak"}
    assert configs["choke"] == locked["choke"]
    assert set(configs["choke"]) == {
        off for _, off in multi.frozen.CHOKE_PAIRS if off != "egpot_no_choke_point"}
    assert all(not spec["choke_point"] and spec["budgets"] == [20, 40]
               for spec in configs["choke"].values())
    assert configs["weights"] == locked["weights"]
    assert configs["pareto_reference"] == locked["pareto_reference"]
    assert len(configs["weights"]) == 55
    assert set(configs["weights"]) == set(multi.weight_experiment_vectors())
    for name, weights in multi.weight_experiment_vectors().items():
        spec = configs["weights"][name]
        assert spec["budgets"] == [10, 20]
        for budget in spec["budgets"]:
            config = multi.spec_at(spec, budget)["config"]
            assert tuple(config["weights"]) == weights
            assert not config["use_mcts"] and not config["use_pareto"]

    stochastic = {"egpot_full_mcts", "egpot_full_tiebreak", "egpot_no_pareto_mcts",
                  "mcts_standard", "mcts_standard_no_choke"}
    assert set(configs["seeds"]) == stochastic
    for name, seed_specs in configs["seeds"].items():
        assert {str(i) for i in range(6)} == set(seed_specs)
        assert {seed: seed_specs[seed] for seed in locked["seeds"].get(name, {})} == locked["seeds"].get(name, {})
        for seed, spec in seed_specs.items():
            assert spec["budgets"] == [20, 40]
            assert all(multi.spec_at(spec, budget)["config"]["seed"] == int(seed)
                       for budget in spec["budgets"])
    label = multi.read_json(multi.REGISTRY["dsb_social"].labels)[0]
    jobs, aliases = multi.plan_locked([label], configs)
    # Seed-zero and Pareto-reference rows reuse main or choke jobs.
    assert len(jobs) == 220
    assert Counter(alias["experiment"] for alias in aliases) == {
        "main": 48, "choke": 12, "weights": 110, "seeds": 60, "pareto_reference": 2}
    assert {task["budget"] for task in jobs} == {10, 20, 40}
    assert {alias["split"] for alias in aliases} == {"all"}


def test_seed_summary_reports_median_range_and_defined_seed_count():
    rows = [
        {"experiment": "seeds", "method": "mcts_standard", "budget": 40, "seed": seed,
         "hit_count": seed, "hit": seed / 5, "gold_recall": seed / 5, "precision": seed / 10,
         "path_coverage": seed / 5, "ordered_path_match": seed / 5, "nodes_returned": 40,
         "nodes_to_hit": seed + 2 if seed else None,
         "precision_at_hit": 2 / (seed + 2) if seed else None, "latency_s": seed / 2}
        for seed in range(6)
    ]
    result, = multi.dsb_seed_summary([*rows, {**rows[0], "experiment": "main"}])
    assert result["primary_seed"] == 0
    assert result["metrics"]["hit_count"] == {"median": 2.5, "min": 0, "max": 5, "defined_seeds": 6}
    assert result["metrics"]["nodes_to_hit"] == {"median": 5, "min": 3, "max": 7, "defined_seeds": 5}
