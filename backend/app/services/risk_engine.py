"""
backend/app/services/risk_engine.py

موتور ارزیابی ریسک مبتنی بر شواهد دانشنامه (Evidence-based Risk Engine)

این ماژول مسئول طبقه‌بندی هر شخص (Person) بر اساس عملکرد فعلی/قبلی،
مواضع، سوابق و شواهد مرتبط دانشنامه به یکی از دسته‌های ریسک است:
    - CLEAN          (پاک)
    - SUSPICIOUS     (مشکوک)
    - INFILTRATOR    (نفوذی)
    - TRANSFORMED    (استحاله‌یافته)
    - INTELLIGENCE   (اطلاعاتی / مرتبط با سرویس)

خروجی شامل یک امتیاز عددی (0..100)، سطح ریسک، رنگ متناظر برای نمایش در
نمودار ارتباطی، شواهد مؤثر و توضیح قابل‌فهم برای انسان است.

این موتور هم به‌صورت قاعده‌محور (rule-based / deterministic) کار می‌کند
و هم در صورت در دسترس بودن یک LLM adapter می‌تواند تحلیل کیفی شواهد
دانشنامه را برای تنظیم نهایی امتیاز به‌کار گیرد.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional, Protocol, Sequence

logger = logging.getLogger("detective.risk_engine")


# ---------------------------------------------------------------------------
# Enums و ثابت‌ها
# ---------------------------------------------------------------------------


class RiskCategory(str, Enum):
    """دسته‌بندی نهایی ریسک یک شخص."""

    CLEAN = "clean"               # پاک
    SUSPICIOUS = "suspicious"     # مشکوک
    INFILTRATOR = "infiltrator"   # نفوذی
    TRANSFORMED = "transformed"   # استحاله‌یافته (تغییر موضع داده)
    INTELLIGENCE = "intelligence" # اطلاعاتی / مرتبط با سرویس
    UNKNOWN = "unknown"           # نامشخص (داده ناکافی)


class RiskLevel(str, Enum):
    """سطح کلی خطر برای رنگ‌بندی نمودار."""

    NONE = "none"       # 0-20
    LOW = "low"         # 21-40
    MEDIUM = "medium"   # 41-60
    HIGH = "high"       # 61-80
    CRITICAL = "critical" # 81-100


# رنگ هگز متناظر هر سطح ریسک — برای رنگ‌بندی node در React Flow / Cytoscape
RISK_LEVEL_COLORS: dict[RiskLevel, str] = {
    RiskLevel.NONE: "#22c55e",      # سبز (tailwind green-500)
    RiskLevel.LOW: "#84cc16",       # سبز-زرد (tailwind lime-500)
    RiskLevel.MEDIUM: "#eab308",    # زرد (tailwind yellow-500)
    RiskLevel.HIGH: "#f97316",      # نارنجی (tailwind orange-500)
    RiskLevel.CRITICAL: "#ef4444",  # قرمز (tailwind red-500)
}


# ---------------------------------------------------------------------------
# مدل‌های داده‌ای
# ---------------------------------------------------------------------------


@dataclass
class RiskEvidence:
    """یک قطعه شواهد که به ارزیابی ریسک کمک می‌کند."""
    source: str                      # منبع شواهد (مثلاً "سوابق شغلی", "دانشنامه", "مواضع عمومی")
    description: str                 # توضیح شواهد
    impact_score: int                # امتیاز تأثیر این شواهد (مثلاً -10 تا +10)
    weight: float = 1.0              # وزن این شواهد در محاسبه نهایی (0.1 تا 1.0)
    article_id: Optional[str] = None # شناسه مقاله مرتبط در دانشنامه
    person_id: Optional[str] = None  # شناسه شخص مرتبط (در صورت وجود ارتباط با شخص دیگر)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RiskAssessmentResult:
    """نتیجه نهایی ارزیابی ریسک یک شخص."""
    person_id: str
    score: int                       # امتیاز نهایی ریسک (0-100)
    category: RiskCategory           # دسته‌بندی ریسک
    level: RiskLevel                 # سطح ریسک
    color: str                       # رنگ متناظر برای نمایش در UI
    summary: str                     # خلاصه و توضیح قابل فهم برای انسان
    evidence: list[RiskEvidence]     # لیست شواهد مؤثر در ارزیابی
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# پروتکل برای LLM Adapter
# ---------------------------------------------------------------------------


class LLMAdapterProtocol(Protocol):
    """پروتکل برای آداپتور LLM جهت تحلیل ریسک."""
    async def analyze_risk_factors(
        self,
        person_data: dict[str, Any],
        evidence: Sequence[RiskEvidence],
        related_articles: Sequence[dict[str, Any]],
        related_persons: Sequence[dict[str, Any]]
    ) -> tuple[str, Optional[int]]:
        """
        تحلیل عوامل ریسک با استفاده از LLM و ارائه خلاصه و (اختیاراً) امتیاز تعدیل‌شده.
        برمی‌گرداند: (خلاصه متنی، امتیاز تعدیل‌شده LLM یا None)
        """
        ...


# ---------------------------------------------------------------------------
# موتور ارزیابی ریسک
# ---------------------------------------------------------------------------


class RiskEngine:
    """
    موتور اصلی برای ارزیابی ریسک اشخاص بر اساس شواهد مختلف.
    """
    def __init__(self, llm_adapter: Optional[LLMAdapterProtocol] = None):
        self.llm_adapter = llm_adapter
        # قواعد اولیه برای ارزیابی ریسک (می‌تواند از فایل کانفیگ یا DB لود شود)
        # این قواعد ساده هستند و برای پیچیدگی بیشتر، نیاز به سیستم Rule Engine قوی‌تری است.
        self.scoring_rules = {
            "keywords_high_risk": [
                ("جاسوس", -20), ("نفوذی", -20), ("فساد اقتصادی", -15),
                ("ارتباط با سرویس خارجی", -25), ("اتهام خیانت", -30)
            ],
            "keywords_medium_risk": [
                ("مواضع متناقض", -10), ("تغییر ناگهانی سمت", -8),
                ("شبهه", -12), ("اختلاس", -15)
            ],
            "keywords_low_risk": [
                ("انتقاد از سیستم", -5), ("نزدیکی به جریان خاص", -7)
            ],
            "keywords_clean": [
                ("خدمت صادقانه", 10), ("مبارزه با فساد", 15),
                ("شفافیت", 8), ("آدم پاک", 10)
            ],
            "position_impact": {
                "مسئول امنیتی": -10,  # حساسیت بالا، پتانسیل نفوذ بیشتر
                "سیاسی": -5,
                "اقتصادی": -7,
                "فرهنگی": -3
            },
            "transformed_indicators": [
                ("تغییر ایدئولوژی", -10), ("برگشت از مواضع قبلی", -10),
                ("تغییرات ناگهانی در رفتار", -8)
            ]
        }

    def _calculate_base_score(
        self,
        person_data: dict[str, Any],
        related_articles: Sequence[dict[str, Any]],
        related_persons: Sequence[dict[str, Any]]
    ) -> tuple[int, list[RiskEvidence]]:
        """
        محاسبه امتیاز اولیه ریسک بر اساس قواعد ثابت و جمع‌آوری شواهد.
        امتیاز اولیه بین 0 تا 100 است (0 کمترین ریسک، 100 بیشترین ریسک).
        """
        base_score = 50  # شروع از یک امتیاز میانی
        collected_evidence: list[RiskEvidence] = []

        # 1. بررسی سوابق شغلی و جایگاه‌ها
        current_position = person_data.get("current_position", "")
        previous_positions = person_data.get("previous_positions", [])
        all_positions = [current_position] + previous_positions

        for pos in all_positions:
            for keyword, impact in self.scoring_rules["position_impact"].items():
                if keyword in pos:
                    base_score += impact
                    collected_evidence.append(
                        RiskEvidence(
                            source="سوابق شغلی",
                            description=f"جایگاه شغلی '{pos}' مرتبط با '{keyword}'",
                            impact_score=impact
                        )
                    )

        # 2. بررسی عملکرد و مواضع (از فیلدهای 'actions' و 'statements' در person_data)
        actions = person_data.get("actions", [])
        statements = person_data.get("statements", [])
        all_text_data = " ".join(actions + statements)

        for keywords_list, impact_multiplier in [
            (self.scoring_rules["keywords_high_risk"], -1),
            (self.scoring_rules["keywords_medium_risk"], -1),
            (self.scoring_rules["keywords_low_risk"], -1),
            (self.scoring_rules["keywords_clean"], 1)
        ]:
            for keyword, keyword_impact in keywords_list:
                if keyword in all_text_data:
                    adjusted_impact = keyword_impact * impact_multiplier
                    base_score += adjusted_impact
                    collected_evidence.append(
                        RiskEvidence(
                            source="عملکرد و مواضع",
                            description=f"کشف کلمه کلیدی '{keyword}' در عملکرد/مواضع",
                            impact_score=adjusted_impact
                        )
                    )
        
        # 3. بررسی مقالات مرتبط دانشنامه
        for article in related_articles:
            article_content = article.get("content", "") + " " + article.get("summary", "")
            for keywords_list, impact_multiplier in [
                (self.scoring_rules["keywords_high_risk"], -1),
                (self.scoring_rules["keywords_medium_risk"], -1),
                (self.scoring_rules["keywords_low_risk"], -1),
                (self.scoring_rules["keywords_clean"], 1)
            ]:
                for keyword, keyword_impact in keywords_list:
                    if keyword in article_content:
                        adjusted_impact = keyword_impact * impact_multiplier * 0.5 # کمی کمتر از مواضع مستقیم
                        base_score += adjusted_impact
                        collected_evidence.append(
                            RiskEvidence(
                                source="دانشنامه",
                                description=f"کلمه کلیدی '{keyword}' در مقاله '{article.get('title', 'N/A')}'",
                                impact_score=adjusted_impact,
                                article_id=article.get("id")
                            )
                        )
            
            # بررسی برای استحاله
            for keyword, keyword_impact in self.scoring_rules["transformed_indicators"]:
                if keyword in article_content:
                    base_score += keyword_impact
                    collected_evidence.append(
                        RiskEvidence(
                            source="دانشنامه",
                            description=f"نشانه 'استحاله' در مقاله '{article.get('title', 'N/A')}'",
                            impact_score=keyword_impact,
                            article_id=article.get("id")
                        )
                    )

        # 4. بررسی ارتباطات با اشخاص دیگر (مثلاً اگر به یک نفوذی شناخته شده وصل باشد)
        for rp in related_persons:
            # این بخش نیاز به یک مکانیزم برای دریافت ریسک شخص مرتبط دارد
            # فعلاً فرض می‌کنیم یک 'risk_level' در داده‌های rp وجود دارد
            if rp.get("risk_level") == RiskLevel.CRITICAL:
                base_score -= 15
                collected_evidence.append(
                    RiskEvidence(
                        source="ارتباطات",
                        description=f"ارتباط با شخص با ریسک بحرانی: {rp.get('name', 'N/A')}",
                        impact_score=-15,
                        person_id=rp.get("id")
                    )
                )
            elif rp.get("risk_level") == RiskLevel.HIGH:
                base_score -= 10
                collected_evidence.append(
                    RiskEvidence(
                        source="ارتباطات",
                        description=f"ارتباط با شخص با ریسک بالا: {rp.get('name', 'N/A')}",
                        impact_score=-10,
                        person_id=rp.get("id")
                    )
                )
            elif rp.get("risk_level") == RiskLevel.SUSPICIOUS:
                base_score -= 5
                collected_evidence.append(
                    RiskEvidence(
                        source="ارتباطات",
                        description=f"ارتباط با شخص مشکوک: {rp.get('name', 'N/A')}",
                        impact_score=-5,
                        person_id=rp.get("id")
                    )
                )


        # نرمال‌سازی امتیاز به محدوده 0-100
        final_score = max(0, min(100, base_score))

        return final_score, collected_evidence

    def _categorize_risk(self, score: int) -> tuple[RiskCategory, RiskLevel, str]:
        """
        دسته‌بندی ریسک و تعیین سطح و رنگ بر اساس امتیاز نهایی.
        """
        if 0 <= score <= 20:
            category = RiskCategory.CLEAN
            level = RiskLevel.NONE
        elif 21 <= score <= 40:
            category = RiskCategory.SUSPICIOUS
            level = RiskLevel.LOW
        elif 41 <= score <= 60:
            category = RiskCategory.SUSPICIOUS # می‌تواند به INFILTRATOR یا TRANSFORMED تغییر کند
            level = RiskLevel.MEDIUM
        elif 61 <= score <= 80:
            category = RiskCategory.INFILTRATOR # می‌تواند به TRANSFORMED/INTELLIGENCE تغییر کند
            level = RiskLevel.HIGH
        else: # 81 <= score <= 100
            category = RiskCategory.INFILTRATOR
            level = RiskLevel.CRITICAL
        
        color = RISK_LEVEL_COLORS.get(level, RISK_LEVEL_COLORS[RiskLevel.NONE])
        return category, level, color

    async def assess_person_risk(
        self,
        person_id: str,
        person_data: dict[str, Any],
        related_articles: Sequence[dict[str, Any]] = [],
        related_persons: Sequence[dict[str, Any]] = []
    ) -> RiskAssessmentResult:
        """
        انجام ارزیابی کامل ریسک برای یک شخص.
        """
        logger.info(f"شروع ارزیابی ریسک برای شخص {person_id}")

        # 1. محاسبه امتیاز اولیه و جمع‌آوری شواهد قاعده‌محور
        base_score, collected_evidence = self._calculate_base_score(
            person_data, related_articles, related_persons
        )

        final_score = base_score
        summary = "ارزیابی اولیه بر اساس قواعد سیستم."
        
        # 2. تحلیل با LLM (در صورت وجود)
        if self.llm_adapter:
            logger.info(f"استفاده از LLM برای تحلیل عمیق‌تر برای شخص {person_id}")
            try:
                llm_summary, llm_adjusted_score = await self.llm_adapter.analyze_risk_factors(
                    person_data, collected_evidence, related_articles, related_persons
                )
                if llm_summary:
                    summary = llm_summary
                if llm_adjusted_score is not None:
                    final_score = max(0, min(100, llm_adjusted_score))
                    logger.debug(f"LLM امتیاز را به {final_score} تغییر داد.")
            except Exception as e:
                logger.error(f"خطا در تحلیل LLM برای شخص {person_id}: {e}")
                # ادامه با امتیاز قاعده‌محور در صورت خطای LLM

        # 3. دسته‌بندی نهایی
        category, level, color = self._categorize_risk(final_score)

        # 4. تنظیم نهایی category بر اساس شواهد خاص
        # این بخش می‌تواند پیچیده‌تر شود. مثلاً اگر LLM پیشنهاد خاصی برای دسته بدهد.
        # فعلا یک منطق ساده برای TRANSFORMED و INTELLIGENCE
        if any("استحاله" in ev.description for ev in collected_evidence) and final_score > 40:
            category = RiskCategory.TRANSFORMED
        elif any("سرویس خارجی" in ev.description or "اطلاعاتی" in ev.description for ev in collected_evidence) and final_score > 60:
            category = RiskCategory.INTELLIGENCE

        logger.info(f"ارزیابی ریسک برای شخص {person_id} به پایان رسید: امتیاز={final_score}, دسته={category.value}")

        return RiskAssessmentResult(
            person_id=person_id,
            score=final_score,
            category=category,
            level=level,
            color=color,
            summary=summary,
            evidence=collected_evidence,
            timestamp=datetime.now(timezone.utc)
        )