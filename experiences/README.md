# 📚 Experiences Folder — Format Guide

این فولدر تجربیات قابل‌استفاده‌مجدد مهندسی را نگه می‌دارد. هر فایل یک
چالش حل‌شده را به شکل **project-agnostic** (مستقل از پروژهٔ خاص) ثبت
می‌کند تا بتوان آن را در پروژه‌های دیگر دوباره به کار برد.

## 📁 نام‌گذاری فایل‌ها

- یک فایل برای هر تجربه: `{topic-slug}.md` (kebab-case)
- مثال‌های خوب:
  - `google-oauth-login.md`
  - `fastapi-rate-limiting.md`
  - `nextjs-static-export-edge-cases.md`
- مثال بد: `bug-fix-in-myproject.md` (نام پروژه ممنوع)

## 📋 ساختار اجباری هر فایل

هر فایل **باید** با frontmatter YAML شروع شود:

```yaml
---
title: "عنوان کوتاه — همان slug ولی خواناتر"
tags: ["auth", "google-oauth", "frontend"]
topic_canonical: "google-oauth-login"
source:
  type: "manual" | "chat-import" | "claude-code-task"
  origin: "claude-code" | "chatgpt" | "gemini" | "user-typed"
  imported_at: "2026-06-05T10:00:00Z"
created_at: "2026-06-05T10:00:00Z"
updated_at: "2026-06-05T10:00:00Z"
merged_from: []
resolution_status: "solved"   # solved | partial | open | regressed | unknown
recurrence_count: 1            # چند بار همین موضوع در چت بازگشته
user_confirmed: true           # آیا کاربر صریحاً «حل شد» گفت
---
```

سپس بخش‌های markdown به این ترتیب:

```markdown
# Topic Title

## 🎯 چالش / Challenge
[چه مشکلی حل می‌شد — کلی، بدون نام پروژه]

## 💡 راه‌حل / Solution
[راه‌حل قدم‌به‌قدم، قابل تعمیم]

## 🧪 نمونه کد (Anonymized)
[snippet با نام‌های عمومی، نه مال این پروژه]

## ⚠️ نکات حیاتی / Pitfalls
[خطاهای رایج وقتی این الگو را در جای دیگر استفاده می‌کنی، شامل
تلاش‌هایی که در چت اصلی شکست خوردند]

## ✅ Resolution
- Status: solved | partial | open | regressed
- Evidence: نقل‌قول کوتاه از چت که اثبات می‌کند مشکل واقعاً حل شد
  (مثلاً «کاربر گفت ‘حالا کار می‌کنه’» یا «کد فاینال run شد و خطا نداد»)

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
[ترجمهٔ این الگو به پروژه‌های دیگر — generic checklist]

### Applies when
- سناریوهای concrete که این الگو در آن‌ها کاربرد دارد

### Does NOT apply when (anti-pattern)
- سناریوهایی که نباید این الگو را اعمال کرد

### Prerequisites
- پیش‌نیازهای فنی (versions, frameworks, …)

## 🔗 References
- منبع اولیه: [chat-export-2026-06-04.txt, line 42]
- مرتبط: [other-experience-slug]
```

## 🤖 دستورالعمل برای مدل‌های AI (Claude Code, GPT, Gemini, …)

وقتی کاربر از تو می‌خواهد یک تجربه را در این فولدر ثبت کنی:

1. **اول بخوان**: تمام فایل‌های موجود را چک کن. اگر `topic_canonical`
   مشابهی هست، **MERGE نه REPLACE**:
   - محتوای اصلی را نگه دار
   - بخش جدید زیر «## Update YYYY-MM-DD» اضافه کن
   - `merged_from:` در frontmatter آپدیت کن

2. **همیشه عمومی بنویس**:
   - ❌ "در پروژهٔ MyApp ما X کردیم"
   - ✅ "وقتی X را پیاده می‌کنیم..."
   - نام فایل‌های مخصوص پروژه → جایگزین با placeholder عمومی
     (مثلاً `MyApp.tsx` → `AuthPage.tsx`)

3. **بخش "How to Apply Elsewhere" اجباری است** — این مهم‌ترین بخش است
   که تجربه را reusable می‌کند.

4. **slug را canonical نگه دار**: `topic_canonical` در frontmatter باید
   یکپارچه باشد تا dedup در آینده کار کند.

5. **References صادق باشن**: اگر مطلب از یک چت import شد، منبع را در
   `source:` و در پایان فایل ذکر کن.

6. **تشخیص resolution را بر اساس شواهد ثبت کن** — نه حدس:
   - `solved` ⇐ کاربر صریحاً تأیید کرد ("کار کرد"، "ممنون") یا کد
     فاینال ارائه شد و کاربر بدون اعتراض موضوع را عوض کرد
   - `partial` ⇐ راه‌حل ارائه شد ولی کاربر یک sub-question باقی‌مانده داشت
   - `open` ⇐ تلاش شد، شواهد روشنی برای حل وجود ندارد
   - `regressed` ⇐ موضوع بعداً در همین چت دوباره ظاهر شد
   - **اگر مطمئن نیستی → `partial` بزن، نه `solved`.**
   - فقط راه‌حلِ **موفق** را در `solution` بیاور؛ تلاش‌های شکست‌خورده
     را در `pitfalls` ثبت کن تا خوانندهٔ بعدی آن‌ها را تکرار نکند.

7. **رشتهٔ یک موضوع را در میان پیام‌های متفرقه دنبال کن** — چت‌های
   طولانی معمولاً interleaved اند. یک موضوع شروع می‌شود، یک سؤال
   نامرتبط وسطش می‌آید، بعد بازمی‌گردد. این پراکندگی نباید باعث شود
   آن را به دو تجربهٔ مجزا تقسیم کنی.

## 📤 سینک با Knowledge Center

این فولدر به‌صورت خودکار توسط صفحهٔ **مرکز دانش** (/knowledge-center)
خوانده می‌شود. فایل‌هایی که فرمت بالا را رعایت کنند با metadata کامل در
کاتالوگ ظاهر می‌شوند؛ فایل‌های بدفرمت در دسته «unparsed» می‌روند.

---
_این فایل توسط Knowledge Center سرویس به‌صورت خودکار ساخته شده.
ویرایش کن اگر می‌خواهی template را برای پروژهٔ خاص خودت گسترش بدهی._
