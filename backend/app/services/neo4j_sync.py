import logging
from typing import Optional, List, Dict, Any

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, Neo4jError

from app.core.config import settings
from app.models.person import Person as DBPerson
from app.models.risk_assessment import RiskAssessment as DBRiskAssessment

logger = logging.getLogger(__name__)


class Neo4jSyncService:
    """
    سرویس همگام‌سازی داده‌ها با پایگاه داده گرافی Neo4j.

    این سرویس مسئول ایجاد، به‌روزرسانی و حذف گره‌های اشخاص (Person)
    و روابط میان آن‌ها است و همچنین نمودار ارتباطی رنگ‌بندی‌شده بر اساس
    سطح ریسک هر فرد را تأمین می‌کند.
    """

    def __init__(self) -> None:
        self.uri = settings.NEO4J_URI
        self.user = settings.NEO4J_USER
        self.password = settings.NEO4J_PASSWORD
        self.driver = None
        self._initialize_driver()

    # ------------------------------------------------------------------ #
    # مدیریت اتصال
    # ------------------------------------------------------------------ #
    def _initialize_driver(self) -> None:
        """درایور Neo4j را مقداردهی اولیه می‌کند."""
        try:
            self.driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            self.driver.verify_connectivity()
            logger.info("Neo4j driver initialized and connected successfully.")
        except ServiceUnavailable as e:
            logger.error(f"Failed to connect to Neo4j at {self.uri}: {e}")
            self.driver = None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Unexpected error initializing Neo4j driver: {e}")
            self.driver = None

    def close(self) -> None:
        """اتصال به Neo4j را می‌بندد."""
        if self.driver:
            self.driver.close()
            self.driver = None
            logger.info("Neo4j driver closed.")

    def _ensure_driver(self) -> bool:
        """
        بررسی می‌کند که درایور در دسترس است؛ در صورت قطع بودن، تلاش
        مجدد برای اتصال انجام می‌دهد. در صورت ناموفق بودن False برمی‌گرداند.
        """
        if self.driver is None:
            self._initialize_driver()
        return self.driver is not None

    def is_available(self) -> bool:
        """آیا اتصال به Neo4j برقرار است."""
        return self._ensure_driver()

    # ------------------------------------------------------------------ #
    # کمک‌متدها
    # ------------------------------------------------------------------ #
    @staticmethod
    def _risk_color(risk_category: Optional[str]) -> str:
        """
        نگاشت دستهٔ ریسک به رنگ برای نمایش در نمودار ارتباطی.

        دسته‌ها: clean (پاک)، suspicious (مشکوک)،
        infiltrator (نفوذی)، transformed (استحاله‌یافته).
        """
        mapping = {
            "clean": "#22c55e",          # سبز — پاک
            "suspicious": "#f59e0b",     # نارنجی — مشکوک
            "infiltrator": "#ef4444",    # قرمز — نفوذی
            "transformed": "#a855f7",    # بنفش — استحاله‌یافته
        }
        if not risk_category:
            return "#9ca3af"  # خاکستری — نامشخص
        return mapping.get(risk_category.lower(), "#9ca3af")

    @staticmethod
    def _person_props(person: DBPerson) -> Dict[str, Any]:
        """ویژگی‌های یک گرهٔ Person را برای ذخیره در Neo4j می‌سازد."""
        return {
            "id": str(person.id),
            "full_name": getattr(person, "full_name", None),
            "current_position": getattr(person, "current_position", None),
            "previous_position": getattr(person, "previous_position", None),
            "photo_url": getattr(person, "photo_url", None),
            "summary": getattr(person, "summary", None),
        }

    # ------------------------------------------------------------------ #
    # عملیات روی گره‌ها
    # ------------------------------------------------------------------ #
    def upsert_person(
        self,
        person: DBPerson,
        risk: Optional[DBRiskAssessment] = None,
    ) -> bool:
        """
        یک گرهٔ Person را ایجاد یا به‌روزرسانی می‌کند.
        رنگ گره بر اساس سطح ریسک تنظیم می‌شود.
        """
        if not self._ensure_driver():
            logger.warning("Neo4j unavailable; skipping upsert_person.")
            return False

        props = self._person_props(person)
        risk_category = getattr(risk, "category", None) if risk else None
        risk_score = getattr(risk, "score", None) if risk else None
        props["risk_category"] = risk_category
        props["risk_score"] = risk_score
        props["color"] = self._risk_color(risk_category)

        query = """
        MERGE (p:Person {id: $id})
        SET p.full_name = $full_name,
            p.current_position = $current_position,
            p.previous_position = $previous_position,
            p.photo_url = $photo_url,
            p.summary = $summary,
            p.risk_category = $risk_category,
            p.risk_score = $risk_score,
            p.color = $color
        RETURN p.id AS id
        """
        try:
            with self.driver.session() as session:
                session.run(query, **props).consume()
            logger.info(f"Upserted Person node id={props['id']} in Neo4j.")
            return True
        except Neo4jError as e:
            logger.error(f"Neo4j error during upsert_person: {e}")
            return False

    def delete_person(self, person_id: Any) -> bool:
        """یک گرهٔ Person و تمام روابط مرتبط با آن را حذف می‌کند."""
        if not self._ensure_driver():
            logger.warning("Neo4j unavailable; skipping delete_person.")
            return False

        query = """
        MATCH (p:Person {id: $id})
        DETACH DELETE p
        """
        try:
            with self.driver.session() as session:
                session.run(query, id=str(person_id)).consume()
            logger.info(f"Deleted Person node id={person_id} from Neo4j.")
            return True
        except Neo4jError as e:
            logger.error(f"Neo4j error during delete_person: {e}")
            return False

    def update_risk(
        self,
        person_id: Any,
        risk: DBRiskAssessment,
    ) -> bool:
        """دستهٔ ریسک و رنگ گرهٔ یک شخص را به‌روزرسانی می‌کند."""
        if not self._ensure_driver():
            logger.warning("Neo4j unavailable; skipping update_risk.")
            return False

        risk_category = getattr(risk, "category", None)
        risk_score = getattr(risk, "score", None)
        color = self._risk_color(risk_category)

        query = """
        MATCH (p:Person {id: $id})
        SET p.risk_category = $risk_category,
            p.risk_score = $risk_score,
            p.color = $color
        RETURN p.id AS id
        """
        try:
            with self.driver.session() as session:
                result = session.run(
                    query,
                    id=str(person_id),
                    risk_category=risk_category,
                    risk_score=risk_score,
                    color=color,
                ).single()
            if result is None:
                logger.warning(
                    f"update_risk: Person id={person_id} not found in Neo4j."
                )
                return False
            logger.info(f"Updated risk for Person id={person_id} in Neo4j.")
            return True
        except Neo4jError as e:
            logger.error(f"Neo4j error during update_risk: {e}")
            return False

    # ------------------------------------------------------------------ #
    # عملیات روی روابط
    # ------------------------------------------------------------------ #
    def upsert_relationship(
        self,
        from_person_id: Any,
        to_person_id: Any,
        rel_type: str = "CONNECTED_TO",
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        یک رابطه بین دو شخص را ایجاد یا به‌روزرسانی می‌کند.

        نوع رابطه برای جلوگیری از تزریق در Cypher اعتبارسنجی می‌شود.
        """
        if not self._ensure_driver():
            logger.warning("Neo4j unavailable; skipping upsert_relationship.")
            return False

        safe_rel = self._sanitize_rel_type(rel_type)
        props = properties or {}

        query = f"""
        MATCH (a:Person {{id: $from_id}})
        MATCH (b:Person {{id: $to_id}})
        MERGE (a)-[r:{safe_rel}]->(b)
        SET r += $props
        RETURN type(r) AS rel
        """
        try:
            with self.driver.session() as session:
                result = session.run(
                    query,
                    from_id=str(from_person_id),
                    to_id=str(to_person_id),
                    props=props,
                ).single()
            if result is None:
                logger.warning(
                    "upsert_relationship: one or both Person nodes not found "
                    f"({from_person_id} -> {to_person_id})."
                )
                return False
            logger.info(
                f"Upserted relationship {safe_rel} "
                f"({from_person_id} -> {to_person_id})."
            )
            return True
        except Neo4jError as e:
            logger.error(f"Neo4j error during upsert_relationship: {e}")
            return False

    def delete_relationship(
        self,
        from_person_id: Any,
        to_person_id: Any,
        rel_type: str = "CONNECTED_TO",
    ) -> bool:
        """یک رابطهٔ مشخص بین دو شخص را حذف می‌کند."""
        if not self._ensure_driver():
            logger.warning("Neo4j unavailable; skipping delete_relationship.")
            return False

        safe_rel = self._sanitize_rel_type(rel_type)
        query = f"""
        MATCH (a:Person {{id: $from_id}})-[r:{safe_rel}]->(b:Person {{id: $to_id}})
        DELETE r
        """
        try:
            with self.driver.session() as session:
                session.run(
                    query,
                    from_id=str(from_person_id),
                    to_id=str(to_person_id),
                ).consume()
            logger.info(
                f"Deleted relationship {safe_rel} "
                f"({from_person_id} -> {to_person_id})."
            )
            return True
        except Neo4jError as e:
            logger.error(f"Neo4j error during delete_relationship: {e}")
            return False

    @staticmethod
    def _sanitize_rel_type(rel_type: str) -> str:
        """
        نوع رابطه را برای استفادهٔ امن در Cypher پاکسازی می‌کند.
        تنها حروف، اعداد و زیرخط مجاز است.
        """
        cleaned = "".join(
            ch for ch in (rel_type or "") if ch.isalnum() or ch == "_"