"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, demo, product } from "@/lib/catalog";
import { clearSession, refreshSession, revokeSession, saveSession } from "@/lib/session";
import { showcaseProducts } from "@/lib/showcase";

const sessionOptions = { httpOnly: true, sameSite: "lax" as const, secure: process.env.NODE_ENV === "production" && !demo, path: "/" };

export async function saveFavorite(form: FormData) {
  const id = Number(form.get("product"));
  if (!Number.isSafeInteger(id) || id < 1) return;
  const remove = form.get("remove") === "true";
  const jar = await cookies();
  if (demo) {
    if (!showcaseProducts.some(p => p.id === id)) return;
    const ids = new Set(jar.get("woodzy-demo-favorites")?.value.split(",") ?? []);
    if (remove) ids.delete(String(id));
    else ids.add(String(id));
    jar.set("woodzy-demo-favorites", [...ids].join(","), sessionOptions);
  } else {
    const access = jar.get("woodzy-access")?.value;
    if (!access) redirect("/favorites");
    const response = await api("favorites/" + id + "/", {
      method: remove ? "DELETE" : "POST", headers: { Authorization: "Bearer " + access },
    });
    if ([401, 403].includes(response.status)) redirect("/favorites");
    if (!response.ok) throw new Error("به‌روزرسانی علاقه‌مندی ممکن نبود.");
  }
  revalidatePath("/", "layout");
}

export async function signIn(form: FormData) {
  const destination = form.get("destination") === "/account/dashboard" ? "/account/dashboard" : "/favorites";
  const loginPage = destination === "/favorites" ? "/favorites" : "/account/auth";
  if (demo) redirect(loginPage + "?feedback=unavailable");
  const phone = String(form.get("phone") ?? "").trim();
  const password = String(form.get("password") ?? "");
  if (!phone || !password || phone.length > 32 || password.length > 128) redirect(loginPage + "?login=invalid");
  const response = await api("auth/login/", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone, password }),
  });
  if (!response.ok) redirect(loginPage + "?login=" + (response.status === 429 ? "limited" : "invalid"));
  if (!await saveSession(await response.json())) redirect(loginPage + "?login=invalid");
  redirect(destination);
}

export async function signOut() {
  try {
    await revokeSession();
  } catch {
    redirect("/account/auth?login=logout-unavailable");
  }
  await clearSession();
  redirect("/account/auth");
}

export async function addToCart(form: FormData) {
  const slug = String(form.get("slug") ?? "");
  const quantity = Number(form.get("quantity"));
  if (!slug || slug.length > 200 || !Number.isInteger(quantity) || quantity < 1 || quantity > 99) return;
  const path = "/products/" + encodeURIComponent(slug);
  if (demo) redirect(path + "?cart=demo");
  const access = (await cookies()).get("woodzy-access")?.value;
  if (!access) redirect("/favorites");
  const item = await product(slug);
  if (!item?.in_stock) redirect(path + "?cart=error");
  const response = await api("cart/items/", {
    method: "POST", headers: { Authorization: "Bearer " + access, "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: item.id, quantity }),
  });
  if ([401, 403].includes(response.status)) redirect("/favorites");
  redirect(path + "?cart=" + (response.ok ? "saved" : "error"));
}


export async function renewSession() {
  let renewed: boolean;
  try {
    renewed = await refreshSession();
  } catch {
    redirect("/account/auth?login=refresh-unavailable");
  }
  redirect(renewed ? "/account/dashboard" : "/account/auth?login=expired");
}
