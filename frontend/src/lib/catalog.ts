import { cache } from "react";
import { cookies } from "next/headers";
import { showcaseCategories, showcaseProducts } from "./showcase";
import type { Category, Listing, Product, Query, Review } from "./types";

const apiBase = process.env.DJANGO_API_URL?.replace(/\/+$/, "");
export const demo = !apiBase;
export const first = (value?: string | string[]) => Array.isArray(value) ? value[0] ?? "" : value ?? "";
export const normalize = (s: string) => s.replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/\u200c/g, " ").replace(/\s+/g, " ").trim().toLocaleLowerCase("fa");
export const number = new Intl.NumberFormat("fa-IR");
export const toman = (price: string) => number.format(Number(price) / (demo || (process.env.STORE_CURRENCY ?? "IRR") === "IRR" ? 10 : 1)) + " تومان";

export async function api(path: string, init?: RequestInit): Promise<Response> {
  if (!apiBase) throw new Error("Django API is not configured.");
  return fetch(apiBase + "/" + path, { ...init, cache: init?.cache ?? "no-store", signal: init?.signal ?? AbortSignal.timeout(6000) });
}

async function data<T>(path: string, cacheCatalog = false): Promise<T | null> {
  const response = await api(path, cacheCatalog ? { cache: "force-cache", next: { revalidate: 30 } } : undefined);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("خطا در دریافت اطلاعات فروشگاه (" + response.status + ")");
  return response.json() as Promise<T>;
}

function media(url: string | null) {
  if (!url || !apiBase) return url;
  const resolved = new URL(url, apiBase);
  return ["http:", "https:"].includes(resolved.protocol) ? resolved.href : null;
}
const productMedia = (p: Product): Product => ({
  ...p, main_image: media(p.main_image),
  gallery: p.gallery.flatMap(image => {
    const url = media(image.image);
    return url ? [{ ...image, image: url }] : [];
  }),
});

export const categories = cache(async (): Promise<Category[]> => {
  if (demo) return showcaseCategories;
  const list: Category[] = [];
  let page = 1;
  while (true) {
    const batch = await data<Listing<Category>>("categories/?page=" + page, true);
    if (!batch) return list;
    list.push(...batch.results.map(c => ({ ...c, image: media(c.image) })));
    if (!batch.next) return list;
    page += 1;
  }
});
export const category = cache(async (slug: string) => {
  const groups = await categories();
  return groups.find(c => c.slug === slug)
    ?? (slug === "living" ? groups.find(c => c.slug === process.env.LIVING_CATEGORY_SLUG || c.name === "نشیمن") : undefined);
});
export const product = cache(async (slug: string) => {
  if (demo) return showcaseProducts.find(p => p.slug === slug) ?? null;
  const found = await data<Product>("products/" + encodeURIComponent(slug) + "/");
  return found ? productMedia(found) : null;
});

const allowed = ["category", "q", "ordering", "in_stock", "min_price", "max_price", "page"] as const;
export function queryParams(query: Query) {
  const params = new URLSearchParams();
  for (const key of allowed) {
    const value = first(query[key]).trim();
    if (value) params.set(key, value);
  }
  return params;
}
function paginate(items: Product[], page: number): Listing<Product> {
  const size = 6;
  return { count: items.length, results: items.slice((page - 1) * size, page * size),
    previous: page > 1 ? String(page - 1) : null, next: page * size < items.length ? String(page + 1) : null };
}
export async function products(query: Query = {}, search = false): Promise<Listing<Product>> {
  const params = queryParams(query);
  const phrase = normalize(params.get("q") ?? "");
  const page = Math.max(1, parseInt(params.get("page") ?? "1", 10) || 1);
  const empty = paginate([], 1);
  if (search && (phrase.length < 2 || phrase.length > 120 || !/[\p{L}\p{N}]/u.test(phrase))) return empty;
  if (!demo) {
    const list = await data<Listing<Product>>((search ? "search/products/" : "products/") + "?" + params, !search);
    return list ? { ...list, results: list.results.map(productMedia) } : empty;
  }
  const slug = params.get("category");
  const parent = showcaseCategories.find(c => c.slug === slug)?.id;
  const allowedCategories = showcaseCategories.filter(c => c.slug === slug || c.parent === parent).map(c => c.slug);
  const result = showcaseProducts.filter(p =>
    (!slug || allowedCategories.includes(p.category)) &&
    (!search || normalize([p.title, p.short_description, showcaseCategories.find(c => c.slug === p.category)?.name].join(" ")).includes(phrase)) &&
    (params.get("in_stock") !== "true" || p.in_stock) &&
    (!params.has("min_price") || Number(p.effective_price) >= Number(params.get("min_price"))) &&
    (!params.has("max_price") || Number(p.effective_price) <= Number(params.get("max_price")))
  );
  const order = params.get("ordering");
  if (order === "price" || order === "-price") result.sort((a, b) => (Number(a.effective_price) - Number(b.effective_price)) * (order === "price" ? 1 : -1));
  if (order === "-newest") result.reverse();
  return paginate(result, page);
}

export async function collection(path: string, excludes?: string) {
  if (demo) {
    const items = showcaseProducts.filter(p => p.slug !== excludes);
    return (path.includes("newest") ? items.reverse() : items).slice(0, 4);
  }
  return (await data<Listing<Product>>(path, !path.endsWith("/related/")))?.results.map(productMedia).slice(0, 4) ?? [];
}

export async function favoriteProducts(page = 1): Promise<{ items: Listing<Product>; authenticated: boolean }> {
  const jar = await cookies();
  const key = demo ? "woodzy-demo-favorites" : "woodzy-access";
  const value = jar.get(key)?.value;
  if (demo) {
    const ids = value?.split(",") ?? [];
    return { items: paginate(showcaseProducts.filter(p => ids.includes(String(p.id))), page), authenticated: true };
  }
  if (!value) return { items: paginate([], 1), authenticated: false };
  const response = await api("favorites/?page=" + page, { headers: { Authorization: "Bearer " + value } });
  if ([401, 403].includes(response.status)) return { items: paginate([], 1), authenticated: false };
  if (!response.ok) throw new Error("دریافت علاقه‌مندی‌ها امکان‌پذیر نبود.");
  const list: Listing<Product> = await response.json();
  return { items: { ...list, results: list.results.map(productMedia) }, authenticated: true };
}

export async function reviews(id: number) {
  if (demo) return [];
  return (await data<Listing<Review>>("products/" + id + "/reviews/"))?.results ?? [];
}
