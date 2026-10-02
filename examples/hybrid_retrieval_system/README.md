# Order service architecture

The order API exposes a list route and an order-creation route.  Creation
delegates price calculation to `helpers.calculate_total`.
