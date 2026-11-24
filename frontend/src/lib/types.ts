export interface Category { id: number; name: string; slug: string; description: string; image: string | null; parent: number | null }
export interface GalleryImage { id: number; image: string; alt_text: string; position: number }
export interface Product {
  id: number; title: string; slug: string; short_description: string; description?: string;
  main_image: string | null; gallery: GalleryImage[]; price: string; discount_price: string | null;
  effective_price: string; discount_percentage: string; category: string; sku: string;
  in_stock: boolean; average_rating: number | null; review_count: number;
  seo?: { meta_title: string; meta_description: string; canonical_url: string; og_title: string; og_description: string; og_image: string | null; robots_index: boolean; robots_follow: boolean; structured_data: Record<string, unknown> };
}
export interface Listing<T> { count: number; next: string | null; previous: string | null; results: T[] }
export type Query = Record<string, string | string[] | undefined>;
export interface Review { id: number; title: string; comment: string; rating: number; replies: { id: number; parent: number | null; comment: string; created_at: string }[] }
