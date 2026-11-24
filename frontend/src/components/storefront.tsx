import Link from "next/link";
import Image from "next/image";
import { HeaderSearch } from "./header-search";
import { ArrowLeft, ArrowUpLeft, ChevronLeft, Heart, Instagram, Leaf, Menu, PackageCheck, Search, ShieldCheck, ShoppingBag, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { saveFavorite } from "@/app/actions";
import { demo, number, toman } from "@/lib/catalog";
import type { Category, Product } from "@/lib/types";

const navigation = [
  ["صفحه نخست", "/"], ["همه محصولات", "/products"], ["دسته‌بندی‌ها", "/categories"],
  ["نشیمن", "/categories/living"], ["درباره ما", "/about"],
];

function Brand() {
  const logoPath = process.env.WOODZY_LOGO_PATH;
  if (logoPath?.startsWith("/") && !logoPath.startsWith("//")) {
    return <Link href="/" className="brand" aria-label="WoodzyHome، صفحه نخست"><Image className="official-brand" src={logoPath} width={199} height={40} alt="WoodzyHome" unoptimized/></Link>;
  }
  return <Link href="/" className="brand" aria-label="WoodzyHome، صفحه نخست">
    <span className="monogram" aria-hidden="true">WH</span>
    <span><b>WOODZY HOME</b><small>FURNITURE & INTERIORS</small></span>
  </Link>;
}
export function Header() {
  return <header className="header">
    <div className="announcement"><Leaf size={14}/> {demo ? "پیش‌نمایش فروشگاه · کاتالوگ نمایشی" : "طراحی برای زندگی، ساخته‌شده برای ماندن"} <span aria-hidden="true">✦</span></div>
    <div className="container header-main">
      <Brand/>
      <HeaderSearch/>
      <div className="header-tools"><Link href="/account" className="icon-button" aria-label="حساب کاربری"><UserRound size={20}/></Link><Link href="/favorites" className="icon-button" aria-label="علاقه‌مندی‌ها"><Heart size={20}/></Link><Link href="/checkout/cart" className="icon-button" aria-label="سبد خرید"><ShoppingBag size={20}/></Link></div>
    </div>
    <nav className="header-nav" aria-label="منوی اصلی"><div className="container nav-inner">
      {navigation.map(([name, href]) => <Link key={href} href={href}>{name}</Link>)}
    </div><details className="mobile-nav"><summary><Menu size={18}/> منو</summary><div>{navigation.map(([name, href]) => <Link key={href} href={href}>{name}</Link>)}</div></details></nav>
  </header>;
}
export function Footer() {
  return <footer className="footer"><div className="container">
    <div className="footer-main"><div><Brand/><p>مبلمان و اشیایی برای خانه‌هایی که داستان خودشان را دارند.</p></div>
      <div><h3>فروشگاه</h3><Link href="/products">همه محصولات</Link><Link href="/categories">دسته‌بندی‌ها</Link><Link href="/favorites">علاقه‌مندی‌ها</Link></div>
      <div><h3>وودزی هوم</h3><Link href="/about">درباره ما</Link><Link href="/about#contact">تماس و نمایشگاه</Link><Link href="/about#faq">پرسش‌های متداول</Link></div>
      <div><h3>الهام برای خانه</h3><Link href="/#lookbook"><Instagram size={17}/> گالری چیدمان</Link><Link href="/search"><Search size={17}/> جست‌وجوی محصولات</Link></div>
    </div><div className="footer-bottom"><span>تمام حقوق برای وودزی هوم محفوظ است.</span><b dir="ltr">WOODZY HOME</b></div>
  </div></footer>;
}
export function Crumbs({ trail }: { trail: [string, string?][] }) {
  return <nav aria-label="مسیر راهنما" className="crumbs"><Link href="/">خانه</Link>{trail.map(([label, href], index) => <span key={index}><ChevronLeft size={13}/>{href ? <Link href={href}>{label}</Link> : <span aria-current="page">{label}</span>}</span>)}</nav>;
}
export function LinkButton({ href, children, secondary = false }: { href: string; children: ReactNode; secondary?: boolean }) {
  return <Link href={href} className={secondary ? "button button-secondary" : "button"}>{children}<ArrowLeft size={17}/></Link>;
}
export function Picture({ src, alt, className = "" }: { src?: string | null; alt: string; className?: string }) {
  return src ? <img className={"picture " + className} src={src} alt={alt} loading="lazy" decoding="async"/> : <div className={"picture absent " + className} role={alt ? "img" : undefined} aria-label={alt || undefined}><Leaf size={30} aria-hidden="true"/></div>;
}
export function FavoriteButton({ id, remove = false }: { id: number; remove?: boolean }) {
  return <form action={saveFavorite} className="favorite-control">
    <input name="product" type="hidden" value={id}/><input name="remove" type="hidden" value={String(remove)}/>
    <button className="icon-button" aria-label={remove ? "حذف از علاقه‌مندی‌ها" : "افزودن به علاقه‌مندی‌ها"}><Heart size={18} fill={remove ? "currentColor" : "none"}/></button>
  </form>;
}
export function ProductCard({ product, remove = false }: { product: Product; remove?: boolean }) {
  return <article className="product-card">
    <div className="product-image"><Link prefetch={false} href={"/products/" + encodeURIComponent(product.slug)} aria-label={product.title}><Picture src={product.main_image} alt={product.title}/></Link>
      <FavoriteButton id={product.id} remove={remove}/>
      {Number(product.discount_percentage) > 0 && <span className="sale">{number.format(Number(product.discount_percentage))}٪ تخفیف</span>}
    </div>
    <div className="product-copy"><h3><Link prefetch={false} href={"/products/" + encodeURIComponent(product.slug)}>{product.title}</Link></h3><p>{product.short_description}</p>
      <div className="price-line"><strong>{toman(product.effective_price)}</strong>{product.discount_price && <s>{toman(product.price)}</s>}</div>
      {!product.in_stock && <span className="availability">ناموجود</span>}
    </div>
  </article>;
}
export function ProductGrid({ items }: { items: Product[] }) {
  return items.length ? <div className="product-grid">{items.map(p => <ProductCard key={p.id} product={p}/>)}</div> : <div className="empty">محصولی برای نمایش پیدا نشد.</div>;
}
export function CategoryGrid({ items }: { items: Category[] }) {
  return items.length ? <div className="category-grid">{items.map(c => <Link prefetch={false} className="category-card" key={c.id} href={"/categories/" + encodeURIComponent(c.slug)}>
    <Picture src={c.image} alt=""/><div><h3>{c.name}</h3><ArrowUpLeft size={22}/></div>
  </Link>)}</div> : <div className="empty">دسته‌بندی پیدا نشد.</div>;
}
export function Heading({ kicker, title, text, children }: { kicker?: string; title: string; text?: string; children?: ReactNode }) {
  return <div className="section-heading"><div>{kicker && <span className="eyebrow">{kicker}</span>}<h2>{title}</h2>{text && <p>{text}</p>}</div>{children}</div>;
}
export function Advantages() {
  return <div className="advantages"><div className="container advantages-inner">
    <span><Leaf/> متریال باکیفیت</span><span><PackageCheck/> بسته‌بندی امن</span><span><ShieldCheck/> پشتیبانی خرید</span>
  </div></div>;
}
