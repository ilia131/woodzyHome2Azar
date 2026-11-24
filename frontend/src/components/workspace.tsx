import Link from "next/link";
import { renewSession } from "@/app/actions";
import type { ReactNode } from "react";
import { mutate } from "@/app/account-actions";
import { Crumbs, LinkButton } from "./storefront";
import type { Field, OperationKey } from "@/features/operations";
import { BackendError, list, type Row } from "@/lib/private-api";
import { first, number } from "@/lib/catalog";
import type { Query } from "@/lib/types";

export type Columns = [key: string, label: string][];
export type Nav = readonly (readonly [slug: string, label: string])[];
const status: Record<string, string> = { pending_payment: "در انتظار پرداخت", paid: "پرداخت‌شده", processing: "در حال آماده‌سازی", cancelled: "لغوشده", expired: "منقضی‌شده", completed: "تکمیل‌شده", succeeded: "موفق", failed: "ناموفق", pending: "در انتظار", requires_review: "نیاز به بررسی", available: "موجود", out_of_stock: "ناموجود", not_visible: "پنهان", insufficient_stock: "موجودی ناکافی" };
export function value(row: Row, key: string): string {
  const item = key.split(".").reduce<unknown>((current, part) => current && typeof current === "object" ? (current as Row)[part] : undefined, row);
  if (item == null || item === "") return "—";
  if (typeof item === "boolean") return item ? "بله" : "خیر";
  if (typeof item === "number") return number.format(item);
  if (typeof item === "string") return status[item] ?? item;
  return "—";
}
export function Feedback({ query }: { query: Query }) {
  const messages: Record<string, string> = { saved: "تغییرات ثبت شد.", registered: "حساب ساخته شد. اکنون وارد شوید.", "400": "اطلاعات فرم پذیرفته نشد. مقادیر را بررسی کنید.", "403": "مجوز انجام این عملیات را ندارید.", "404": "مورد درخواستی در دسترس نیست.", "409": "عملیات با وضعیت فعلی سازگار نیست. اطلاعات را دوباره بررسی کنید.", "429": "تعداد درخواست‌ها بیش از حد مجاز است.", "503": "این سرویس اکنون در دسترس نیست.", unavailable: "اتصال به سرویس برقرار نشد." };
  const key = first(query.feedback);
  return key ? <p className="workspace-feedback" role="status">{messages[key] ?? "درخواست انجام نشد."}</p> : null;
}
export function Workspace({ root, section, title, nav, children, query }: { root: string; section: string; title: string; nav: Nav; children: ReactNode; query: Query }) {
  return <div className="container workspace"><Crumbs trail={[[title]]}/><div className="workspace-heading"><h1>{title}</h1></div>
    <div className="workspace-layout"><nav className="workspace-nav" aria-label="بخش‌های مرتبط">{nav.map(([slug, text]) => <Link key={slug} aria-current={section === slug ? "page" : undefined} href={root + "/" + slug}>{text}</Link>)}</nav>
    <div className="workspace-content"><Feedback query={query}/>{children}</div></div>
  </div>;
}
export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="workspace-panel"><h2>{title}</h2>{children}</section>;
}
export function ServiceIssue({ error }: { error: unknown }) {
  if (error instanceof BackendError && error.status === 401) return <div className="empty">برای دسترسی به اطلاعات حساب <Link href="/account/auth" className="inline-link">وارد شوید</Link>.<form action={renewSession}><button className="chips-button">تمدید نشست</button></form></div>;
  if (error instanceof BackendError && error.status === 403) return <p className="empty">حساب شما مجوز مشاهدهٔ این بخش را ندارد.</p>;
  if (error instanceof BackendError && error.status === 404) return <p className="empty">اطلاعات درخواستی پیدا نشد.</p>;
  return <p className="empty">اتصال به سرویس برقرار نشد. کمی بعد دوباره تلاش کنید.</p>;
}
export function DataTable({ rows, columns, actions, caption }: { rows: Row[]; columns: Columns; actions?: (row: Row) => ReactNode; caption?: string }) {
  if (!rows.length) return <p className="empty">موردی برای نمایش وجود ندارد.</p>;
  return <div className="table-scroll" tabIndex={0}><table>
    {caption && <caption>{caption}</caption>}
    <thead><tr>{columns.map(([key, label]) => <th scope="col" key={key}>{label}</th>)}{actions && <th scope="col">عملیات</th>}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={String(row.id ?? index)}>{columns.map(([key]) => <td key={key}>{value(row, key)}</td>)}{actions && <td>{actions(row)}</td>}</tr>)}</tbody>
  </table></div>;
}
export async function ApiTable({ endpoint, columns, actions, page = 1, route }: { endpoint: string; columns: Columns; actions?: (row: Row) => ReactNode; page?: number; route?: string }) {
  try {
    const { rows, next, previous } = await list(endpoint + (route ? (endpoint.includes("?") ? "&" : "?") + "page=" + page : ""));
    return <><DataTable rows={rows} columns={columns} actions={actions}/>{route && (next || previous) && <nav className="pagination" aria-label="صفحه‌بندی"><span>{number.format(page)}</span>{previous && <Link href={route + (route.includes("?") ? "&" : "?") + "page=" + (page - 1)}>صفحه قبل</Link>}{next && <Link href={route + (route.includes("?") ? "&" : "?") + "page=" + (page + 1)}>صفحه بعد</Link>}</nav>}</>;
  } catch (error) { return <ServiceIssue error={error}/>; }
}
export function FieldInput({ field }: { field: Field }) {
  const v = field.value;
  if (field.type === "hidden") return <input type="hidden" name={field.name} value={String(v ?? "")}/>;
  if (field.type === "checkbox") return <label className="checkbox-field"><input name={field.name} type="checkbox" defaultChecked={Boolean(v)}/>{field.label}</label>;
  return <label>{field.label}{field.type === "select" ? <select name={field.name} aria-label={field.label} required={field.required} defaultValue={String(v ?? "")}>{field.options?.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select> : field.type === "textarea" ? <textarea name={field.name} aria-label={field.label} defaultValue={String(v ?? "")} rows={4} required={field.required}/> : <input name={field.name} aria-label={field.label} type={field.type ?? "text"} defaultValue={field.type === "file" ? undefined : String(v ?? "")} required={field.required} min={field.min} accept={field.type === "file" ? "image/jpeg,image/png,image/webp" : undefined} step={field.type === "number" ? 1 : undefined}/>}</label>;
}
export function MutationForm({ operation, id = "", returnTo, fields = [], label }: { operation: OperationKey; id?: string; returnTo: string; fields?: Field[]; label: string }) {
  return <form action={mutate.bind(null, operation, id, returnTo)} className={fields.some(f => f.type !== "hidden") ? "workspace-form" : "inline-form"}>{fields.map(field => <FieldInput field={field} key={field.name}/>)}<button className="button">{label}</button></form>;
}
export function ConnectionRequired() {
  return <div className="empty">برای استفاده از امکانات حساب، فروشگاه باید به بک‌اند متصل باشد.<div><LinkButton href="/products" secondary>مرور محصولات</LinkButton></div></div>;
}
