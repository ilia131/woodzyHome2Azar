"use server";

import { redirect } from "next/navigation";
import { api, demo } from "@/lib/catalog";
import { authorized, BackendError } from "@/lib/private-api";

const flows = {
  recovery: ["auth/password/recovery/", ["phone", "email"], "/account/recovery", false],
  reset: ["auth/password/recovery/confirm/", ["phone", "token", "password"], "/account/recovery", false],
  enroll: ["auth/password/recovery/email/", ["email", "password"], "/account/recovery", true],
  verify: ["auth/password/recovery/email/confirm/", ["token"], "/account/recovery", true],
  contact: ["store/contact/", ["name", "email", "message"], "/about", false],
  newsletter: ["store/newsletter/", ["email", "action"], "/", false],
  newsletterCode: ["store/newsletter/confirm/", ["token"], "/", false],
} as const;

export async function submitStoreForm(flow: keyof typeof flows, form: FormData) {
  if (!Object.hasOwn(flows, flow)) redirect("/");
  const [endpoint, fields, path, privateForm] = flows[flow];
  const anchor = flow === "contact" ? "#contact" : path === "/" ? "#newsletter" : "";
  const payload = Object.fromEntries(fields.map(name => [name, String(form.get(name) ?? "")]));
  let result = "unavailable";
  if (!demo) {
    try {
      if (privateForm) {
        await authorized(endpoint, "POST", payload);
        result = flow;
      } else {
        const response = await api(endpoint, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
        });
        result = response.ok ? flow : String(response.status);
      }
    } catch (error) {
      if (error instanceof BackendError) result = String(error.status);
    }
  }
  redirect(path + "?store=" + encodeURIComponent(result) + anchor);
}
