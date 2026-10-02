import axios from "axios";

export function loadProducts() {
  return axios.get("/v1/products");
}

export function removeProduct() {
  return axios.delete("/v1/products/sku-1");
}
