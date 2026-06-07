---
title: "Next.js standalone in Docker — Run `node server.js`, not `next start`"
tags: ["nextjs", "docker", "deployment", "standalone", "frontend"]
topic_canonical: "nextjs-standalone-docker-run-node-server-js"
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

# Next.js standalone in Docker — Run `node server.js`

## 🎯 چالش / Challenge
Docker image یک اپ Next.js با `output: 'standalone'` به‌خوبی build می‌شود،
ولی کانتینر هنگام اجرا فوراً می‌میرد:

```
> next start
sh: next: not found
==> Exited with status 127
```

علت: خروجی **standalone** یک `server.js` خودکفا و یک `node_modules` حداقلی
تولید می‌کند و **باینری `next` (CLI) را شامل نمی‌شود**. بنابراین
`npm start` → `next start` در runtime پیدا نمی‌شود.

## 💡 راه‌حل / Solution
سرور standalone را مستقیم با Node اجرا کن و host را روی `0.0.0.0` بگذار:

## 🧪 نمونه کد (Anonymized)
```dockerfile
# --- builder ---
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci                       # devDeps لازم‌اند تا next build اجرا شود
COPY . .
RUN NEXT_TELEMETRY_DISABLED=1 npm run build   # خروجی: .next/standalone

# --- runner ---
FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
ENV HOSTNAME=0.0.0.0             # تا پلتفرم بتواند سرویس را ببیند
# PORT را میزبان (PaaS) تزریق می‌کند؛ server.js آن را می‌خواند
CMD ["node", "server.js"]       # ✅ نه "npm start" / "next start"
```

## ⚠️ نکات حیاتی / Pitfalls
- **`npm ci --omit=dev` در stage build اشتباه است:** `next build` به devDeps
  (typescript، tailwind، postcss، @types) نیاز دارد. image نهایی به‌خاطر
  کپی فقطِ خروجی standalone کوچک می‌ماند، پس `--omit=dev` لازم نیست.
- مسیرها باید دقیق باشند: `server.js` در ریشهٔ standalone، `public/` و
  `.next/static` کنار آن. این سه را در stage runner کپی کن.
- **`HOSTNAME=0.0.0.0`** را ست کن؛ بعضی نسخه‌ها پیش‌فرض به `localhost` bind
  می‌کنند و health-check پلتفرم به آن نمی‌رسد.
- پلتفرم `PORT` را تزریق می‌کند؛ `server.js` آن را از `process.env.PORT`
  می‌خواند — PORT را هاردکد نکن.
- اگر سرویس Docker است، می‌توانی به‌جای ری‌بیلد، فعلاً **Docker Command** را
  در داشبورد روی `node server.js` override کنی (فیکس فوری).
- نیاز به `public/`: اگر پوشهٔ `public` وجود نداشته باشد، `COPY .../public`
  می‌تواند بیفتد — یک `public/.gitkeep` نگه‌اش دار.

## ✅ Resolution
- Status: solved
- Evidence: با تغییر CMD به `node server.js` (+ `HOSTNAME=0.0.0.0`) خطای
  `next: not found` رفع شد و سرویس بالا آمد (frontend در PaaS به وضعیت
  Deployed رسید و کاربر سبزشدن را دید).

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- Docker image برای Next.js با `output: 'standalone'`.

### Does NOT apply when (anti-pattern)
- بدون standalone و با `node_modules` کامل در runtime → آنجا `next start` کار می‌کند.
- static export (`output: 'export'`) → اصلاً سرور Node نداری.

### Prerequisites
- `output: 'standalone'` در next.config، Dockerfile دو-مرحله‌ای.

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — دیپلوی Docker یک frontend.
- مرتبط: `nextjs-paas-static-vs-web-service`
