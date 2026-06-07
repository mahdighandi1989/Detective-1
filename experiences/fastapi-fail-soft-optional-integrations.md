---
title: "Boot the App Without Optional External Services (Fail-Soft Integrations)"
tags: ["fastapi", "configuration", "twelve-factor", "celery", "startup", "python", "resilience"]
topic_canonical: "fastapi-fail-soft-optional-integrations"
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

# Boot the App Without Optional External Services (Fail-Soft Integrations)

## 🎯 چالش / Challenge
یک سرویس به چند بک‌اند خارجی وابسته است (graph DB، object storage، vector
DB، LLM)، ولی محیط دیپلوی فعلی فقط بعضی‌شان را دارد (مثلاً فقط Postgres +
Redis). چون این فیلدها در کانفیگ **required** هستند یا validatorها سخت‌گیرند،
کل اپ موقع بوت با `ValidationError: field required` می‌افتد — حتی برای
endpointهای ساده‌ای مثل `/health` که اصلاً به آن سرویس‌ها نیاز ندارند.

## 💡 راه‌حل / Solution
وابستگی‌های **اختیاری** را در زمان بوت غیرفاتال کن؛ فقط زمان استفادهٔ واقعی
خطا بده:

1. فیلدهای مربوط به سرویس‌های اختیاری را `Optional[...] = None` کن (نه required).
2. validatorهای سخت (مثل «اگر provider=X پس کلید لازم است») را به **هشدار**
   تبدیل کن، نه `raise`.
3. اتصال‌ها را **lazy** کن و در lifespan فقط وقتی hook واقعاً موجود است صدا بزن.
4. هستهٔ واقعاً لازم (DB URL، secret، broker) را همچنان **required** نگه دار.

## 🧪 نمونه کد (Anonymized)
```python
# 1) اختیاری‌کردن سرویس‌های غایب
class Settings(BaseSettings):
    DATABASE_URL: PostgresDsn                 # هسته → required
    SECRET_KEY: SecretStr                     # هسته → required
    GRAPHDB_URI: Optional[str] = None         # اختیاری
    OBJECT_STORAGE_KEY: Optional[SecretStr] = None
    VECTOR_DB_URL: Optional[AnyHttpUrl] = None
    LLM_API_KEY: Optional[SecretStr] = None

    # 2) به‌جای کرش، هشدار بده
    @model_validator(mode="after")
    def warn_llm(self) -> "Settings":
        if self.LLM_PROVIDER == "openai" and not self.LLM_API_KEY:
            logger.warning("LLM_API_KEY not set; LLM features disabled until configured.")
        return self

# 3) lifespan: فقط اگر hook موجود است وصل شو
async def lifespan(app):
    if connect_db := _resolve_hook("app.db.session", "connect_database"):
        await connect_db()
    # graph/vector/storage در نبودِ ماژول/کانفیگ به‌صورت no-op می‌مانند
    yield
```

همچنین کلاینت‌ها را فقط هنگام نیاز بساز (نه در سطح ماژول):
```python
class GraphSync:
    def __init__(self):
        self.uri = settings.GRAPHDB_URI
        self.driver = None
        if self.uri and settings.GRAPHDB_USER and settings.GRAPHDB_PASSWORD:
            self._connect()       # فقط اگر کامل پیکربندی شده
        else:
            logger.info("Graph DB not configured; sync disabled.")
```

## ⚠️ نکات حیاتی / Pitfalls
- **ترتیب خطاها گول‌زننده است:** `model_validator(mode="after")` فقط بعد از
  موفقیت validation فیلدها اجرا می‌شود. وقتی فیلدهای required را اختیاری
  می‌کنی، ناگهان خطای validatorِ بعدی (مثل کلید LLM) **تازه ظاهر می‌شود** —
  انگار مشکل جدید است، در حالی‌که از قبل پنهان بود.
- **کلاینت را در سطح ماژول نساز** (`client = Client(settings.X)` در top-level):
  اگر `settings.X` None باشد یا سرویس قطع باشد، importِ ماژول می‌افتد. آن را
  داخل تابع/متد (lazy) ببر.
- مرز بین «هسته» و «اختیاری» را آگاهانه بکش: DB/secret/broker باید
  required بمانند تا خطاهای واقعی صامت نشوند.
- این تغییر «رفتار» است؛ مستندش کن که فلان قابلیت بدون فلان سرویس کار نمی‌کند.

## ✅ Resolution
- Status: solved
- Evidence: پس از اختیاری‌کردن سرویس‌های غایب و نرم‌کردن validatorها، API و
  worker با حداقل env (DB/Redis/secret) محلی و سپس روی PaaS بالا آمدند؛
  `/health` و `/ready` پاسخ `200` دادند و کاربر تأیید کرد سرویس‌ها سبز شدند.

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- اپ چند integration دارد ولی باید در محیط‌های ناقص (dev/staging/MVP) بالا بیاید.
- می‌خواهی `/health` بدون وابستگی به همهٔ بک‌اندها کار کند (مهم برای health-check دیپلوی).

### Does NOT apply when (anti-pattern)
- آن سرویس واقعاً برای هر درخواست حیاتی است (مثلاً خود دیتابیس اصلی) — آن را
  required و fail-fast نگه دار.
- صامت‌کردن خطا باعث می‌شود یک misconfiguration واقعی پنهان شود.

### Prerequisites
- pydantic-settings v2؛ یک entrypoint که اتصال‌ها را lifecycle-managed یا lazy می‌کند.

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — رساندن یک API چندوابستگی به حالت بوت‌پذیر.
- مرتبط: `pydantic-secretstr-unwrap-for-plain-use`, `recovering-truncated-ai-generated-code`
