"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Search } from "lucide-react";
import type { Category, GalleryImage } from "@/lib/types";

const normalizeText = (text: string) => text.trim().replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/\u200c/g, " ").replace(/\s+/g, " ");

export function CategoryDirectory({ items }: { items: Category[] }) {
  const [query, setQuery] = useState("");
  const [rootsOnly, setRootsOnly] = useState(false);
  const matched = items.filter(item => (!rootsOnly || item.parent === null) && normalizeText(item.name).includes(normalizeText(query)));
  return <>
    <label className="field category-search"><Search size={18}/><input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="نام دسته‌بندی را جست‌وجو کنید" aria-label="جست‌وجوی دسته‌بندی"/></label>
    <div className="chips" aria-label="فیلتر دسته‌بندی"><button aria-pressed={!rootsOnly} onClick={() => setRootsOnly(false)}>همه دسته‌ها</button><button aria-pressed={rootsOnly} onClick={() => setRootsOnly(true)}>دسته‌های اصلی</button></div>
    {matched.length ? <div className="category-grid directory-grid">{matched.map(c => <Link prefetch={false} className="category-card" key={c.id} href={"/categories/" + encodeURIComponent(c.slug)}>
      {c.image && <img className="picture" src={c.image} alt="" loading="lazy" decoding="async"/>}<div><h3>{c.name}</h3><ArrowLeft size={20}/></div>
    </Link>)}</div> : <div className="empty" role="status">دسته‌بندی مطابق جست‌وجو پیدا نشد.</div>}
  </>;
}
export function Gallery({ images, title }: { images: GalleryImage[]; title: string }) {
  const [active, setActive] = useState(0);
  const image = images[active];
  return <div className="gallery">
    {image ? <img className="picture gallery-stage" src={image.image} alt={image.alt_text || title}/> : <div className="gallery-stage absent">تصویری ثبت نشده است.</div>}
    {images.length > 1 && <div className="thumbnails">{images.map(({ image, alt_text }, index) => <button type="button" key={index} aria-pressed={index === active} aria-label={"نمایش تصویر " + (index + 1)} onClick={() => setActive(index)}><img className="picture" src={image} alt={alt_text || ""}/></button>)}</div>}
  </div>;
}
