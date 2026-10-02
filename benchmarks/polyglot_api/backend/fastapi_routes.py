"""FastAPI-style routes for the static API-link benchmark."""


class DemoRouter:
    def get(self, path):
        return lambda handler: handler

    def delete(self, path):
        return lambda handler: handler


router = DemoRouter()


@router.get("/v1/products")
def list_products():
    return {"products": []}


@router.delete("/v1/products/sku-1")
def delete_product():
    return {"deleted": True}
