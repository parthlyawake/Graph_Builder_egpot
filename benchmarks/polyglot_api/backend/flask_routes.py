"""Flask-style routes for the static API-link benchmark."""


class DemoApp:
    def get(self, path):
        return lambda handler: handler

    def post(self, path):
        return lambda handler: handler

    def route(self, path, methods=None):
        return lambda handler: handler


app = DemoApp()


@app.get("/api/users")
def list_users():
    return {"users": []}


@app.post("/api/users")
def create_user():
    return {"created": True}


@app.route("/api/orders", methods=["PUT"])
def update_order():
    return {"updated": True}


@app.route("/api/search", methods=("PATCH",))
def patch_search():
    return {"patched": True}
