---
title: "Pydantic Settings — List/CSV Env Var Crashes With JSON Decode Error"
tags: ["pydantic", "pydantic-settings", "cors", "environment-variables", "json", "python"]
topic_canonical: "pydantic-settings-list-env-var-json-decode"
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

# Pydantic Settings — List/CSV Env Var Crashes With JSON Decode Error

## 🎯 چالش / Challenge
یک فیلد لیستی در settings (مثلاً `CORS_ORIGINS: List[str]`) وقتی از env
به‌صورت یک رشتهٔ ساده یا comma-separated ست می‌شود، اپ را موقع بالا آمدن
می‌اندازد:

```
pydantic_settings.sources.SettingsError: error parsing value for field
"CORS_ORIGINS" from source "EnvSettingsSource"
...
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

علت: pydantic-settings برای فیلدهای **«complex»** (مثل `List`/`dict`)
مقدار env را **قبل از validatorها** با `json.loads` decode می‌کند. پس
`https://app.example.com` (یا `a,b`) JSON معتبر نیست و خطا می‌دهد. یک
`field_validator(mode="before")` هم دیر است چون decode در لایهٔ source
اتفاق می‌افتد.

## 💡 راه‌حل / Solution
دو راه، بسته به نسخهٔ pydantic-settings:

- **نسخهٔ ≥ 2.5 (دارای `NoDecode`):** فیلد را `Annotated[List[str], NoDecode]`
  کن تا decode خودکار خاموش شود و یک `field_validator(mode="before")`
  رشته را پارس کند.
- **نسخه‌های قدیمی‌تر (بدون `NoDecode`، مثل 2.3.x):** مقدار را به‌صورت
  **رشتهٔ خام** بخوان و لیست را از طریق یک `@property` برگردان. (این روش روی
  همهٔ نسخه‌ها کار می‌کند.)

## 🧪 نمونه کد (Anonymized)
```python
import json
from typing import List, Optional
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # فیلد را به‌صورت str خام بخوان (str فیلد «complex» نیست → JSON decode نمی‌شود)
    CORS_ORIGINS_RAW: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("CORS_ORIGINS", "CORS_ORIGINS_RAW"),
    )

    @property
    def CORS_ORIGINS(self) -> List[str]:
        raw = self.CORS_ORIGINS_RAW
        if not raw or not raw.strip():
            return ["http://localhost:3000"]
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(o).strip() for o in parsed]
            except json.JSONDecodeError:
                pass
        return [o.strip() for o in raw.split(",") if o.strip()]
```

## ⚠️ نکات حیاتی / Pitfalls
- **`field_validator(mode="before")` به‌تنهایی کافی نیست** — خطا در
  EnvSettingsSource (قبل از validatorها) رخ می‌دهد.
- **قبل از استفاده از `NoDecode` نسخه را چک کن:** در 2.3.x وجود ندارد و
  `from pydantic_settings import NoDecode` خودش `ImportError` می‌دهد و اوضاع
  را بدتر می‌کند. (`pip show pydantic-settings`)
- اگر property را هم‌نام فیلد می‌گذاری، فیلد خام را با نام دیگری (`_RAW`)
  تعریف کن و با `validation_alias` نام env اصلی را به آن نگاشت کن.
- مصرف‌کننده‌ها (مثلاً CORS middleware) باید یک **list** بگیرند؛ اگر فیلد را
  `str` کنی و جایی روی آن iterate شود، روی کاراکترها حلقه می‌زند (باگ).

## ✅ Resolution
- Status: solved
- Evidence: پس از تغییر، اپ با `CORS_ORIGINS=https://app.example.com`
  (تک‌مقدار)، comma-separated و JSON-array بدون خطا بالا آمد؛ محلی هر سه حالت
  به لیست درست پارس شدند و در redeploy خطای SettingsError حذف شد.

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- هر فیلد `List`/`dict`/`set` در pydantic-settings که از env به‌صورت رشتهٔ
  غیر-JSON ست می‌شود (CORS origins، hostها، featureها، …).
- محیط‌های دیپلوی که عادتاً مقادیر را comma-separated یا تک‌URL می‌دهند.

### Does NOT apply when (anti-pattern)
- مقدار env همیشه JSON معتبر است (آنگاه رفتار پیش‌فرض درست کار می‌کند).
- از pydantic ساده (نه pydantic-settings) استفاده می‌کنی و env را خودت پارس می‌کنی.

### Prerequisites
- pydantic-settings v2 (`NoDecode` فقط ≥ 2.5).

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — دیباگ کرش دیپلوی API.
- مرتبط: `pydantic-settings-module-level-settings-instance`
