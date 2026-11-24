import type { Metadata } from "next";
import "@fontsource-variable/vazirmatn";
import "./tokens.css";
import "./globals.css";
import { Footer, Header } from "@/components/storefront";

export const metadata: Metadata = { title: { default: "وودزی هوم | مبلمان و دکور خانه", template: "%s | وودزی هوم" }, description: "جست‌وجو و مرور مبلمان، دکور و دسته‌بندی‌های وودزی هوم" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="fa" dir="rtl"><body><a className="skip-link" href="#content">رفتن به محتوای اصلی</a><Header/><main id="content">{children}</main><Footer/></body></html>;
}
