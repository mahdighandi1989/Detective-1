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
