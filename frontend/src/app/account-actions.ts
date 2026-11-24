"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { api, demo } from "@/lib/catalog";
import { authorized, BackendError } from "@/lib/private-api";
import { operations, type OperationKey } from "@/features/operations";

const routes = /^\/(?:account\/(?:auth|recovery|dashboard|profile|orders|activity)|checkout\/(?:cart|details|payment|result)|admin\/(?:overview|products|editor|categories|inventory|orders|customers|payments|settings))(?:\?[^#]*)?$/;
export async function mutate(op: OperationKey, id: string, returnTo: string, form: FormData) {
  if (!Object.hasOwn(operations, op) || !routes.test(returnTo) || (id && !/^\d{1,16}$/.test(id))) redirect("/");
  const operation: (typeof operations)[OperationKey] = operations[op];
  const integers = "integers" in operation ? operation.integers : [];
  const booleans = "booleans" in operation ? operation.booleans : [];
  const multipart = "multipart" in operation && operation.multipart;
  const json: Record<string, unknown> = {};
  const fileForm = new FormData();
  let outcome = "saved";
  let destination: string | undefined;
  try {
    for (const field of operation.fields) {
      const raw = form.get(field);
      if (raw instanceof File) {
        if (raw.size > 5 * 1024 * 1024) throw new BackendError(400);
        if (multipart && raw.size > 0) fileForm.set(field, raw);
      } else if (booleans.includes(field)) {
        json[field] = raw === "true" || raw === "on";
        if (multipart) fileForm.set(field, String(json[field]));
      } else if (raw !== null) {
        json[field] = integers.includes(field) && raw !== "" ? Number(raw) : raw;
        if (multipart) fileForm.set(field, raw);
      }
    }
    const result = await authorized(operation.path(id), operation.method, operation.method === "DELETE" ? undefined : multipart ? fileForm : json);
    if ("result" in operation) destination = operation.result(result);
  } catch (error) {
    outcome = error instanceof BackendError ? String(error.status) : "unavailable";
  }
  if (outcome === "401") redirect("/account/auth");
  if (destination) redirect(destination);
  const path = new URL(returnTo, "https://woodzy.invalid");
  path.searchParams.set("feedback", outcome);
  revalidatePath(path.pathname);
  redirect(path.pathname + path.search);
}
export async function register(form: FormData) {
  if (demo) redirect("/account/auth?feedback=unavailable");
  const payload = Object.fromEntries(["phone", "password", "first_name", "last_name", "email"].map(key => [key, String(form.get(key) ?? "")]));
  const response = await api("auth/register/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).catch(() => null);
  redirect("/account/auth?feedback=" + (response?.ok ? "registered" : response?.status ?? "unavailable"));
}
