import Link from "next/link";
import { RecoveryForms, StoreFeedback } from "@/components/store-forms";
import { signIn, signOut } from "@/app/actions";
import { register } from "@/app/account-actions";
import { ApiTable, DataTable, FieldInput, MutationForm, Panel, ServiceIssue, value } from "@/components/workspace";
import type { Field } from "./operations";
import { authorized, list, type Row } from "@/lib/private-api";
import { first, number } from "@/lib/catalog";
import type { Query } from "@/lib/types";

export const accountNav = [["auth", "ورود و ثبت‌نام"], ["recovery", "بازیابی گذرواژه"], ["dashboard", "داشبورد"], ["profile", "پروفایل و آدرس‌ها"], ["orders", "سفارش‌ها"], ["activity", "پرداخت‌ها و دیدگاه‌ها"]] as const;

const credentials: Field[] = [
  { name: "phone", label: "شماره موبایل", type: "tel", required: true },
  { name: "password", label: "گذرواژه", type: "password", required: true },
];
export function AuthForms({ query }: { query: Query }) {
  return <>
    <Panel title="ورود"><p>{query.login === "invalid" && "شماره موبایل یا گذرواژه معتبر نیست."}{query.login === "limited" && "تعداد درخواست‌های ورود زیاد است."}</p><form className="workspace-form" action={signIn}>
      {credentials.map(field => <FieldInput key={field.name} field={field}/>)}<input name="destination" type="hidden" value="/account/dashboard"/><button className="button">ورود</button>
    </form><Link href="/account/recovery" className="inline-link">گذرواژه را فراموش کرده‌اید؟</Link></Panel>
    <Panel title="ثبت‌نام"><form className="workspace-form" action={register}>
      {credentials.map(field => <FieldInput key={field.name} field={field}/>)}<FieldInput field={{ name: "first_name", label: "نام" }}/><FieldInput field={{ name: "last_name", label: "نام خانوادگی" }}/><button className="button">ساخت حساب</button>
    </form></Panel>
  </>;
}
export async function Recovery({ query }: { query: Query }) {
  let loggedIn = false;
  try { await authorized("auth/me/"); loggedIn = true; } catch {}
  return <Panel title="گذرواژه حساب"><StoreFeedback result={first(query.store)}/><RecoveryForms authenticated={loggedIn}/>{loggedIn ? <MutationForm operation="password" returnTo="/account/recovery" label="تغییر گذرواژه" fields={[
    { name: "old_password", label: "گذرواژه فعلی", type: "password", required: true },
    { name: "password", label: "گذرواژه جدید", type: "password", required: true },
  ]}/> : <Link href="/account/auth" className="inline-link">ورود به حساب</Link>}</Panel>;
}
export async function Dashboard() {
  const info: Row = await authorized("dashboard/overview/");
  return <><Panel title={"خوش آمدید " + ((info.profile as Row).first_name || "")}>
    <div className="metric-grid">{[["favorite_count", "علاقه‌مندی"], ["reviews.count", "دیدگاه"], ["notifications.unread_count", "اعلان خوانده‌نشده"]].map(([key, label]) => <Link href={key === "favorite_count" ? "/favorites" : key === "reviews.count" ? "/account/activity" : "#notifications"} key={key}><strong>{value(info, key)}</strong>{label}</Link>)}</div>
    <form action={signOut}><button className="chips-button">خروج از حساب</button></form></Panel>
    <div id="notifications"><Panel title="اعلان‌ها"><ApiTable endpoint="dashboard/notifications/" columns={[["title","عنوان"],["body","پیام"],["is_read","دیده شده"]]}/></Panel></div>
    <Panel title="جست‌وجوهای اخیر"><ApiTable endpoint="dashboard/searches/" columns={[["term","عبارت"]]}/></Panel>
    <Panel title="بازدیدهای اخیر"><ApiTable endpoint="dashboard/views/" columns={[["product.title","محصول"],["viewed_at","زمان"]]}/></Panel>
  </>;
}
const addressFields = (row: Row = {}): Field[] => [
  { name: "label", label: "عنوان آدرس" }, { name: "recipient_name", label: "گیرنده", required: true },
  { name: "recipient_phone", label: "شماره گیرنده", type: "tel", required: true }, { name: "province", label: "استان", required: true },
  { name: "city", label: "شهر", required: true }, { name: "postal_code", label: "کد پستی", required: true },
  { name: "address_line", label: "نشانی", type: "textarea", required: true }, { name: "is_default", label: "آدرس پیش‌فرض", type: "checkbox" },
].map(f => ({ ...f, value: row[f.name] as string | boolean | undefined })) as Field[];
export async function Profile() {
  const [person, addresses] = await Promise.all([authorized("auth/me/"), list("addresses/")]);
  return <><Panel title="مشخصات حساب"><p dir="ltr">{person.phone}</p><MutationForm operation="profile" returnTo="/account/profile" label="ذخیره مشخصات" fields={[
    { name: "first_name", label: "نام", value: person.first_name }, { name: "last_name", label: "نام خانوادگی", value: person.last_name },
    { name: "email", label: "ایمیل", type: "email", value: person.email },
  ]}/></Panel><Panel title="آدرس‌ها">
    {addresses.rows.map(a => <details key={String(a.id)}><summary>{String(a.label || a.city)} · {String(a.address_line)} {Boolean(a.is_default) && " (پیش‌فرض)"}</summary>
      <MutationForm operation="editAddress" id={String(a.id)} returnTo="/account/profile" label="ذخیره آدرس" fields={addressFields(a)}/>
      <MutationForm operation="removeAddress" id={String(a.id)} returnTo="/account/profile" label="حذف آدرس"/></details>)}
    <h3>آدرس جدید</h3><MutationForm operation="addAddress" returnTo="/account/profile" label="ثبت آدرس" fields={addressFields()}/>
  </Panel></>;
}
export const orderColumns: [string, string][] = [["order_number","شماره سفارش"],["status","وضعیت"],["total_amount","مبلغ"],["currency","واحد"],["created_at","تاریخ"]];
export const paymentColumns: [string, string][] = [["id","شناسه"],["order","سفارش"],["provider","درگاه"],["amount","مبلغ"],["currency","واحد"],["status","وضعیت"]];
export async function Orders({ query }: { query: Query }) {
  const id = first(query.id);
  if (!/^\d+$/.test(id)) return <Panel title="سفارش‌های من"><ApiTable endpoint="orders/" columns={orderColumns} page={readPage(query)} route="/account/orders" actions={order => <Link className="inline-link" href={"/account/orders?id=" + order.id}>جزئیات</Link>}/></Panel>;
  const order = await authorized("orders/" + id + "/");
  return <Panel title={"سفارش " + order.order_number}>
    <DataTable rows={[order]} columns={orderColumns}/><h3>اقلام سفارش</h3><DataTable rows={order.items} columns={[["product_title","محصول"],["quantity","تعداد"],["line_total","جمع"]]}/>
    <p>{value(order,"shipping_address_snapshot.city")} · {value(order,"shipping_address_snapshot.address_line")}</p>
    {order.status === "pending_payment" && <div className="actions"><Link className="button" href={"/checkout/payment?order=" + id}>پرداخت</Link><MutationForm operation="cancelOrder" id={id} returnTo={"/account/orders?id=" + id} label="لغو سفارش"/></div>}
  </Panel>;
}
const reviewFields = (r: Row = {}): Field[] => [{ name: "title", label: "عنوان", value: String(r.title ?? ""), required: true },
  { name: "rating", label: "امتیاز", type: "select", options: [1,2,3,4,5].map(n => [String(n), number.format(n)]), value: Number(r.rating || 5) },
  { name: "comment", label: "دیدگاه", type: "textarea", value: String(r.comment ?? ""), required: true }];
export async function Activity({ query }: { query: Query }) {
  const productId = first(query.product);
  return <><Panel title="پرداخت‌ها"><ApiTable endpoint="payments/" columns={paymentColumns} page={readPage(query)} route="/account/activity" actions={row => <Link href={"/checkout/result?id=" + row.id}>جزئیات</Link>}/></Panel>
    <Panel title="دیدگاه‌های من">
      <ApiTable endpoint="dashboard/reviews/" columns={[["title","عنوان"],["rating","امتیاز"],["is_approved","تأیید شده"]]} actions={row => <details><summary>ویرایش</summary><MutationForm operation="editReview" id={String(row.id)} returnTo="/account/activity" label="ذخیره" fields={reviewFields(row)}/><MutationForm operation="removeReview" id={String(row.id)} returnTo="/account/activity" label="حذف"/></details>}/>
      {/^[1-9]\d*$/.test(productId) && <MutationForm operation="addReview" id={productId} returnTo="/account/activity" fields={reviewFields()} label="ثبت دیدگاه"/>}
    </Panel></>;
}
export const readPage = (query: Query) => Math.min(100000, Math.max(1, parseInt(first(query.page), 10) || 1));
export async function customerSection(section: string, query: Query) {
  try {
    switch (section) {
      case "auth": return <AuthForms query={query}/>;
      case "recovery": return await Recovery({ query });
      case "dashboard": return await Dashboard();
      case "profile": return await Profile();
      case "orders": return await Orders({ query });
      case "activity": return await Activity({ query });
    }
  } catch (error) { return <ServiceIssue error={error}/>; }
}
