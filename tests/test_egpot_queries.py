"""Read-only validation of the 30 source-backed Online Boutique queries."""

from collections import Counter, defaultdict
import json
from pathlib import Path
import re

import networkx as nx
import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("C:/dev/microservices-demo")
EXPECTED_INDIRECT = {
    1: "Which service supplies the available currency choices for display?",
    2: "Which service turns a price in one currency into another when a shopper changes the display currency?",
    3: "Which service returns the full catalog of items shown on the home page?",
    4: "Which service looks up the details of a single item on a product page?",
    5: "Which service returns the items a shopper currently has in their basket?",
    6: "Which service stores a newly selected product in the shopper's basket?",
    7: "Which service removes everything from a shopper's basket?",
    8: "Which service suggests other products a shopper might like?",
    9: "Which service estimates the delivery cost for the items in a basket?",
    10: "Which service picks the advertisement text shown on a page?",
    11: "Which service takes the card details and completes the payment for an order?",
    12: "Which service notifies the customer by email after an order is placed?",
    13: "Which service arranges dispatch and returns a tracking number once an order is paid?",
    14: "Which service does the order-placement flow ask for the shipping price when totalling an order?",
    15: "Which service does the order-placement flow use to express item prices in the customer's chosen currency?",
}
EXPECTED_LINKS = [
    ("frontend", "getCurrencies", "CurrencyService.GetSupportedCurrencies"),
    ("frontend", "convertCurrency", "CurrencyService.Convert"),
    ("frontend", "getProducts", "ProductCatalogService.ListProducts"),
    ("frontend", "getProduct", "ProductCatalogService.GetProduct"),
    ("frontend", "getCart", "CartService.GetCart"),
    ("frontend", "insertCart", "CartService.AddItem"),
    ("frontend", "emptyCart", "CartService.EmptyCart"),
    ("frontend", "getRecommendations", "RecommendationService.ListRecommendations"),
    ("frontend", "getShippingQuote", "ShippingService.GetQuote"),
    ("frontend", "getAd", "AdService.GetAds"),
    ("checkoutservice", "chargeCard", "PaymentService.Charge"),
    ("checkoutservice", "sendOrderConfirmation", "EmailService.SendOrderConfirmation"),
    ("checkoutservice", "shipOrder", "ShippingService.ShipOrder"),
    ("checkoutservice", "quoteShipping", "ShippingService.GetQuote"),
    ("checkoutservice", "convertCurrency", "CurrencyService.Convert"),
]


@pytest.fixture(scope="module")
def labels():
    with (ROOT / "bench/labels/online_boutique_egpot_queries.json").open(encoding="utf-8") as stream:
        return json.load(stream)


@pytest.fixture(scope="module")
def graph():
    return nx.read_graphml(ROOT / "bench/results/online_boutique_graph_fresh.graphml", force_multigraph=True)


def test_unique_ids_and_paired_links(labels):
    assert isinstance(labels, list) and len(labels) == 30
    assert Counter(row["type"] for row in labels) == {"explicit": 15, "indirect": 15}
    assert len({row["id"] for row in labels}) == len(labels)
    links = defaultdict(list)
    for row in labels:
        assert type(row["link_id"]) is int and 1 <= row["link_id"] <= 15
        assert row["type"] in {"explicit", "indirect"}
        assert row["id"] == f"ob{row['link_id']:02d}_{row['type']}"
        links[row["link_id"]].append(row)
    assert set(links) == set(EXPECTED_INDIRECT)
    for pair in links.values():
        assert sorted(row["type"] for row in pair) == ["explicit", "indirect"]
        for key in ("start_node", "contract_node", "handler_node", "gold_nodes", "gold_path",
                    "path_relations", "evidence", "service_start", "service_handler", "accepted_alternatives"):
            assert pair[0][key] == pair[1][key]


def test_nodes_and_path_bindings(labels, graph):
    for row in labels:
        start = row["start_node"]
        assert len(row["gold_nodes"]) == 2
        contract, handler = row["contract_node"], row["handler_node"]
        assert row["gold_nodes"] == [contract, handler]
        assert all(node in graph for node in (start, contract, handler))
        assert graph.nodes[start]["type"] == graph.nodes[handler]["type"] == "function"
        assert graph.nodes[contract]["type"] == "rpc_contract"
        assert start not in row["gold_nodes"]
        assert len(set(row["gold_nodes"])) == 2
        path = row["gold_path"]
        assert path == [start, contract, handler]
        assert all(node in graph for node in path)
        assert len(row["path_relations"]) == len(path) - 1
        assert row["path_relations"] == ["CONSUMES->", "<-IMPLEMENTS"]
        for source, target, edge in zip(path, path[1:], row["path_relations"]):
            if edge.endswith("->"):
                u, v, relation = source, target, edge[:-2]
            else:
                assert edge.startswith("<-")
                u, v, relation = target, source, edge[2:]
            assert any(data.get("relation") == relation
                       for data in graph.get_edge_data(u, v, default={}).values())
        assert any(data.get("relation") == "CONSUMES"
                   for data in graph.get_edge_data(start, contract, default={}).values())
        assert any(data.get("relation") == "IMPLEMENTS"
                   for data in graph.get_edge_data(handler, contract, default={}).values())
        repo, caller_name, rpc = EXPECTED_LINKS[row["link_id"] - 1]
        assert graph.nodes[start]["repo"] == row["service_start"] == repo
        assert graph.nodes[start]["name"] == caller_name
        assert contract == "contract::" + rpc
        assert row["service_handler"] == graph.nodes[handler]["repo"]
        assert row["service_handler"] == rpc.split(".")[0].lower()


def test_query_text_and_no_indirect_symbol_leak(labels, graph):
    for row in labels:
        contract, handler = row["gold_nodes"]
        rpc = graph.nodes[contract]["name"]
        caller = graph.nodes[row["start_node"]]["name"]
        if row["type"] == "explicit":
            assert row["query"] == f"In Online Boutique, where is {rpc} implemented for {caller}?"
        else:
            assert row["query"] == EXPECTED_INDIRECT[row["link_id"]]
            query = row["query"].casefold()
            for symbol in (rpc, graph.nodes[handler]["name"], caller):
                assert symbol and symbol.casefold() not in query


def test_source_evidence_points_to_stub_calls_and_definitions(labels, graph):
    for row in labels:
        evidence = row["evidence"]
        assert evidence["basis"] == "source"
        for role, node in (("caller", row["start_node"]), ("handler", row["handler_node"])):
            location, line = evidence[role].rsplit(":", 1)
            assert location == "src/" + graph.nodes[node]["file"]
            full_path = (SOURCE / location).resolve()
            assert full_path.is_relative_to(SOURCE.resolve())
            lines = full_path.read_text(encoding="utf-8").splitlines()
            number = int(line)
            assert 1 <= number <= len(lines)
            text = lines[number - 1]
            symbol = re.escape(graph.nodes[node]["name"])
            if role == "caller":
                rpc = re.escape(graph.nodes[row["contract_node"]]["name"])
                assert re.search(r"\b" + rpc + r"\s*\(", text)
                service = row["contract_node"].split("::", 1)[1].split(".")[0]
                assert f"New{service}Client(" in "\n".join(lines[max(0, number - 3):number])
                # The call evidence must be inside the named Go caller, not a
                # different same-service stub invocation elsewhere in the file.
                headers = [(i + 1, value) for i, value in enumerate(lines)
                           if re.match(r"^func\s", value) and i + 1 <= number]
                assert re.search(r"\)\s+" + symbol + r"\s*\(", headers[-1][1])
            else:
                patterns = {
                    ".py": r"^\s*def\s+" + symbol + r"\s*\(",
                    ".go": r"^\s*func\s+\([^)]*\)\s+" + symbol + r"\s*\(",
                    ".js": r"^\s*(?:function\s+|static\s+)?" + symbol + r"\s*\(",
                    ".cs": r"^\s*public\b.*\boverride\b.*\b" + symbol + r"\s*\(",
                    ".java": r"^\s*public\b.*\b" + symbol + r"\s*\(",
                }
                assert re.search(patterns[full_path.suffix], text)
                if row["link_id"] == 10:
                    assert number == 94  # declaration, not @Override at 93


def test_email_alternative_is_informational_and_dummy_is_gold(labels, graph):
    dummy = "emailservice/email_server.py:DummyEmailService.SendOrderConfirmation"
    alternative = "emailservice/email_server.py:EmailService.SendOrderConfirmation"
    for row in labels:
        assert set(row["accepted_alternatives"]).isdisjoint(row["gold_nodes"])
        assert set(row["accepted_alternatives"]).isdisjoint(row["gold_path"])
        if row["link_id"] == 12:
            assert row["handler_node"] == dummy
            assert row["accepted_alternatives"] == [alternative]
            assert alternative in graph
            assert any(data.get("relation") == "IMPLEMENTS" for data in
                       graph.get_edge_data(alternative, row["contract_node"], default={}).values())
        else:
            assert row["accepted_alternatives"] == []
    lines = (SOURCE / "src/emailservice/email_server.py").read_text(encoding="utf-8").splitlines()
    assert "service = DummyEmailService()" in lines[121]
    assert "add_EmailServiceServicer_to_server(service, server)" in lines[125]
