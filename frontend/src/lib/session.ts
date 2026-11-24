import { cookies } from "next/headers";
import { api } from "./catalog";

const accessKey = "woodzy-access";
const refreshKey = "woodzy-refresh";
const options = { httpOnly: true, sameSite: "lax" as const, secure: process.env.NODE_ENV === "production", path: "/" };

export async function saveSession(data: { access?: unknown; refresh?: unknown }) {
  if (typeof data.access !== "string" || typeof data.refresh !== "string") return false;
  const jar = await cookies();
  jar.set(accessKey, data.access, { ...options, maxAge: 600 });
  jar.set(refreshKey, data.refresh, { ...options, maxAge: 604800 });
  return true;
}

export async function refreshSession() {
  const refresh = (await cookies()).get(refreshKey)?.value;
  if (!refresh) return false;
  const response = await api("auth/token/refresh/", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh }),
  });
  if (response.status === 401 || response.status === 400) {
    await clearSession();
    return false;
  }
  if (!response.ok) throw new Error("Session refresh unavailable");
  return saveSession(await response.json());
}

export async function clearSession() {
  const jar = await cookies();
  jar.delete(accessKey);
  jar.delete(refreshKey);
}

export async function revokeSession() {
  const jar = await cookies();
  let access = jar.get(accessKey)?.value;
  let refresh = jar.get(refreshKey)?.value;
  if (!refresh) return;
  const logout = () => api("auth/logout/", {
    method: "POST", headers: { Authorization: "Bearer " + access, "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (access) {
    const response = await logout();
    if (response.ok || response.status === 400) return;
    if (response.status !== 401) throw new Error("Logout unavailable");
  }
  if (await refreshSession()) {
    access = jar.get(accessKey)?.value;
    refresh = jar.get(refreshKey)?.value;
    const response = await logout();
    if (!response.ok) throw new Error("Logout unavailable");
  }
}
