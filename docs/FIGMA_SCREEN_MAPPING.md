# WoodzyHome Figma screen mapping

The [design specification](WOODZYHOME_DESIGN_SPEC.md) and [layer geometry](WOODZYHOME_FIGMA_GEOMETRY.tsv) are the desktop references. Each view implements the recorded sequence of sections and uses the shared RTL storefront. Desktop reference width is 1280 px. Breakpoints and mobile layouts are adaptations. Starter-plan limits blocked the render and Design Context requests, so visual parity, exact assets, typography and effects remain unverified.

| Figma frame | Next.js route | Shared components | Django endpoints (under /api/v1/) | Responsive treatment |
|---|---|---|---|---|
| صفحه نخست (`1:2226`) | `/` | Header, Footer, Heading, CategoryGrid, ProductGrid, Advantages | categories, products/popular, products with newest ordering | Stacked hero; category, product and lookbook grids reduce columns |
| همه محصولات (`1:4233`) | `/products` | CatalogView, Crumbs, ProductGrid | products, categories | Filters above grid on small screens |
| جزئیات محصول (`1:1635`) | `/products/[slug]` | Gallery, ProductGrid, FavoriteButton | product detail, related, product reviews, favorites, cart/items | Gallery and summary stack; thumbnail strip and tab links wrap |
| دسته‌بندی محصولات (`1:611`) | `/categories` | CategoryDirectory, Advantages | categories | Bento grid reduces columns; live filtering remains visible |
| محصولات دسته‌بندی نشیمن (`1:3573`) | `/categories/[slug]` | CatalogView, Picture, ProductGrid | categories, products with category filter | Editorial image stacks; filters above results |
| نتایج جستجو (`1:2`) | `/search` | CatalogView, HeaderSearch, ProductGrid | search/products, search/suggestions, categories | Search field and filters reflow above results |
| علاقه‌مندی‌ها (`1:3011`) | `/favorites` | ProductCard, FavoriteButton, ProductGrid | favorites, auth/login, products/recommended | Summary moves above saved items |
| درباره ما و تماس (`1:1103`) | `/about` | Crumbs, Picture, Heading | Editorial; no contact or newsroom API found | Story and showroom columns stack; FAQ uses native disclosure |
