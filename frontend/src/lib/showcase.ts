import type { Category, Product } from "./types";

const categoryRows = [
  ["نشیمن", "living", "room"], ["مبل و کاناپه", "sofas", "sofa"], ["صندلی", "chairs", "chair"],
  ["میز", "tables", "table"], ["کنسول", "consoles", "console"], ["دکور و اکسسوری", "decor", "decor"],
];
export const showcaseCategories: Category[] = categoryRows.map(([name, slug, image], index) => ({
  id: index + 1, name, slug, image: "/images/" + image + ".jpg",
  description: "مجموعه‌ای برای چیدمان گرم و آرام خانه", parent: [1, 2, 3].includes(index) ? 1 : null,
}));
const productRows = [
  ["مبل لینن آرتا", "arta-sofa", "sofa", "sofas", 32400000],
  ["صندلی چوبی راشا", "rasha-chair", "chair", "chairs", 6900000],
  ["میز جلو مبلی وندا", "vanda-table", "table", "tables", 12800000],
  ["کنسول چوبی ماهور", "mahoor-console", "console", "consoles", 20700000],
  ["گلدان سرامیکی نارون", "narvan-vase", "vase", "decor", 1850000],
  ["ست دکور آوین", "avin-decor", "decor", "decor", 2900000],
  ["کاناپه پارچه‌ای نیلا", "nila-sofa", "interior", "sofas", 41800000],
  ["میز پذیرایی ویرا", "vira-table", "room", "tables", 18200000],
] as const;
export const showcaseProducts: Product[] = productRows.map(([title, slug, image, category, amount], index) => {
  const main_image = "/images/" + image + ".jpg";
  const price = String(amount * 10);
  const discount_price = index === 0 ? String(amount * 9) : null;
  return {
    id: index + 1, title, slug, category, price, discount_price, main_image,
    sku: "WZ-" + (101 + index), discount_percentage: index === 0 ? "10" : "0",
    effective_price: discount_price ?? price, in_stock: index !== 5, average_rating: null, review_count: 0,
    short_description: "فرم ساده، متریال گرم و جزئیاتی برای استفادهٔ روزمره",
    description: "این محصول بخشی از کاتالوگ نمایشی WoodzyHome است. مشخصات و تصاویر نهایی از کاتالوگ فروشگاه دریافت می‌شوند.",
    gallery: [main_image].map((image, position) => ({ id: position + 1, image, position, alt_text: title })),
  };
});
