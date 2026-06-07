---
title: "npm ci Needs a Lockfile In Sync — A Stub package-lock.json Fails the Build"
tags: ["npm", "nodejs", "ci", "docker", "deployment", "lockfile"]
topic_canonical: "npm-ci-requires-synced-lockfile"
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

# npm ci Needs a Lockfile In Sync With package.json

## 🎯 چالش / Challenge
build (در Docker یا CI) موقع نصب وابستگی‌ها می‌افتد، چون `package-lock.json`
یک **stub** است (مثلاً فقط چند خط با نام پکیج root و بدون هیچ dependency)،
ولی `package.json` ده‌ها dependency دارد:

```
npm error `npm ci` can only install packages when your package.json and
package-lock.json are in sync ... Missing: <pkg> from lock file
```

`npm ci` (برخلاف `npm install`) **lockfile را بازنویسی نمی‌کند**؛ فقط دقیقاً
طبق lockfile نصب می‌کند و اگر با package.json نخواند، fail می‌دهد.

## 💡 راه‌حل / Solution
یک lockfile کامل و sync تولید کن و commit کن:

## 🧪 نمونه کد (Anonymized)
```bash
cd frontend           # جایی که package.json هست
npm install           # lockfile کامل را (باز)تولید می‌کند
git add package-lock.json
git commit -m "chore: regenerate package-lock.json in sync with package.json"
# حالا 'npm ci' در Docker/CI کار می‌کند
```

## ⚠️ نکات حیاتی / Pitfalls
- `npm ci` نیاز دارد lockfile دقیقاً با package.json بخواند؛ هر drift =
  شکستِ build. `npm install` خطا را پنهان می‌کند چون lockfile را بازمی‌نویسد.
- یک `package-lock.json` تقریباً خالی (lockfileVersion بدون بخش `packages`
  واقعی) علامتِ یک scaffold ناقص است — قبل از دیپلوی بازتولیدش کن.
- lockfile بازتولیدشده را **commit** کن؛ build‌های reproducible به آن وابسته‌اند.
- در Dockerfile دو-مرحله‌ای برای Next.js: در stage build از `--omit=dev`
  استفاده نکن (ابزارهای build مثل typescript/tailwind/postcss devDep‌اند).

## ✅ Resolution
- Status: solved
- Evidence: پس از بازتولید lockfile با `npm install` و commit، `npm ci` در
  Docker build بدون خطا گذشت و Next.js با موفقیت build شد.

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- هر build مبتنی بر `npm ci` (Docker/CI) که lockfile ناقص/ناهماهنگ دارد.

### Does NOT apply when (anti-pattern)
- عمداً از `npm install` در build استفاده می‌کنی (کندتر و کمتر reproducible،
  ولی lockfile را تحمل می‌کند). برای builds پایدار `npm ci` بهتر است.

### Prerequisites
- Node/npm؛ یک `package.json` معتبر.

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — build frontend روی PaaS/Docker.
- مرتبط: `nextjs-standalone-docker-run-node-server-js`
