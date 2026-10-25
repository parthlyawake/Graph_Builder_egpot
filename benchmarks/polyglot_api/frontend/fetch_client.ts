export function listUsers() {
  return fetch("/api/users");
}

export function createUser() {
  return fetch("/api/users", { method: "POST", body: JSON.stringify({ name: "Ada" }) });
}

export function updateOrder() {
  return fetch("/api/orders", { method: "PUT" });
}

export function patchSearch() {
  return fetch("/api/search", { method: "PATCH" });
}

export function dynamicLookup(userId: string) {
  return fetch(`/api/users/${userId}`);
}

export function wrongMethod() {
  return fetch("/v1/products", { method: "POST" });
}
