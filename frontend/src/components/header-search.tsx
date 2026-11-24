"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

type Suggestions = { products: { id: number; title: string; slug: string }[]; categories: { id: number; name: string; slug: string }[] };
const searchApi = createApi({
  reducerPath: "searchApi",
  baseQuery: fetchBaseQuery({ baseUrl: "/api" }),
  endpoints: builder => ({
    suggestions: builder.query<Suggestions, string>({ query: term => ({ url: "search", params: { q: term } }), keepUnusedDataFor: 30 }),
  }),
});
const makeStore = () => configureStore({ reducer: { [searchApi.reducerPath]: searchApi.reducer }, middleware: getDefault => getDefault().concat(searchApi.middleware) });

function SearchInput() {
  const [query, setQuery] = useState("");
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setTerm(query.trim()), 250);
    return () => window.clearTimeout(id);
  }, [query]);
  const { currentData } = searchApi.useSuggestionsQuery(term, { skip: !open || term.length < 2 });
  const suggestions = currentData ? [
    ...currentData.products.map(row => ({ ...row, href: "/products/" + encodeURIComponent(row.slug) })),
    ...currentData.categories.map(row => ({ ...row, title: row.name, href: "/categories/" + encodeURIComponent(row.slug) })),
  ] : [];
  return <form className="header-search" action="/search" role="search"
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
    onKeyDown={event => { if (event.key === "Escape") setOpen(false); }}>
    <button className="search-icon" aria-label="اجرای جست‌وجو"><Search size={18}/></button>
    <input aria-label="جست‌وجوی محصولات" name="q" minLength={2} maxLength={120} required placeholder="جست‌وجو در محصولات و دسته‌بندی‌ها" value={query}
      onFocus={() => setOpen(true)} onChange={event => { setOpen(true); setQuery(event.target.value); }} autoComplete="off"/>
    {open && query.trim() === term && suggestions.length > 0 && <ul className="suggestions" aria-label="پیشنهادهای جست‌وجو">
      {suggestions.map(row => <li key={row.href}><Link prefetch={false} href={row.href} onClick={() => setOpen(false)}>{row.title}</Link></li>)}
    </ul>}
  </form>;
}
export function HeaderSearch() {
  const [store] = useState(makeStore);
  return <Provider store={store}><SearchInput/></Provider>;
}
