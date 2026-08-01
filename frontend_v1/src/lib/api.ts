export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const csrf = document.cookie.split("; ").find((item) => item.startsWith("csrf_token="))?.split("=")[1];
  if (csrf && ["POST", "PUT", "PATCH", "DELETE"].includes(options.method?.toUpperCase() ?? "GET")) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const response = await fetch(path, { ...options, credentials: "include", headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Request failed");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export function mediaUrl(value: string): string {
  try {
    const url = new URL(value, window.location.origin);
    return `${url.pathname}${url.search}`;
  } catch {
    return value;
  }
}

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const response = await fetch(path, { credentials: "include" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Unable to download file");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition");
  const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
