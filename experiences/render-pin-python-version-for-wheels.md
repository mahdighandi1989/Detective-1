---
title: "Pin the Python Version on a PaaS to Get Prebuilt Wheels (avoid source builds)"
tags: ["python", "deployment", "render", "pip", "wheels", "packaging"]
topic_canonical: "paas-pin-python-version-for-wheels"
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

# Pin the Python Version on a PaaS to Get Prebuilt Wheels

## 🎯 چالش / Challenge
`pip install -r requirements.txt` روی یک سرویسِ تازه‌ساخته‌ی PaaS می‌افتد،
معمولاً روی پکیجی با اکستنشن نیتیو (مثل `pydantic-core`, `asyncpg`, `lxml`,
`Pillow`, `orjson`):

```
Preparing metadata (pyproject.toml) ... error
maturin failed / Read-only file system (os error 30)
error: metadata-generation-failed  ╰─> pydantic-core
```

علت: پلتفرم یک نسخهٔ **خیلی جدید** پایتون (مثلاً 3.14) را به‌عنوان پیش‌فرض
انتخاب کرده که هنوز برای آن نسخه‌های **پین‌شدهٔ** پکیج‌ها، wheel آماده وجود
ندارد. pip به ساخت از سورس می‌افتد (Rust/maturin/کامپایلر C) و در محیط
read-only/بدون toolchain شکست می‌خورد. (سرویس قدیمی‌تر که کار می‌کرد روی
نسخهٔ قدیمی‌تر پایتون بود → drift نسخه بین سرویس‌ها.)

## 💡 راه‌حل / Solution
نسخهٔ پایتون را پین کن تا با نسخه‌ای که wheel دارد resolve شود. سه راه (هر
کدام کافی است):

- فایل `.python-version` در ریشهٔ سرویس (مثلاً `backend/`).
- فایل `runtime.txt` با `python-3.11.11`.
- متغیر محیطی `PYTHON_VERSION=3.11.11` (سریع‌ترین فیکسِ داشبوردی، بدون merge).

## 🧪 نمونه کد (Anonymized)
```bash
# داخل root directory سرویس
echo "3.11.11" > backend/.python-version
# اگر .gitignore آن را نادیده می‌گیرد، با -f اضافه کن:
git add -f backend/.python-version
```
```yaml
# در render.yaml (Blueprint)
services:
  - type: web
    runtime: python
    rootDir: backend
    envVars:
      - key: PYTHON_VERSION
        value: "3.11.11"
```

## ⚠️ نکات حیاتی / Pitfalls
- **`.python-version` اغلب در `.gitignore` است** (پیش‌فرض pyenv) → با
  `git add -f` اضافه‌اش کن، وگرنه commit نمی‌شود.
- نسخه را در root directory **همان سرویس** بگذار (اگر `rootDir=backend`،
  فایل باید آنجا باشد، نه ریشهٔ ریپو).
- سرویس‌های مختلف ممکن است نسخه‌های متفاوت بگیرند (drift). همه را پین کن تا
  یکدست شوند — مخصوصاً سرویسِ قدیمیِ کارکنده که اگر دوباره deploy شود ممکن
  است نسخهٔ جدید بگیرد و **بشکند**.
- نسخه‌ای را انتخاب کن که requirements پین‌شده‌ات برای آن wheel دارند (اغلب
  همان نسخه‌ای که محیط قبلیِ کارکرده استفاده می‌کرد).

## ✅ Resolution
- Status: solved
- Evidence: پس از ست‌کردن `PYTHON_VERSION=3.11.11`، نصب وابستگی‌ها بدون ساختِ
  از سورس کامل شد و سرویس build شد (worker از حالت Failed به Deployed رفت).

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- خطای ساختِ wheel/maturin/کامپایل هنگام `pip install` روی PaaS، به‌خصوص بعد
  از اینکه پلتفرم نسخهٔ پیش‌فرض پایتون را بالا برده.

### Does NOT apply when (anti-pattern)
- خطا واقعاً مربوط به نبودِ یک system library است (آنجا باید build deps را نصب کنی).
- عمداً به نسخهٔ جدید پایتون نیاز داری (آنگاه نسخهٔ پکیج‌ها را به‌روز کن تا wheel داشته باشند).

### Prerequisites
- requirements با نسخه‌های پین‌شده؛ پلتفرمی که `.python-version`/`runtime.txt`/`PYTHON_VERSION` را می‌خواند.

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — build سرویس پایتون روی PaaS.
- مرتبط: `celery-app-target-and-worker-service-type`
