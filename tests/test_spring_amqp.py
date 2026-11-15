"""Spring listener adapters become queue consumers only with typed handler wiring."""
from graft_ckg import CKGBuilder


def test_container_queue_and_handler_wiring(tmp_path):
    (tmp_path / "Handler.java").write_text(
        "public class ShipmentHandler {\n"
        "  public void handleMessage(String shipment) { }\n"
        "}\n", encoding="utf8")
    (tmp_path / "Config.java").write_text(
        "public class Config {\n"
        '  final static String queueName = "shipping-task";\n'
        "  ShipmentHandler shipmentHandler;\n"
        "  void configure() {\n"
        "    SimpleMessageListenerContainer listener = new SimpleMessageListenerContainer();\n"
        "    listener.setQueueNames(this.queueName);\n"
        "    listener.setMessageListener(messageListenerAdapter());\n"
        "  }\n"
        "  MessageListenerAdapter messageListenerAdapter() {\n"
        "    return new MessageListenerAdapter(shipmentHandler);\n"
        "  }\n"
        "}\n", encoding="utf8")
    builder = CKGBuilder(str(tmp_path))
    graph = builder.build()
    source = "Handler.java:ShipmentHandler.handleMessage"
    target = "queue::amqp::shipping-task"
    assert any(v == target and d.get("relation") == "CONSUMES_EVENT"
               for _, v, d in graph.out_edges(source, data=True))
