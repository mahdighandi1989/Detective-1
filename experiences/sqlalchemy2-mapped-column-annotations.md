---
title: "SQLAlchemy 2.0 — Legacy `x: Any = Column(...)` Annotations Break Mapping"
tags: ["sqlalchemy", "orm", "python", "migration", "declarative"]
topic_canonical: "sqlalchemy2-mapped-column-annotations"
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

# SQLAlchemy 2.0 — Legacy Annotated `Column` Breaks Mapping

## 🎯 چالش / Challenge
موقع import مدل‌ها (یا اولین mapper configuration) خطایی شبیه زیر می‌آید،
اغلب منتسب به یک ستونِ ارثی مثل `created_at`:

```
sqlalchemy.exc.ArgumentError: Type annotation for "SomeModel.created_at"
can't be correctly interpreted for Annotated Declarative Table form.
ORM annotations should normally make use of the Mapped[] generic type ...
or set "__allow_unmapped__ = True" ...
```

علت: `DeclarativeBase` (یا یک mixin) از سبک قدیمی استفاده می‌کند:
```python
created_at: Any = Column(DateTime, server_default=func.now())
```
SQLAlchemy 2.0 وقتی یک attribute **annotation دارد ولی `Mapped[...]` نیست**
را نمی‌تواند تفسیر کند.

## 💡 راه‌حل / Solution
ستون‌های Base/mixin را به سبک درست 2.0 منتقل کن: `Mapped[...] = mapped_column(...)`.

## 🧪 نمونه کد (Anonymized)
```python
from datetime import datetime
from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    __allow_unmapped__ = True  # تور ایمنی برای annotationهای legacy باقی‌مانده

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
```

## ⚠️ نکات حیاتی / Pitfalls
- **`__allow_unmapped__ = True` همیشه کافی نیست.** اگر annotation دقیقاً
  `Any` (یا یک نوع مبهم) باشد، باز هم در `_produce_column_copies` می‌ترکد.
  راه قطعی، تبدیل به `Mapped[...] + mapped_column(...)` است.
- خطا ممکن است به **اولین مدلی** که مَپ می‌شود نسبت داده شود (مثلاً اولین
  مدلی که هنگام import یک router لود می‌شود)، نه لزوماً جایی که ستون تعریف
  شده. ریشه را در **Base/mixin مشترک** بگرد، نه در آن مدل.
- اگر زیرکلاس‌ها همان ستون (مثل `id`) را با نوع دیگری (مثلاً `UUID`)
  بازتعریف کنند، override مجاز است و مشکلی نیست.
- `Column` (بدون annotation، سبک کاملاً legacy) هم کار می‌کند ولی توصیه‌نشده؛
  یکدست‌سازی به `mapped_column` تمیزتر است.

## ✅ Resolution
- Status: solved
- Evidence: پس از تبدیل ستون‌های Base به `Mapped[...]`، خطای ArgumentError
  در زمان import حذف شد و کل زنجیرهٔ مدل‌ها/روترها import شد (در تست محلی،
  اپ FastAPI با موفقیت ساخته شد و health endpointها پاسخ دادند).

## 🔁 چطور در جای دیگر اعمال کنیم / How to Apply Elsewhere
### Applies when
- ارتقای پروژه به SQLAlchemy 2.x یا کدی که Base/mixin با `x: Type = Column(...)`
  دارد و خطای «Annotated Declarative» می‌دهد.

### Does NOT apply when (anti-pattern)
- هنوز روی SQLAlchemy 1.4 با سبک کلاسیک هستی (آنجا این خطا نیست).
- attribute واقعاً یک متغیر کلاسی غیر-مَپ است → از `ClassVar[...]` استفاده کن، نه Mapped.

### Prerequisites
- SQLAlchemy 2.0+ با `DeclarativeBase`.

## 🔗 References
- منبع اولیه: chat-import (Claude Code) — بوت‌پذیرکردن یک API با مدل‌های ORM.
- مرتبط: `recovering-truncated-ai-generated-code`
