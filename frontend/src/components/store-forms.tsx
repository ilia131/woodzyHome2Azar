import { submitStoreForm } from "@/app/store-actions";
import { demo } from "@/lib/catalog";
import { FieldInput } from "./workspace";
import type { Field } from "@/features/operations";

const phone: Field = { name: "phone", label: "شماره موبایل", type: "tel", required: true };
const email: Field = { name: "email", label: "ایمیل", type: "email", required: true };
const code: Field = { name: "token", label: "کد دریافتی", required: true };
const password: Field = { name: "password", label: "گذرواژه", type: "password", required: true };
type Flow = Parameters<typeof submitStoreForm>[0];
const messages: Record<string,string> = {
  recovery: "اگر ایمیل تأییدشده با حساب مطابقت داشته باشد، کد بازیابی ارسال خواهد شد.",
  reset: "گذرواژه تغییر کرد. با گذرواژه جدید وارد شوید.",
  enroll: "درخواست ارسال کد تأیید ثبت شد.",
  verify: "ایمیل بازیابی تأیید شد.",
  contact: "پیام شما در صندوق پیام فروشگاه ثبت شد.",
  newsletter: "درخواست ثبت شد. برای تأیید، ایمیل را بررسی کنید.",
  newsletterCode: "درخواست خبرنامه تأیید شد.",
  "400": "اطلاعات یا کد را بررسی کنید.", "401": "ابتدا وارد حساب شوید.",
  "429": "تعداد درخواست‌ها بیش از حد مجاز است.", "503": "سرویس ارسال ایمیل اکنون در دسترس نیست.",
};
export function StoreFeedback({ result }: { result: string }) {
  return result ? <p className="workspace-feedback" role="status">{messages[result] ?? "سرویس اکنون در دسترس نیست."}</p> : null;
}
function PublicForm({ flow, label, fields }: { flow: Flow; label: string; fields: Field[] }) {
  return <form className="workspace-form" action={submitStoreForm.bind(null, flow)}>
    {fields.map(field => <FieldInput key={field.name} field={field}/>)}
    <button className="button">{label}</button>
  </form>;
}
export function RecoveryForms({ authenticated }: { authenticated: boolean }) {
  if (demo) return <p>بازیابی گذرواژه به اتصال فروشگاه و تنظیم سرویس ایمیل نیاز دارد.</p>;
  return <>
    <h3>درخواست بازیابی</h3><PublicForm flow="recovery" label="درخواست کد بازیابی" fields={[phone, email]}/>
    <h3>ثبت گذرواژهٔ جدید</h3><PublicForm flow="reset" label="ثبت گذرواژهٔ جدید" fields={[phone, code, { ...password, label: "گذرواژهٔ جدید" }]}/>
    {authenticated && <><h3>تأیید ایمیل برای بازیابی</h3>
      <PublicForm flow="enroll" label="ارسال کد تأیید ایمیل" fields={[email, { ...password, label: "گذرواژهٔ فعلی" }]}/>
      <PublicForm flow="verify" label="تأیید ایمیل بازیابی" fields={[code]}/>
    </>}
  </>;
}
export function ContactForm({ result }: { result: string }) {
  return <><StoreFeedback result={result}/>{demo ? <p>صندوق پیام پس از اتصال به سرور فروشگاه در دسترس است.</p> : <PublicForm flow="contact" label="ارسال پیام" fields={[
    { name: "name", label: "نام", required: true }, email, { name: "message", label: "پیام", type: "textarea", required: true },
  ]}/>}</>;
}
export function NewsletterForms({ result }: { result: string }) {
  return <><StoreFeedback result={result}/>{demo ? <p>خبرنامه پس از اتصال به سرویس فروشگاه در دسترس است.</p> : <>
    <PublicForm flow="newsletter" label="درخواست کد خبرنامه" fields={[email, {
      name: "action", label: "نوع درخواست", type: "select", options: [["subscribe", "عضویت"], ["unsubscribe", "لغو عضویت"]],
    }]}/>
    <PublicForm flow="newsletterCode" label="تأیید درخواست خبرنامه" fields={[code]}/>
  </>}</>;
}
