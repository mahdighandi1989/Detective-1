---
title: "Recovering a Codebase Where the Generator Truncated Many Files"
tags: ["ai-generated-code", "debugging", "python", "refactoring", "import-chain", "methodology"]
topic_canonical: "recovering-truncated-ai-generated-code"
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

# Recovering a Codebase Where the Generator Truncated Many Files

## 🎯 چالش / Challenge
یک پروژهٔ تولیدشده توسط AI در دیپلوی می‌افتد و معلوم می‌شود **تقریباً هر
فایل مهم وسط فایل قطع (truncated) شده** — توابع نیمه‌کاره، `__all__` ناتمام،
حتی **متنِ توضیحیِ خود مدل (markdown/prose)** که اشتباهی داخل فایل سورس
نوشته شده. علاوه بر این، نام‌ها بین لایه‌ها (route ↔ schema ↔ model ↔ enum)
با هم نمی‌خوانند. هر فیکس، خطای بعدی را آشکار می‌کند.

## 💡 راه‌حل / Solution
یک فرایند سیستماتیک به‌جای فیکسِ تصادفی:

1. **دامنه را یکجا بسنج، نه تک‌تک.** یک‌بار همهٔ فایل‌های سینتکس‌خراب را
   فهرست کن (compile sweep) تا بدانی با چند فایل طرفی.
2. **یک حلقهٔ تأیید محلی بساز.** یک venv با نسخه‌های **دقیقِ prod** بزن و
   مدام entrypoint را import کن؛ هر بار خطای بعدی را بگیر و رفع کن — بدون
   رفت‌وبرگشت با محیط دیپلوی.
3. **به‌ترتیب وابستگی بازسازی کن:** enums/مدل‌ها → schemas → services →
   routes → entrypoint/tasks.
4. **فقط نیمهٔ گم‌شده را بازساز**، هماهنگ با کدِ موجودِ همان فایل (همان امضاها،
   تایپ‌ها، سبک). برای منطقِ ناشناختهٔ بیرونی (مثل client یک SDK) فراخوانی
   **دفاعی** بنویس.
5. **زبالهٔ embedded را حذف کن:** اگر بعد از کدِ معتبر، markdown/prose آمده،
   فایل را در آخرین خطِ معتبر «ببر».
6. **ناهماهنگی نام‌ها بین لایه‌ها را با alias/superset سازگار کن** (پایین‌تر).

## 🧪 نمونه کد (Anonymized)
```bash
# (1) فهرست همهٔ فایل‌های سینتکس‌خراب — یکجا
for f in $(find app -name "*.py"); do
  python -m py_compile "$f" 2>/dev/null || echo "BROKEN: $f"
done

# پیداکردن متنِ LLM که اشتباهی داخل سورس نوشته شده
grep -rlE '```|I cannot|as an AI|Here.?s the|نمی.?توانم|را اصلاح کردم' app/

# بریدن فایل در آخرین خط معتبر (حذف زبالهٔ انتهایی)
head -n 193 app/schemas/user.py > /tmp/x && mv /tmp/x app/schemas/user.py
```
```bash
# (2) حلقهٔ تأیید محلی با نسخه‌های دقیق prod
python -m venv /tmp/venv && . /tmp/venv/bin/activate
pip install -r requirements.txt
# تکرار کن تا «OK» شود؛ هر بار خطای بعدی را رفع کن:
env DATABASE_URL=... REDIS_URL=... SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") \
  python -c "import app.main; print('OK', type(app.main.app).__name__)"
```
```python
# (6) سازگارکردن ناهماهنگی نام بین لایه‌ها بدون بازنویسی همه‌چیز:
# - alias در مبدأ:
SourceInDB = SourceRead                      # یک route این نام را می‌خواهد
process_article = classify_and_summarize_article   # alias تسک
# - superset کردن enum کانونیکال تا همهٔ ارجاع‌ها resolve شوند:
class UserRole(str, Enum):
    ADMIN="admin"; ANALYST="analyst"; VIEWER="viewer"
    INVESTIGATOR="investigator"; OPERATOR="operator"   # افزوده‌شده چون کد ارجاع می‌داد
# - re-export از یک ماژول دیگر (بدون ساختن چرخهٔ import):
from app.core.enums import ClassificationLevel  # noqa: F401
```

## ⚠️ نکات حیاتی / Pitfalls
- **`py_compile` همه‌چیز را نمی‌گیرد.** یک خطِ بریده مثل `app.include_` (دسترسی
  به attribute) از نظر سینتکس **معتبر** است و compile می‌شود، ولی منطقاً
  ناقص است و entrypoint شیء `app` را نمی‌سازد. پس بعد از compile-sweep
  حتماً **import واقعی** را هم اجرا کن.
- **چرخهٔ import:** هنگام re-export برای سازگاری، مطمئن شو ماژول مبدأ، ماژول
  مقصد را import نمی‌کند. جهت وابستگی را چک کن.
- **`__allow_unmapped__`/Mapped و امثال آن:** بعضی خطاها در زمان import مدل
  (نه سینتکس) ظاهر می‌شوند؛ آن‌ها را با همان حلقهٔ import کشف می‌کنی.
- **با نسخه‌های دقیق prod تست کن.** رفتار (مثلاً وجود `NoDecode`، یا
  ساخت wheel) بین نسخه‌ها فرق دارد؛ تست با نسخهٔ متفاوت، نتیجهٔ گمراه‌کننده می‌دهد.
- **اختیار کن چه چیزی را اختراع نکنی.** برای منطق محصولی که نمی‌دانی، با
  کاربر چک کن یا stub بگذار؛ بازنویسیِ حدسیِ منطقِ کسب‌وکار خطرناک است.
- **route↔model divergenceها را جدا گزارش کن:** بعضی هندلرها به ستون‌هایی
  اشاره می‌کنند که مدل ندارد. این‌ها مانع **بوت** نیستند (بدنهٔ تابع در زمان
  اجرا خطا می‌دهد) ولی باید جدا اصلاح/گزارش شوند.

## ✅ Resolution
- Status: solved
- Evidence: با compile-sweep ۱۴ فایل بریده شناسایی و بازسازی شدند؛ حلقهٔ
  import محلی تا «`app.main` imported OK» پیش رفت؛ سپس روی PaaS هر ۵ سرویس
  (web, worker, redis, db, frontend) به وضعیت Deployed/Available رسیدند و
  کاربر تأیید کرد («حالا اصلا این ۵ تا سرویس برای چیه» = همه سبز).

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- یک خروجی AI/اسکفولد ناقص یا بریده تحویل گرفته‌ای و خطاها زنجیره‌ای‌اند.
- مهاجرت بزرگ که importها لایه‌به‌لایه می‌شکنند.

### Does NOT apply when (anti-pattern)
- فقط یک باگ ساده داری (سراغ این فرایند سنگین نرو).
- منطق گم‌شده، تصمیم محصولی است که باید کاربر بدهد (آنجا بازسازیِ حدسی نکن).

### Prerequisites
- دسترسی به محیطی که بتوانی deps را نصب و entrypoint را import کنی (ترجیحاً venv با نسخه‌های prod).

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — بازسازی کامل بک‌اند یک پروژهٔ تولیدشده با AI.
- مرتبط: `sqlalchemy2-mapped-column-annotations`, `fastapi-fail-soft-optional-integrations`,
  `pydantic-settings-module-level-settings-instance`
