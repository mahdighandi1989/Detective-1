---
title: "Pydantic Settings — Expose a Module-Level settings Instance"
tags: ["pydantic", "pydantic-settings", "configuration", "python", "import-error", "fastapi"]
topic_canonical: "pydantic-settings-module-level-settings-instance"
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

# Pydantic Settings — Expose a Module-Level `settings` Instance

## 🎯 چالش / Challenge
اپ هنگام بالا آمدن با خطایی شبیه زیر کرش می‌کند، در حالی‌که کلاس `Settings`
و یک factory مثل `get_settings()` در فایل کانفیگ تعریف شده‌اند:

```
ImportError: cannot import name 'settings' from 'app.core.config'
```

علت: ده‌ها ماژول `from app.core.config import settings` می‌کنند، ولی هیچ
**شیء سطح‌ماژول** به نام `settings` ساخته نشده — فقط کلاس و تابع factory
وجود دارد.

## 💡 راه‌حل / Solution
یک نمونهٔ singleton در سطح ماژول بساز تا importها کار کنند:

1. factory کش‌شده را نگه دار.
2. **یک خط** نمونهٔ ماژول‌سطح اضافه کن.

## 🧪 نمونه کد (Anonymized)
```python
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    # ...

@lru_cache()
def get_settings() -> "Settings":
    return Settings()

# ✅ این خط را اضافه کن — کل کدبیس این را import می‌کند:
settings = get_settings()
```

## ⚠️ نکات حیاتی / Pitfalls
- به‌محض افزودن این خط، `Settings()` در زمان **import** ساخته می‌شود، پس
  هر فیلد required بدون مقدار، خطای import را به یک `pydantic ValidationError`
  («field required») تبدیل می‌کند. یعنی فیکس کد + ست‌کردن env varها با هم
  لازم‌اند.
- اگر بعضی importها داخل `try/except` هستند (fallback) ولی entrypointها
  (مثل `main.py` یا celery app) fail-fast هستند، همان fail-fastها سرویس را
  می‌اندازند تا وقتی این نمونه ساخته شود.
- `@lru_cache` تضمین می‌کند کل پروسه یک نمونهٔ واحد و validate‌شده داشته باشد.

## ✅ Resolution
- Status: solved
- Evidence: در redeploy بعدی، خطای `ImportError: cannot import name 'settings'`
  از لاگ‌ها حذف شد و اجرا به خط `settings = get_settings()` رسید (سپس خطای
  بعدی مربوط به env varهای required ظاهر شد که موضوع جداگانه است).

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
چک‌لیست عمومی وقتی پروژه‌ای یک singleton کانفیگ را import می‌کند:
1. `grep` بزن ببین کد چه چیزی import می‌کند (`import settings` در مقابل
   `import get_settings`).
2. اگر `settings` (نمونه) را import می‌کنند، در فایل کانفیگ آن را بساز.
3. اگر `get_settings()` را import می‌کنند، نیازی به نمونهٔ ماژول‌سطح نیست.
4. هر دو را پشتیبانی کن: نمونهٔ ماژول‌سطح را از همان factory کش‌شده بساز.

### Applies when
- چند ماژول مستقیماً یک شیء `settings` را از ماژول کانفیگ import می‌کنند.
- از pydantic-settings (یا هر کلاس کانفیگ مبتنی بر factory) استفاده می‌شود.

### Does NOT apply when (anti-pattern)
- عمداً می‌خواهی کانفیگ per-request/per-call ساخته شود (آنگاه فقط factory
  را expose کن، نه singleton).
- کانفیگ به متغیرهای runtime که در زمان import موجود نیستند وابسته است.

### Prerequisites
- Python، pydantic-settings v2 (یا هر settings loader).

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — دیباگ کرش دیپلوی یک API روی PaaS.
- مرتبط: `pydantic-settings-list-env-var-json-decode`, `pydantic-secretstr-unwrap-for-plain-use`
