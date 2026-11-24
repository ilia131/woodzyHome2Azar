import Link from "next/link";
import { randomUUID } from "node:crypto";
import { authorized, list, type Row } from "@/lib/private-api";
import { first, toman } from "@/lib/catalog";
import type { Query } from "@/lib/types";
import { DataTable, MutationForm, Panel, ServiceIssue, value } from "@/components/workspace";
import { LinkButton } from "@/components/storefront";
import { paymentColumns, readPage } from "./customer";

export const checkoutNav = [["cart","سبد خرید"],["details","ثبت سفارش"],["payment","انتخاب پرداخت"],["result","نتیجه پرداخت"]] as const;
const cartColumns: [string, string][] = [["product_title","محصول"],["quantity","تعداد"],["availability","وضعیت"],["line_total","جمع"]];

async function Cart({query}: {query: Query}) {
  const page = readPage(query);
  const cart = await authorized("cart/?page=" + page);
  return <Panel title="اقلام سبد خرید"><DataTable rows={cart.results} columns={cartColumns} actions={row => <div className="stack">
    <MutationForm operation="changeCart" id={String(row.id)} returnTo={"/checkout/cart?page=" + page} label="به‌روزرسانی" fields={[{ name: "quantity", label: "تعداد", type: "number", value: Number(row.quantity), min: 1, required: true }]}/>
    <MutationForm operation="removeCart" id={String(row.id)} returnTo="/checkout/cart" label="حذف کالا"/>
  </div>}/>
  {(cart.previous || cart.next) && <nav className="pagination" aria-label="صفحه‌بندی">{cart.previous && <Link href={"?page=" + (page - 1)}>صفحه قبل</Link>}{cart.next && <Link href={"?page=" + (page + 1)}>صفحه بعد</Link>}</nav>}
  <p>جمع کالاهای قابل خرید {toman(String(cart.summary.subtotal))}</p>{cart.summary.available_item_count > 0 && <LinkButton href="/checkout/details">ادامه خرید</LinkButton>}</Panel>;
}
async function CheckoutDetails() {
  const [cart, addresses] = await Promise.all([authorized("cart/"), list("addresses/")]);
  return <Panel title="تأیید اطلاعات سفارش"><DataTable rows={cart.results} columns={cartColumns}/><p>جمع فعلی {toman(String(cart.summary.subtotal))}</p>
    {!addresses.rows.length ? <LinkButton href="/account/profile">ثبت آدرس</LinkButton> : cart.summary.available_item_count > 0 ?
      <MutationForm operation="order" returnTo="/checkout/details" label="ثبت سفارش" fields={[{ name: "address_id", label: "آدرس تحویل", type: "select", value: String(addresses.rows.find(row => row.is_default)?.id ?? ""), options: addresses.rows.map(row => [String(row.id), String(row.address_line)]), required: true }]}/>
      : <p>سبد شما کالای قابل سفارش ندارد.</p>}
  </Panel>;
}
const mockCheckout = process.env.WOODZY_TEST_PAYMENTS === "1";
const validId = (query: Query, field: string) => /^[1-9]\d{0,15}$/.test(first(query[field])) ? first(query[field]) : "";
async function PaymentSelection({ query }: { query: Query }) {
  const orderId = validId(query, "order");
  if (!orderId) return <Panel title="سفارش برای پرداخت"><LinkButton href="/account/orders">انتخاب از سفارش‌ها</LinkButton></Panel>;
  const order: Row = await authorized("orders/" + orderId + "/");
  return <Panel title={"پرداخت سفارش " + order.order_number}><p>{toman(String(order.total_amount))}</p>
    {order.status === "pending_payment" && mockCheckout ? <MutationForm operation="payment" returnTo={"/checkout/payment?order=" + orderId} label="شروع پرداخت آزمایشی" fields={[
      { name: "order_id", label: "", type: "hidden", value: orderId }, { name: "idempotency_key", label: "", type: "hidden", value: randomUUID() },
      { name: "provider", label: "درگاه", type: "select", options: [["mock", "درگاه آزمایشی"]], value: "mock" },
    ]}/> : <p>{order.status === "pending_payment" ? "درگاه پرداخت در دسترس نیست." : "وضعیت سفارش " + value(order, "status")}</p>}</Panel>;
}
async function PaymentResult({ query }: { query: Query }) {
  const id = validId(query, "id");
  if (!id) return <Panel title="پیگیری پرداخت"><LinkButton href="/account/activity">تاریخچه پرداخت‌ها</LinkButton></Panel>;
  const payment: Row = await authorized("payments/" + id + "/status/");
  return <Panel title="وضعیت تأییدشده توسط فروشگاه"><DataTable rows={[payment]} columns={paymentColumns}/>
    <Link className="inline-link" href={"/checkout/result?id=" + id}>بررسی دوباره وضعیت</Link>
    {mockCheckout && payment.provider === "mock" && ["pending","created","processing"].includes(String(payment.status)) && <MutationForm operation="simulate" id={id} returnTo={"/checkout/result?id=" + id} label="ارسال سناریوی آزمایشی" fields={[
      { name: "scenario", label: "سناریوی درگاه آزمایشی", type: "select", options: [["success","موفق"],["failure","ناموفق"],["cancel","لغو"],["timeout","اتمام مهلت"]], value: "success" },
    ]}/>}
  </Panel>;
}
export async function checkoutSection(section: string, query: Query) {
  try {
    switch (section) {
      case "cart": return await Cart({ query });
      case "details": return await CheckoutDetails();
      case "payment": return await PaymentSelection({ query });
      case "result": return await PaymentResult({ query });
    }
  } catch (error) { return <ServiceIssue error={error}/>; }
}
