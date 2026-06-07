---
title: "Next.js on a PaaS — Static Site vs Web Service (output: standalone)"
tags: ["nextjs", "deployment", "render", "docker", "static-export", "frontend"]
topic_canonical: "nextjs-paas-static-vs-web-service"
source:
  type: "chat-import"
  origin: "claude-code"
  imported_at: "2026-06-07T19:30:00Z"
created_at: "2026-06-07T19:30:00Z"
updated_at: "2026-06-07T19:30:00Z"
merged_from: []
resolution_status: "solved"
recurrence_count: 1
user_confirmed: true
---

# Next.js on a PaaS — Static Site vs Web Service

## 🎯 چالش / Challenge
یک اپ Next.js روی PaaS به‌عنوان **Static Site** ساخته شده و دیپلوی می‌افتد.
نشانه‌ها:
- build command چیزی شبیه `vite build` یا انتظار خروجی `out/` دارد:
  `Could not resolve entry module "index.html"`.
- یا build موفق است ولی publish directory خالی است.

علت ریشه‌ای: این اپ Next.js است (با `output: 'standalone'` یا قابلیت‌های
سروری مثل `rewrites`/`headers`/`server actions`) — یک **سرور Node** تولید
می‌کند، نه فایل استاتیک. «Static Site» فقط فایل HTML/JS استاتیک سرو می‌کند.

## 💡 راه‌حل / Solution
نوع سرویس را با نوع build هم‌تراز کن:

- **اگر اپ سروری است** (`output: 'standalone'`، rewrites/headers/SSR/route
  handlers): آن را **Web Service** بساز — ترجیحاً با **Docker** (از Dockerfile
  پروژه). نوع سرویس روی اکثر PaaSها بعد از ساخت **قابل‌تغییر نیست**؛ پس سرویس
  Static را **حذف** و یک Web Service جدید بساز.
- **اگر واقعاً می‌خواهی استاتیک باشد:** باید `output: 'export'` بگذاری،
  `images.unoptimized: true`، و `rewrites/headers/server-actions` را حذف کنی
  (اینها در static export کار نمی‌کنند) و publish dir را `out` بگذاری.

## 🧪 نمونه کد (Anonymized)
```js
// next.config.js — حالت سروری (نیازمند Web Service / Docker)
const nextConfig = {
  output: 'standalone',
  async rewrites() { return [{ source: '/api/backend/:path*',
    destination: `${process.env.NEXT_PUBLIC_API_URL}/api/:path*` }]; },
};
module.exports = nextConfig;
```
تنظیمات سرویس (Web Service / Docker):
```
Runtime:        Docker
Root Directory: frontend           # جایی که Dockerfile هست
Env:            NEXT_PUBLIC_API_BASE_URL=https://<backend-host>
```

## ⚠️ نکات حیاتی / Pitfalls
- نوع سرویس (Static / Web / Worker) معمولاً **پس از ساخت قابل‌تغییر نیست** →
  باید حذف و از نو بسازی.
- اگر PaaS به‌خاطر وجود یک Dockerfile در ریپو، runtime را خودکار «Docker»
  تشخیص نداد، **دستی Docker را انتخاب کن** و `Root Directory` را درست بگذار.
- `NEXT_PUBLIC_*` در **زمان build** درون باندل می‌رود؛ مطمئن شو قبل از build
  ست شده (نه فقط runtime).
- static export قابلیت‌های سروری را بی‌صدا غیرفعال می‌کند؛ اگر به rewrite/SSR
  نیاز داری، static نرو.

## ✅ Resolution
- Status: solved
- Evidence: پس از بازساخت frontend به‌صورت Web Service/Docker، Docker build
  موفق شد و سرویس در فهرست PaaS با runtime «Docker» و وضعیت Deployed ظاهر شد
  (کاربر هر ۵ سرویس را سبز دید).

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- دیپلوی Next.js (یا هر فریم‌ورک SSR) که به‌اشتباه به‌عنوان static site پیکربندی شده.

### Does NOT apply when (anti-pattern)
- اپ واقعاً یک SPA/Static خالص است (CRA/Vite بدون SSR) → همان Static Site درست است.

### Prerequisites
- یک Dockerfile برای اپ (یا قابلیت Web Service در PaaS)، و درک اینکه اپ سروری است یا استاتیک.

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — دیپلوی frontend روی PaaS.
- مرتبط: `nextjs-standalone-docker-run-node-server-js`
