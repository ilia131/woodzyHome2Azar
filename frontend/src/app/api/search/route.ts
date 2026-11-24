import { NextResponse } from "next/server";
import { api, demo, normalize } from "@/lib/catalog";
import { showcaseCategories, showcaseProducts } from "@/lib/showcase";

export async function GET(request: Request) {
  const q = normalize(new URL(request.url).searchParams.get("q") ?? "");
  if (q.length < 2 || q.length > 120 || !/[\p{L}\p{N}]/u.test(q)) return NextResponse.json({ products: [], categories: [] });
  if (demo) return NextResponse.json({
    products: showcaseProducts.filter(p => normalize(p.title).includes(q)).slice(0, 4).map(({ id, title, slug }) => ({ id, title, slug })),
    categories: showcaseCategories.filter(c => normalize(c.name).includes(q)).slice(0, 4).map(({ id, name, slug }) => ({ id, name, slug })),
  });
  try {
    const response = await api("search/suggestions/?" + new URLSearchParams({ q, limit: "4" }));
    return NextResponse.json(response.ok ? await response.json() : { error: "suggestions_unavailable" }, { status: response.status });
  } catch {
    return NextResponse.json({ error: "suggestions_unavailable" }, { status: 503 });
  }
}
