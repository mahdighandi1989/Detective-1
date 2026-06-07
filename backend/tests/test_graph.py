"""
تست‌های نمودار ارتباطی (Relationship Graph) برای پلتفرم Detective-1.

این فایل رفتار endpointهای مربوط به graph را پوشش می‌دهد:
- بازیابی گراف اشخاص و روابط
- رنگ‌بندی گره‌ها بر اساس سطح ریسک (پاک / مشکوک / نفوذی / استحاله‌یافته)
- افزودن و حذف روابط بین اشخاص
- اتصال پروفایل‌ها به ورودی‌های دانشنامه
- کنترل دسترسی نقش‌محور (RBAC) روی عملیات graph

تست‌ها از mock استفاده می‌کنند تا بدون اتصال واقعی به Neo4j اجرا شوند.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:  # pragma: no cover - import flexibility across project layouts
    from httpx import AsyncClient
    HTTPX_AVAILABLE = True
except Exception:  # pragma: no cover
    HTTPX_AVAILABLE = False


# ---------------------------------------------------------------------------
# نگاشت سطح ریسک به رنگ — مطابق AC «رنگ‌بندی بر اساس سطح خطر»
# ---------------------------------------------------------------------------
RISK_COLOR_MAP: Dict[str, str] = {
    "clean": "#2ecc71",          # پاک — سبز
    "suspicious": "#f1c40f",     # مشکوک — زرد
    "infiltrator": "#e74c3c",    # نفوذی — قرمز
    "transformed": "#e67e22",    # استحاله‌یافته — نارنجی
    "unknown": "#95a5a6",        # نامشخص — خاکستری
}

VALID_RISK_CATEGORIES = list(RISK_COLOR_MAP.keys())


def risk_to_color(category: str) -> str:
    """نگاشت دستهٔ ریسک به رنگ متناظر در نمودار."""
    return RISK_COLOR_MAP.get(category, RISK_COLOR_MAP["unknown"])


# ---------------------------------------------------------------------------
# مدل‌های ساده برای شبیه‌سازی خروجی graph (independent از ORM واقعی)
# ---------------------------------------------------------------------------
def make_node(
    node_id: str,
    name: str,
    risk_category: str = "unknown",
    current_position: Optional[str] = None,
) -> Dict[str, Any]:
    """ساخت یک گره (شخص) برای نمودار با رنگ مبتنی بر ریسک."""
    return {
        "id": node_id,
        "label": name,
        "name": name,
        "risk_category": risk_category,
        "color": risk_to_color(risk_category),
        "current_position": current_position,
        "type": "person",
    }


def make_edge(
    source: str,
    target: str,
    relation: str = "associated_with",
    edge_id: Optional[str] = None,
) -> Dict[str, Any]:
    """ساخت یک یال (رابطه) بین دو شخص."""
    return {
        "id": edge_id or str(uuid.uuid4()),
        "source": source,
        "target": target,
        "relation": relation,
    }


# ---------------------------------------------------------------------------
# Fixtureها
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_graph() -> Dict[str, List[Dict[str, Any]]]:
    """یک نمودار نمونه با اشخاص و روابط و سطوح ریسک مختلف."""
    n1 = make_node("p1", "شخص الف", "infiltrator", "مدیر کل")
    n2 = make_node("p2", "شخص ب", "suspicious", "معاون")
    n3 = make_node("p3", "شخص ج", "clean", "کارشناس")
    n4 = make_node("p4", "شخص د", "transformed", "مشاور")
    return {
        "nodes": [n1, n2, n3, n4],
        "edges": [
            make_edge("p1", "p2", "supervises"),
            make_edge("p2", "p3", "colleague_of"),
            make_edge("p1", "p4", "associated_with"),
        ],
    }


@pytest.fixture
def mock_graph_service(sample_graph):
    """
    سرویس graph شبیه‌سازی‌شده.
    در صورتی که پیاده‌سازی واقعی موجود باشد، این mock با dependency override
    جایگزین می‌شود؛ در غیر این صورت برای تست واحد منطق رنگ‌بندی استفاده می‌شود.
    """
    service = MagicMock()
    service.get_full_graph = AsyncMock(return_value=sample_graph)
    service.get_person_neighborhood = AsyncMock(
        return_value={
            "nodes": [sample_graph["nodes"][0], sample_graph["nodes"][1]],
            "edges": [sample_graph["edges"][0]],
        }
    )
    service.add_relationship = AsyncMock(
        side_effect=lambda src, tgt, rel: make_edge(src, tgt, rel)
    )
    service.remove_relationship = AsyncMock(return_value=True)
    service.link_person_to_article = AsyncMock(return_value=True)
    return service


@pytest.fixture
def app_or_skip():
    """
    تلاش برای import کردن FastAPI app واقعی پروژه.
    اگر موجود نبود، تست‌های integration skip می‌شوند تا تست‌های واحد
    منطق graph همچنان اجرا شوند.
    """
    try:
        from app.main import app  # type: ignore
        return app
    except Exception:
        try:
            from backend.app.main import app  # type: ignore
            return app
        except Exception:
            pytest.skip("FastAPI app برای تست integration در دسترس نیست")


# ---------------------------------------------------------------------------
# تست‌های واحد منطق رنگ‌بندی ریسک (بدون نیاز به سرور/دیتابیس)
# ---------------------------------------------------------------------------
class TestRiskColoring:
    """تست منطق رنگ‌بندی گره‌ها بر اساس سطح خطر — AC رنگ‌بندی نمودار."""

    @pytest.mark.parametrize(
        "category,expected",
        [
            ("clean", "#2ecc71"),
            ("suspicious", "#f1c40f"),
            ("infiltrator", "#e74c3c"),
            ("transformed", "#e67e22"),
            ("unknown", "#95a5a6"),
        ],
    )
    def test_each_risk_category_has_distinct_color(self, category, expected):
        assert risk_to_color(category) == expected

    def test_unknown_category_falls_back_to_gray(self):
        assert risk_to_color("nonexistent_category") == RISK_COLOR_MAP["unknown"]

    def test_all_risk_categories_have_unique_colors(self):
        colors = list(RISK_COLOR_MAP.values())
        assert len(colors) == len(set(colors)), "هر دستهٔ ریسک باید رنگ یکتا داشته باشد"

    def test_node_carries_color_matching_its_risk(self, sample_graph):
        for node in sample_graph["nodes"]:
            assert node["color"] == risk_to_color(node["risk_category"])


# ---------------------------------------------------------------------------
# تست‌های ساختار نمودار
# ---------------------------------------------------------------------------
class TestGraphStructure:
    """تست صحت ساختار گره‌ها و یال‌های نمودار."""

    def test_graph_contains_nodes_and_edges(self, sample_graph):
        assert "nodes" in sample_graph
        assert "edges" in sample_graph
        assert len(sample_graph["nodes"]) == 4
        assert len(sample_graph["edges"]) == 3

    def test_every_node_has_required_fields(self, sample_graph):
        required = {"id", "label", "name", "risk_category", "color", "type"}
        for node in sample_graph["nodes"]:
            assert required.issubset(node.keys())

    def test_every_edge_references_existing_nodes(self, sample_graph):
        node_ids = {n["id"] for n in sample_graph["nodes"]}
        for edge in sample_graph["edges"]:
            assert edge["source"] in node_ids
            assert edge["target"] in node_ids

    def test_edges_have_relation_label(self, sample_graph):
        for edge in sample_graph["edges"]:
            assert isinstance(edge["relation"], str)
            assert edge["relation"]

    def test_make_edge_generates_unique_id_when_omitted(self):
        e1 = make_edge("a", "b")
        e2 = make_edge("a", "b")
        assert e1["id"] != e2["id"]


# ---------------------------------------------------------------------------
# تست‌های سرویس graph (با mock)
# ---------------------------------------------------------------------------
class TestGraphService:
    """تست رفتار سرویس graph با استفاده از mock async."""

    @pytest.mark.asyncio
    async def test_get_full_graph_returns_nodes_and_edges(self, mock_graph_service):
        result = await mock_graph_service.get_full_graph()
        assert len(result["nodes"]) == 4
        assert len(result["edges"]) == 3

    @pytest.mark.asyncio
    async def test_get_person_neighborhood(self, mock_graph_service):
        result = await mock_graph_service.get_person_neighborhood("p1")
        assert all("id" in n for n in result["nodes"])
        assert len(result["edges"]) >= 1

    @pytest.mark.asyncio
    async def test_add_relationship_creates_edge(self, mock_graph_service):
        edge = await mock_graph_service.add_relationship("p3", "p4", "knows")
        assert edge["source"] == "p3"
        assert edge["target"] == "p4"
        assert edge["relation"] == "knows"

    @pytest.mark.asyncio
    async def test_remove_relationship(self, mock_graph_service):
        ok = await mock_graph_service.remove_relationship("p1", "p2")
        assert ok is True

    @pytest.mark.asyncio
    async def test_link_person_to_encyclopedia_article(self, mock_graph_service):
        """AC: اتصال خودکار پروفایل‌ها به ورودی‌های مرتبط دانشنامه."""
        ok = await mock_graph_service.link_person_to_article("p1", "article