import { cookies } from "next/headers";
import { api, demo } from "./catalog";

export class BackendError extends Error {
  constructor(readonly status: number) { super("Backend response " + status); }
}
export async function authorized(path: string, method = "GET", body?: FormData | Record<string, unknown>) {
  const access = (await cookies()).get("woodzy-access")?.value;
  if (!access || demo) throw new BackendError(401);
  const headers = new Headers({ Authorization: "Bearer " + access });
  if (body && !(body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await api(path, { method, headers, body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined });
  if (!response.ok) throw new BackendError(response.status);
  return response.status === 204 ? null : response.json();
}
export type Row = Record<string, unknown>;
export async function list(path: string): Promise<{ rows: Row[]; next: boolean; previous: boolean }> {
  const collection = await authorized(path);
  if (Array.isArray(collection)) return { rows: collection, next: false, previous: false };
  return { rows: collection?.results ?? [], next: Boolean(collection?.next), previous: Boolean(collection?.previous) };
}
