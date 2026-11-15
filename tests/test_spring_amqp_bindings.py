"""Realistic Spring AMQP Bean wiring resolves unique queue and exchange types."""
from spring_amqp_bindings import spring_bindings


def test_spring_bean_parameter_routing_key_constant():
    source = """
        final static String queueName = "shipping-task";
        Queue queue() { return new Queue(queueName, false); }
        TopicExchange exchange() { return new TopicExchange("shipping-task-exchange"); }
        Binding binding(Queue queue, TopicExchange exchange) {
            return BindingBuilder.bind(queue).to(exchange).with(queueName);
        }
    """
    assert [x[:3] for x in spring_bindings(source)] == [
        ("shipping-task", "shipping-task-exchange", "shipping-task")
    ]
