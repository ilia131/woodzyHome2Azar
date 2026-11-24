import { CatalogView } from "@/components/catalog-view";
import type { Query } from "@/lib/types";
export const metadata = { title: "همه محصولات" };
export default async function ProductsPage({ searchParams }: { searchParams: Promise<Query> }) {
  return <CatalogView path="/products" query={await searchParams}/>;
}
