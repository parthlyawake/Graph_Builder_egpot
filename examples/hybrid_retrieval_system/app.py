"""Small, labelled fixture for hybrid retrieval smoke benchmarks."""


class DemoApp:
    def get(self, path):
        return lambda handler: handler

    def post(self, path):
        return lambda handler: handler


app = DemoApp()


@app.get("/orders")
def list_orders():
    """Return all orders for the dashboard."""
    return []


@app.post("/orders")
def create_order(items):
    """Create an order after calculating its total."""
    from helpers import calculate_total
    return {"total": calculate_total(items)}
