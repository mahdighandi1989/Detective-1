---
title: "Celery on a PaaS — Correct `-A` Target and Use a Background Worker"
tags: ["celery", "deployment", "render", "fastapi", "background-worker", "python"]
topic_canonical: "celery-app-target-and-worker-service-type"
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

# Celery on a PaaS — Correct `-A` Target and Worker Service Type

## 🎯 چالش / Challenge
دیپلوی celery worker می‌افتد. دو اشتباه رایج که با هم اتفاق می‌افتند:

1. **هدف `-A` غلط است.** start command روی ماژول اپ وب اشاره می‌کند
   (`celery -A app.main worker`)، در حالی‌که اپ Celery جای دیگری است. نتیجه:
   ```
   AttributeError: 'FastAPI' object has no attribute 'user_options'
   ```
   (celery شیء `app` ماژول را برمی‌دارد که یک FastAPI است، نه Celery.)

2. **نوع سرویس غلط است.** worker به‌عنوان «Web Service» ساخته شده، پس پلتفرم
   منتظر باز شدن یک پورت می‌ماند:
   ```
   Port scan timeout reached, no open ports detected.
   ```
   یک celery worker هیچ پورتی باز نمی‌کند.

## 💡 راه‌حل / Solution
1. `-A` را به ماژولی که **نمونهٔ Celery** را دارد بده (نه ماژول اپ وب):
   ```
   celery -A app.workers.celery_app worker --loglevel=info
   ```
2. worker را به‌عنوان **Background Worker** بساز (نه Web Service). چون نوع
   سرویس بعد از ساخت قابل‌تغییر نیست، سرویس قبلی را حذف و از نو بساز.

## 🧪 نمونه کد (Anonymized)
```python
# app/workers/celery_app.py  ← نمونهٔ Celery اینجاست
from celery import Celery
from app.core.config import settings
celery_app = Celery(
    "worker",
    broker=str(settings.CELERY_BROKER_URL),
    backend=str(settings.CELERY_RESULT_BACKEND),
    include=["app.workers.tasks"],
)
```
```
# تنظیمات Background Worker روی PaaS
Type:           Background Worker          # نه Web Service
Root Directory: backend
Build:          pip install -r requirements.txt
Start:          celery -A app.workers.celery_app worker --loglevel=info
Env:            DATABASE_URL, REDIS_URL, CELERY_BROKER_URL,
                CELERY_RESULT_BACKEND, SECRET_KEY
```

## ⚠️ نکات حیاتی / Pitfalls
- celery برای `-A <module>` ابتدا attribute به نام `app` را امتحان می‌کند؛
  اگر ماژول اپ وب هم یک `app` (FastAPI) داشته باشد، celery همان را برمی‌دارد
  و با خطای نامفهوم می‌میرد. **همیشه به ماژولِ celery اشاره کن** (یا
  `-A pkg.module:celery_app`).
- **هیچ فیکس کدی نمی‌تواند `app.main` را هم‌زمان برای uvicorn (FastAPI) و
  celery قابل‌استفاده کند** — چون celery اول `app` را می‌گیرد. این یک تنظیمِ
  دیپلوی است، نه باگ کد.
- worker نباید Web Service باشد؛ وگرنه health-check پورت، آن را failed علامت
  می‌زند حتی اگر celery سالم اجرا شود.
- env varهای worker باید کامل باشند (همان‌هایی که Settings لازم دارد):
  معمولاً `CELERY_BROKER_URL` و `CELERY_RESULT_BACKEND` فراموش می‌شوند.

## ✅ Resolution
- Status: solved
- Evidence: پس از تصحیح start command به `app.workers.celery_app` و ساخت
  سرویس به‌صورت Background Worker با env کامل، worker به وضعیت Deployed رسید
  (کاربر سبزشدن celery-worker را تأیید کرد).

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- اپ FastAPI/Django + Celery که worker جدا روی PaaS دیپلوی می‌شود.

### Does NOT apply when (anti-pattern)
- celery app عمداً در همان ماژول entrypoint با نامی غیرمتعارض تعریف شده
  (آنگاه `-A module:celery_name` بده).

### Prerequisites
- Redis/broker در دسترس؛ پلتفرمی که «Background Worker» (بدون پورت) دارد.

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — دیپلوی celery worker روی PaaS.
- مرتبط: `render-dashboard-env-no-shell-interpolation`, `render-pin-python-version-for-wheels`
