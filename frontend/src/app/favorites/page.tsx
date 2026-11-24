import Link from "next/link";
import { Heart } from "lucide-react";
import { signIn, signOut } from "@/app/actions";
import { Crumbs, Heading, LinkButton, ProductCard, ProductGrid } from "@/components/storefront";
import { collection, demo, favoriteProducts, first, number } from "@/lib/catalog";
import type { Query } from "@/lib/types";
export const metadata = { title: "علاقه‌مندی‌ها", robots: { index: false } };
export default async function FavoritesPage({ searchParams }: { searchParams: Promise<Query> }) {
  const query = await searchParams;
  const page = Math.max(1, parseInt(first(query.page), 10) || 1);
  const [{ items, authenticated }, suggested] = await Promise.all([favoriteProducts(page), collection("products/recommended/")]);
  const error = first(query.login);
  return <div className="container favorites-page">
    <Crumbs trail={[["علاقه‌مندی‌ها"]]}/>
    <section className="catalog-hero"><div><h1>علاقه‌مندی‌های من</h1><p>محصولاتی را که برای چیدمان خانه در نظر دارید اینجا مرور کنید.</p></div><Heart size={58} aria-hidden="true"/></section>
    {!authenticated ? <section className="login-panel"><h2>ورود برای مشاهده علاقه‌مندی‌ها</h2>{error && <p role="alert">{error === "limited" ? "تلاش‌های ورود زیاد بوده است. کمی بعد دوباره امتحان کنید." : "شماره موبایل یا گذرواژه معتبر نیست."}</p>}
      <form action={signIn}><label>شماره موبایل<input name="phone" type="tel" autoComplete="username" required maxLength={32}/></label><label>گذرواژه<input name="password" type="password" autoComplete="current-password" required maxLength={128}/></label><button className="button">ورود</button></form></section>
    : <section className="favorites-layout">
      <div>{items.results.length ? <div className="favorite-grid">{items.results.map(p => <ProductCard key={p.id} product={p} remove/>)}</div> : <div className="empty">هنوز محصولی به علاقه‌مندی‌ها اضافه نشده است.</div>}
        {(items.next || items.previous) && <nav className="pagination" aria-label="صفحه‌بندی">{items.previous && <Link href={"?page=" + (page - 1)}>صفحه قبل</Link>}<span aria-current="page">{number.format(page)}</span>{items.next && <Link href={"?page=" + (page + 1)}>صفحه بعد</Link>}</nav>}
      </div>
      <aside className="filter-panel"><h2>خلاصه علاقه‌مندی‌ها</h2><p>{number.format(items.count)} محصول ذخیره‌شده</p><LinkButton href="/products" secondary>مرور محصولات</LinkButton>{!demo && <form action={signOut}><button className="chips-button">خروج از حساب</button></form>}</aside>
    </section>}
    <section className="related"><Heading title="محصولات پیشنهادی"/><ProductGrid items={suggested}/></section>
  </div>;
}
