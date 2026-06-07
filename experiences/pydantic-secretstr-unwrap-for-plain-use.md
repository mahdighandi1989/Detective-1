---
title: "Pydantic SecretStr — Unwrap Before Using as a Plain String (JWT keys, drivers)"
tags: ["pydantic", "secretstr", "jwt", "security", "python"]
topic_canonical: "pydantic-secretstr-unwrap-for-plain-use"
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

# Pydantic SecretStr — Unwrap Before Using as a Plain String

## 🎯 چالش / Challenge
یک مقدار حساس در settings به‌صورت `SecretStr` تعریف شده (خوب، برای جلوگیری
از لاگ‌شدن)، ولی کدی که آن را مصرف می‌کند فرض می‌کند `str` است. دو شکست
رایج:

1. اعتبارسنجی اشتباه می‌گوید مقدار «ست نشده» در حالی‌که ست شده:
   ```python
   if not isinstance(secret, str):   # SecretStr زیرکلاس str نیست → همیشه True
       raise RuntimeError("SECRET_KEY is not set")
   ```
2. کتابخانه‌ای که رشته می‌خواهد (مثل `jose.jwt.encode`/`decode`، درایور DB،
   client) با `SecretStr` می‌ترکد یا توکن خراب می‌سازد.

## 💡 راه‌حل / Solution
هرجا مقدار **خام** لازم است، با `.get_secret_value()` آن را باز کن:

## 🧪 نمونه کد (Anonymized)
```python
from pydantic import SecretStr

def _raw(value) -> str:
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)

# اعتبارسنجی درست:
secret = getattr(settings, "SECRET_KEY", None)
if secret is not None and hasattr(secret, "get_secret_value"):
    secret = secret.get_secret_value()
if not secret or not isinstance(secret, str):
    raise RuntimeError("SECRET_KEY not configured")

# استفاده به‌عنوان کلید امضا:
import jwt  # یا jose
token = jwt.encode(payload, _raw(settings.SECRET_KEY), algorithm="HS256")
```

## ⚠️ نکات حیاتی / Pitfalls
- `isinstance(SecretStr("x"), str)` برابر **False** است — چک‌های مبتنی بر
  `isinstance(..., str)` روی `SecretStr` همیشه رد می‌شوند.
- `str(SecretStr("x"))` می‌دهد `'**********'` (ماسک)، نه مقدار واقعی! فقط
  `.get_secret_value()` مقدار واقعی را می‌دهد. (به همین خاطر از `_raw`
  استفاده کن، نه `str()`.)
- این الگو برای همهٔ کلیدها/رمزها صادق است: `JWT secret`, `DB password`,
  `API key`, `MinIO/S3 keys`, `Neo4j password`.
- اگر روی پروژه‌ای جداگانه طول کلید را هم چک می‌کنی (مثلاً ≥ 32 برای HS256)،
  **اول unwrap کن، بعد length را بسنج** — وگرنه طولِ شیء SecretStr را
  می‌سنجی.

## ✅ Resolution
- Status: solved
- Evidence: پس از unwrap، خطای زمان‌import «SECRET_KEY تنظیم نشده است» حذف
  شد و سرویس بالا آمد؛ تولید/اعتبارسنجی JWT با کلید رشته‌ای درست کار کرد.

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- فیلدهای حساس settings از نوع `SecretStr`/`SecretBytes` هستند ولی توسط
  کتابخانه‌هایی که `str` می‌خواهند مصرف می‌شوند.

### Does NOT apply when (anti-pattern)
- مقدار را فقط لاگ/نمایش می‌دهی (آنجا اتفاقاً نباید unwrap کنی تا نشت نکند).
- فیلد از ابتدا `str` ساده است (نیازی به unwrap نیست).

### Prerequisites
- pydantic v2، و یک مصرف‌کنندهٔ رشته‌محور (jose/pyjwt، sqlalchemy URL، client SDK).

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — دیباگ بوت API و امنیت JWT.
- مرتبط: `pydantic-settings-module-level-settings-instance`
