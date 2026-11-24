import Link from "next/link";
import { Search, SlidersHorizontal } from "lucide-react";
import { categories, categoryChildren, first, number, popularSearches, products, queryParams, recentSearches, suggestedCategories } from "@/lib/catalog";
import type { Category, Query } from "@/lib/types";
import { Crumbs, Heading, Picture, ProductGrid } from "./storefront";

const sorts = [["", "پیش‌فرض"], ["-newest", "تازه‌ترین"], ["price", "کمترین قیمت"], ["-price", "بیشترین قیمت"], ["-score", "محبوب‌ترین"]];

export async function CatalogView({ path, query, selected, search = false }: { path: string; query: Query; selected?: Category; search?: boolean }) {
  const selectedQuery = selected ? { ...query, category: selected.slug } : query;
  const [groups, list, children, suggestions, terms, recent] = await Promise.all([categories(), products(selectedQuery, search), selected ? categoryChildren(selected.slug) : [], search ? suggestedCategories() : [], search ? popularSearches() : [], search ? recentSearches() : []]);
  const phrase = first(query.q);
  const title = search ? "نتایج جست‌وجو" : selected?.name ?? "همه محصولات";
  const params = queryParams(selectedQuery);
  const page = Math.max(1, parseInt(params.get("page") ?? "1", 10) || 1);
  const pageHref = (position: number) => {
    const copy = new URLSearchParams(params);
    copy.set("page", String(position));
    return path + "?" + copy.toString();
  };

  return <div className={`container catalog-page ${search ? "search-page" : selected ? "category-page" : "all-products-page"}`}>
    <Crumbs trail={selected ? [["دسته‌بندی‌ها", "/categories"], [title]] : [[title]]}/>
    <section className={`catalog-hero ${selected ? "category-hero" : ""}`}>
      <div><h1>{title}</h1><p>{search ? "نام محصول یا دسته‌بندی دلخواهتان را وارد کنید." : selected?.description || "مبلمان، میز، صندلی و جزئیات دکور را برای خانه‌تان مرور کنید."}</p>
      {search && <form action="/search" className="search-form" role="search"><label className="field"><Search size={19}/><input name="q" aria-label="عبارت جست‌وجو" defaultValue={phrase} minLength={2} maxLength={120} required placeholder="مثلاً صندلی چوبی"/></label><button className="button">جست‌وجو</button></form>}
      {children.length > 0 && <div className="chips">{children.map(c => <Link key={c.id} href={"/categories/" + encodeURIComponent(c.slug)}>{c.name}</Link>)}</div>}</div>
      {selected && <Picture src={selected.image} alt=""/>}
    </section>
    <div className="catalog-filters"><form action={path} id="catalog-filter">
      {search && <input name="q" type="hidden" value={phrase}/>}</form>
      <div className="catalog-toolbar"><span>{search && phrase ? `«${phrase}» · ` : ""}{number.format(list.count)} محصول</span>
      <label>مرتب‌سازی <select form="catalog-filter" name="ordering" defaultValue={first(query.ordering)}>{sorts.map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label></div>
      <div className="catalog-layout">
        <aside className="filter-panel">
          <h2><SlidersHorizontal size={18}/> فیلتر محصولات</h2>
          {!selected && <label>دسته‌بندی<select form="catalog-filter" name="category" defaultValue={first(query.category)}><option value="">همه دسته‌ها</option>{groups.map(c => <option key={c.id} value={c.slug}>{c.name}</option>)}</select></label>}
          <label>حداقل قیمت ({process.env.STORE_CURRENCY === "IRT" ? "تومان" : "ریال"})<input form="catalog-filter" name="min_price" type="number" min="0" defaultValue={first(query.min_price)} placeholder="بدون محدودیت"/></label>
          <label>حداکثر قیمت ({process.env.STORE_CURRENCY === "IRT" ? "تومان" : "ریال"})<input form="catalog-filter" name="max_price" type="number" min="0" defaultValue={first(query.max_price)} placeholder="بدون محدودیت"/></label>
          <label className="stock"><input form="catalog-filter" name="in_stock" type="checkbox" value="true" defaultChecked={first(query.in_stock) === "true"}/> فقط کالاهای موجود</label>
          <button type="submit" form="catalog-filter" className="button">اعمال فیلتر و مرتب‌سازی</button><Link href={search && phrase ? "/search?q=" + encodeURIComponent(phrase) : path} className="inline-link">پاک‌کردن فیلترها</Link>
        </aside>
        <div id="catalog-results"><ProductGrid items={list.results}/>
          {(list.next || list.previous) && <nav className="pagination" aria-label="صفحه‌بندی">{list.previous && <Link href={pageHref(page - 1)}>صفحه قبل</Link>}<span aria-current="page">{number.format(page)}</span>{list.next && <Link href={pageHref(page + 1)}>صفحه بعد</Link>}</nav>}
        </div>
      </div>
    </div>
    {search && recent.length > 0 && <section className="search-related"><Heading title="جست‌وجوهای اخیر شما"/><div className="chips">{recent.map(({ term }) => <Link key={term} href={"/search?q=" + encodeURIComponent(term)}>{term}</Link>)}</div></section>}
    {search && terms.length > 0 && <section className="search-related"><Heading title="جست‌وجوهای محبوب"/><div className="chips">{terms.map(({ term }) => <Link key={term} href={"/search?q=" + encodeURIComponent(term)}>{term}</Link>)}</div></section>}
    {search && suggestions.length > 0 && <section className="search-related"><Heading title="دسته‌های مرتبط"/><div className="chips">{suggestions.map(c => <Link key={c.id} href={"/categories/" + encodeURIComponent(c.slug)}>{c.name}</Link>)}</div></section>}
  </div>;
}
