class DemoApp:
    def get(self, path):
        return lambda f: f

app = DemoApp()

@app.get("/paper/status")
def status():
    return {"ok": True}
