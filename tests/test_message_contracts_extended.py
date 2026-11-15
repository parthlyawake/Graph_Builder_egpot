"""AMQP and Kafka message extraction fixtures without repository-specific rules."""
from pathlib import Path

from graft_ckg import CKGBuilder


def _build(tmp_path, files):
    for path, source in files.items():
        full = tmp_path / path
        full.parent.mkdir(exist_ok=True, parents=True)
        full.write_text(source, encoding="utf-8")
    builder = CKGBuilder(str(tmp_path))
    graph = builder.build()
    return builder, graph


def _relations(graph, relation):
    return {(u, v) for u, v, d in graph.edges(data=True)
            if d.get("relation") == relation}


def test_python_pika_default_exchange_distinguishes_producers_and_consumers(tmp_path):
    builder, graph = _build(tmp_path, {
        "messaging.py": (
            "import pika\n"
            "def send(channel):\n"
            '    channel.basic_publish(exchange="", routing_key="orders", body=b"data")\n'
            "def receive(channel):\n"
            '    channel.basic_consume(queue="orders", on_message_callback=lambda ch,msg: None)\n'
            "def unknown(channel, queue):\n"
            '    channel.basic_publish(exchange="", routing_key=queue, body=b"data")\n'
        )
    })
    assert ("messaging.py:send", "queue::amqp::orders") in _relations(graph, "PRODUCES_EVENT")
    assert ("messaging.py:receive", "queue::amqp::orders") in _relations(graph, "CONSUMES_EVENT")
    assert not any(u == "messaging.py:unknown" for u, v in _relations(graph, "PRODUCES_EVENT"))


def test_java_rabbit_listener_and_producer(tmp_path):
    _, graph = _build(tmp_path, {
        "Messaging.java": (
            "import org.springframework.amqp.rabbit.core.RabbitTemplate;\n"
            "import org.springframework.amqp.rabbit.annotation.RabbitListener;\n"
            "class Messaging {\n"
            "  RabbitTemplate rabbit;\n"
            "  void send() { rabbit.convertAndSend(\"orders\", new Object()); }\n"
            "  @RabbitListener(queues = \"orders\")\n"
            "  public void receive(String s) {}\n"
            "}\n"
        ),
    })
    assert ("Messaging.java:Messaging.send", "queue::amqp::orders") in _relations(graph, "PRODUCES_EVENT")
    assert ("Messaging.java:Messaging.receive", "queue::amqp::orders") in _relations(graph, "CONSUMES_EVENT")


def test_js_amqp_queue_events(tmp_path):
    _, graph = _build(tmp_path, {
        "send.js": (
            'const amqp = require("amqplib");\n'
            'function send(channel) { return channel.sendToQueue("orders", Buffer.from("msg")); }\n'
            'function listen(channel) { return channel.consume("orders", onMessage); }\n'
            'function other(channel, queue) { return channel.consume(queue, onMessage); }\n'
        )
    })
    assert ("send.js:send", "queue::amqp::orders") in _relations(graph, "PRODUCES_EVENT")
    assert ("send.js:listen", "queue::amqp::orders") in _relations(graph, "CONSUMES_EVENT")
    assert not any(u == "send.js:other" for u, v in _relations(graph, "CONSUMES_EVENT"))


def test_go_amqp_event_calls(tmp_path):
    _, graph = _build(tmp_path, {
        "queue.go": (
            'package queue\n'
            'import "github.com/rabbitmq/amqp091-go"\n'
            'func send(ch *amqp.Channel) { ch.Publish("events", "orders", false, false, amqp.Publishing{}) }\n'
            'func recv(ch *amqp.Channel) { ch.Consume("orders", "", true, false, false, false, nil) }\n'
        )
    })
    assert ("queue.go:send", "topic::amqp::events/orders") in _relations(graph, "PRODUCES_EVENT")
    assert ("queue.go:recv", "queue::amqp::orders") in _relations(graph, "CONSUMES_EVENT")


def test_python_kafka_literal_topic_and_unknown_omission(tmp_path):
    _, graph = _build(tmp_path, {
        "pub.py": (
            'from kafka import KafkaProducer\n'
            'def emit(producer):\n'
            '    producer.send("metadata-change", b"event")\n'
            'def dynamic(producer, key):\n'
            '    producer.send(key, b"event")\n'
        )
    })
    assert ("pub.py:emit", "topic::kafka::metadata-change") in _relations(graph, "PRODUCES_EVENT")
    assert not any(u == "pub.py:dynamic" for u, v in _relations(graph, "PRODUCES_EVENT")
