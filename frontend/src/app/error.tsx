"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <div className="container status-page"><h1>دریافت اطلاعات ممکن نبود</h1><p>لطفاً لحظه‌ای بعد دوباره امتحان کنید.</p><button className="button" onClick={reset}>تلاش دوباره</button></div>;
}
