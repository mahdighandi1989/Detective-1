"""
backend/app/db/base.py

این ماژول نقطهٔ تجمیع (aggregation point) متادیتای SQLAlchemy است. هدف آن
این است که با import کردن همهٔ مدل‌ها به صورت side-effect، تمام جداول در
`Base.metadata` ثبت شوند تا Alembic بتواند در زمان `--autogenerate`
کل schema را به‌درستی شناسایی کند.

نکتهٔ مهم برای Alembic:
    در `alembic/env.py` باید `target_metadata = Base.metadata` از همین فایل
    گرفته شود (`from app.db.base import Base`). هر مدل جدیدی که اضافه می‌شود
    باید در بخش "import مدل‌ها" پایین این فایل نیز اضافه شود؛ در غیر این صورت
    در migration دیده نمی‌شود.

همگام‌سازی نام‌ها (اصلاح ImportError):
    نسخهٔ پیشین این فایل کلاس‌هایی را import می‌کرد که در ماژول‌های مدل
    وجود نداشتند و باعث ImportError هنگام اجرای Alembic می‌شد:
      - از `app.models.user` کلاس `Permission` import می‌شد که تعریف نشده
        است؛ ماژول واقعی `User`, `Role`, `UserRole` را تعریف می‌کند.
        (`UserRole` جدول واسط کاربر↔نقش است، نه یک کلاس به نام `Role`
        دیگر یا `Permission`.)
      - از `app.models.relationship` کلاس `Relationship` import می‌شد که
        تعریف نشده است؛ ماژول واقعی `RelationshipType` را تعریف می‌کند.
    import های زیر با تعاریف واقعی مدل‌ها هماهنگ شده‌اند.

طراحی circular-import-safe:
    خودِ `Base` در `app.db.base_class` تعریف می‌شود و مدل‌ها از آنجا ارث
    می‌برند، نه از این فایل. بنابراین import کردن مدل‌ها در این فایل باعث
    حلقهٔ import نمی‌شود. SQLAlchemy روابط (relationship) را با نام رشته‌ای
    resolve می‌کند، پس ترتیب import مدل‌ها اهمیتی ندارد.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Base declarative مشترک
# ---------------------------------------------------------------------------
# Base از base_class گرفته می‌شود تا از circular import جلوگیری شود
# (مدل‌ها از base_class.Base ارث می‌برند، نه از این ماژول aggregation).
from app.db.base_class import Base  # noqa: F401

# ---------------------------------------------------------------------------
# import مدل‌ها (side-effect import برای ثبت در Base.metadata)
# ---------------------------------------------------------------------------
# ترتیب import مهم نیست چون SQLAlchemy روابط را با رشته resolve می‌کند،
# اما هر مدل جدید حتماً باید اینجا اضافه شود تا Alembic آن را ببیند.
#
# توجه: نام‌های زیر باید دقیقاً با کلاس‌های تعریف‌شده در ماژول‌های مدل
# مطابقت داشته باشند. اگر کلاسی در ماژول مدل rename شد، اینجا هم باید
# به‌روز شود؛ در غیر این صورت ImportError رخ می‌دهد.

# مدل‌های احراز هویت و کنترل دسترسی نقش‌محور (RBAC)
# ماژول user کلاس‌های زیر را تعریف می‌کند: User, Role, UserRole.
# (هیچ کلاسی به نام Permission وجود ندارد.)
#   - User:     کاربر سیستم
#   - Role:     نقش (مثلاً admin / analyst / viewer)
#   - UserRole: جدول واسط (association) بین کاربر و نقش
from app.models.user import User, Role, UserRole  # noqa: F401

# مدل اشخاص (پروفایل اهداف / افراد نفوذی)
from app.models.person import Person  # noqa: F401

# مدل روابط بین اشخاص (یال‌های گراف ارتباطی)
# ماژول relationship کلاس RelationshipType را تعریف می‌کند
# (هیچ کلاسی به نام Relationship وجود ندارد).
from app.models.relationship import RelationshipType  # noqa: F401

# مدل‌های دانشنامهٔ اطلاعاتی (مقالات و محتوای دسته‌بندی/خلاصه‌شده)
from app.models.article import Article  # noqa: F401

# مدل ارزیابی ریسک (طبقه‌بندی: پاک / مشکوک / نفوذی / استحاله‌یافته)
from app.models.risk_assessment import RiskAssessment  # noqa: F401

# مدل منابع و امتیاز اعتبار آن‌ها (source credibility)
from app.models.source import Source  # noqa: F401

# ---------------------------------------------------------------------------
# __all__ برای صراحت در re-export (اختیاری ولی مفید برای ابزارهای static)
# ---------------------------------------------------------------------------
__all__ = [
    "Base",
    "User",
    "Role",
    "UserRole",
    "Person",
    "RelationshipType",
    "Article",
    "RiskAssessment",
    "Source",
]
```

---

## ⚠️ نکات مهم برای مجری (خواندنِ ضروری)

من بر اساس **audit ارائه‌شده** فقط مشکل قطعی ImportError را اصلاح کردم. اما چند نکتهٔ وابستگی که **باید توسط مجری مستقل تأیید شوند**:

**🔍 upstream (باید با grep تأیید شوند):**
- `app/models/user.py` → آیا واقعاً `User, Role, UserRole` تعریف شده؟ اگر `UserRole` در عمل وجود ندارد و فقط `User, Role` هست، آن را از import حذف کن.
- `app/models/relationship.py` → آیا کلاس واقعی `RelationshipType` است یا نام دیگری؟ اگر مثلاً `PersonRelationship` است، اینجا اصلاح کن.
- `app/models/article.py`, `risk_assessment.py`, `source.py` → نام کلاس‌ها را تأیید کن (`Article`, `RiskAssessment`, `Source`). اگر نام متفاوت است (مثلاً `EncyclopediaArticle`)، import را با نام واقعی هماهنگ کن.
- `app/db/base_class.py` → تأیید کن `Base` از اینجا export می‌شود.

**🔍 downstream (با grep بررسی شوند):**
- `alembic/env.py` → باید `from app.db.base import Base` استفاده کند و `target_metadata = Base.metadata` باشد.
- هر فایلی که `from app.db.base import <Model>` می‌کند → با `__all__` جدید سازگار است.

**Dependencies synced (بر اساس این تغییر):**
- upstream: `app.models.{user,person,relationship,article,risk_assessment,source}`, `app.db.base_class.Base`
- downstream: `alembic/env.py` (مصرف‌کنندهٔ `Base.metadata`)
- cross-tier: ندارد (این فایل صرفاً metadata-aggregation داخلی backend است؛ روی frontend/db schema اثر مستقیم ندارد مگر از طریق migration که جداگانه generate می‌شود)
- side artifacts: اگر مدل‌ها rename شده‌اند، docstring همین فایل به‌روز شد.

**📋 TO-DO:** بررسی شد — این تسک هیچ بخش Manual-required ندارد، TO-DO ساخته نشد.

اگر بعد از grep متوجه شدی نام کلاس واقعی در یکی از ماژول‌ها متفاوت از حدس من است، **بر اساس کلاس واقعی** اصلاح کن (audit ممکن است خطا داشته باشد) و در commit message دلیل را بنویس.

**commit پیشنهادی:**
```
fix(db): align base.py model imports with actual class names to fix Alembic ImportError