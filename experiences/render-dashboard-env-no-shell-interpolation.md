---
title: "PaaS Dashboard Env Vars Are Literal — `$OTHER_VAR` Is NOT Interpolated"
tags: ["deployment", "render", "environment-variables", "configuration"]
topic_canonical: "paas-env-var-no-shell-interpolation"
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

# PaaS Dashboard Env Vars Are Literal — `$OTHER_VAR` Is NOT Interpolated

## 🎯 چالش / Challenge
برای اینکه یک env var مقدار env دیگری را بگیرد، در داشبورد PaaS مقدار را
`$REDIS_URL` گذاشته‌ای، ولی اپ می‌افتد چون مقدار **به‌صورت متن خام** رسیده:

```
CELERY_BROKER_URL
  Input should be a valid URL ... input_value='$REDIS_URL'
```

علت: مقدارهای env در داشبورد PaaS **literal** هستند؛ shell-interpolation
انجام نمی‌شود. پس `$REDIS_URL` همان رشتهٔ `"$REDIS_URL"` می‌ماند، نه مقدار
آن متغیر.

## 💡 راه‌حل / Solution
- در داشبورد، **مقدار واقعی را paste کن** (مثلاً همان `redis://...:6379`)،
  نه `$REDIS_URL`.
- اگر می‌خواهی مقادیر را share کنی بدون کپیِ دستی، از قابلیت‌های خودِ PaaS
  استفاده کن:
  - **Blueprint / IaC** با مرجع‌دهی (`fromService`/`fromDatabase`).
  - **Environment Groups** (گروه env مشترک بین سرویس‌ها).

## 🧪 نمونه کد (Anonymized)
```text
# ❌ در فیلد مقدارِ داشبورد:
CELERY_BROKER_URL = $REDIS_URL          # literal، کار نمی‌کند

# ✅ مقدار واقعی:
CELERY_BROKER_URL = redis://red-xxxxxxxx:6379
```
```yaml
# ✅ در render.yaml مرجع‌دهی واقعی کار می‌کند:
envVars:
  - key: CELERY_BROKER_URL
    fromService:
      type: redis
      name: my-redis
      property: connectionString
```

## ⚠️ نکات حیاتی / Pitfalls
- این با **شِل start command** فرق دارد: در `startCommand`، شِل می‌تواند
  `$PORT` را expand کند؛ ولی در **مقدار یک env var** در داشبورد، expand
  نمی‌شود.
- وقتی چند var باید یک مقدار باشند (مثل `REDIS_URL` و `CELERY_BROKER_URL` و
  `CELERY_RESULT_BACKEND`)، هر سه را عیناً همان URL واقعی بگذار.
- اگر مقدار، URL است و فیلد در pydantic از نوع URL است، literal اشتباه
  معمولاً به‌صورت `url_parsing` error ظاهر می‌شود (سرنخ خوبی است).

## ✅ Resolution
- Status: solved
- Evidence: پس از جایگزینی `$REDIS_URL` با رشتهٔ واقعی redis در
  `CELERY_BROKER_URL` و `CELERY_RESULT_BACKEND`، خطای url_parsing رفع شد و
  سرویس بالا آمد.

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- هر PaaS که env varها را در داشبورد به‌صورت literal ذخیره می‌کند و سعی کرده‌ای
  یکی را با `$OTHER` به دیگری ارجاع دهی.

### Does NOT apply when (anti-pattern)
- جایی که پلتفرم صریحاً interpolation/templating را پشتیبانی می‌کند (مستندش را چک کن).

### Prerequisites
- دسترسی به داشبورد سرویس، یا فایل IaC (render.yaml و مشابه).

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — تنظیم env یک worker روی PaaS.
- مرتبط: `celery-app-target-and-worker-service-type`
