export function requestStatus() {
  return fetch("/paper/status", { method: "GET" });
}

export function unknownStatus(id: string) {
  return fetch(`/paper/status/${id}`);
}
