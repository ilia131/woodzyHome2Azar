import { CatalogView } from "@/components/catalog-view";
import type { Query } from "@/lib/types";
export const metadata = { title: "نتایج جست‌وجو", robots: { index: false } };
export default async function SearchPage({ searchParams }: { searchParams: Promise<Query> }) {
  return <CatalogView path="/search" query={await searchParams} search/>;
}
