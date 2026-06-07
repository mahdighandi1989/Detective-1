"""
Graph API routes for Detective-1.

Provides the relationship graph (persons + their connections) as a
risk-colored, interactive-ready payload that the frontend (React Flow /
Cytoscape.js) can render directly.

Each node carries a `color` derived from the person's current risk
classification so the client can paint the diagram without re-computing
colors. Edges represent known relationships between persons.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.person import Person

logger = logging.getLogger("detective1.graph")

router = APIRouter(prefix="/graph", tags=["graph"])


# ---------------------------------------------------------------------------
# Risk classification -> color mapping
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    """Risk classification buckets used to color graph nodes."""

    CLEAN = "clean"              # پاک
    SUSPICIOUS = "suspicious"    # مشکوک
    INFILTRATOR = "infiltrator"  # نفوذی
    TRANSFORMED = "transformed"  # استحاله‌یافته
    UNKNOWN = "unknown"          # نامشخص


# Hex colors chosen for clear visual separation on dark/light graph canvases.
RISK_COLOR_MAP: dict[RiskLevel, str] = {
    RiskLevel.CLEAN: "#22c55e",        # green
    RiskLevel.SUSPICIOUS: "#eab308",   # yellow/amber
    RiskLevel.INFILTRATOR: "#ef4444",  # red
    RiskLevel.TRANSFORMED: "#a855f7",  # purple
    RiskLevel.UNKNOWN: "#94a3b8",      # slate/gray
}

DEFAULT_NODE_COLOR = RISK_COLOR_MAP[RiskLevel.UNKNOWN]


def _normalize_risk(value: Any) -> RiskLevel:
    """Coerce an arbitrary stored risk value into a known RiskLevel.

    Accepts RiskLevel, plain strings (case-insensitive), or anything that
    can be stringified. Falls back to UNKNOWN when the value is missing or
    unrecognized so the graph never crashes on dirty data.
    """
    if value is None:
        return RiskLevel.UNKNOWN
    if isinstance(value, RiskLevel):
        return value
    try:
        return RiskLevel(str(value).strip().lower())
    except (ValueError, AttributeError):
        return RiskLevel.UNKNOWN


def _color_for(risk: RiskLevel) -> str:
    return RISK_COLOR_MAP.get(risk, DEFAULT_NODE_COLOR)


# ---------------------------------------------------------------------------
# Response models (kept generic so the frontend graph lib can consume them)
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    """A single person rendered as a graph node."""

    id: str = Field(..., description="Stable node id (person id as string).")
    label: str = Field(..., description="Display name for the node.")
    risk: RiskLevel = Field(
        default=RiskLevel.UNKNOWN,
        description="Current risk classification of the person.",
    )
    color: str = Field(..., description="Hex color derived from `risk`.")
    photo_url: Optional[str] = Field(
        default=None, description="Avatar / photo URL if available."
    )
    current_position: Optional[str] = Field(
        default=None, description="Current role/position of the person."
    )
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional arbitrary metadata for the client.",
    )


class GraphEdge(BaseModel):
    """A relationship between two persons."""

    id: str = Field(..., description="Stable edge id.")
    source: str = Field(..., description="Source node (person) id.")
    target: str = Field(..., description="Target node (person) id.")
    label: Optional[str] = Field(
        default=None, description="Relationship label/type."
    )
    meta: dict[str, Any] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    """Full graph payload consumed by the frontend graph renderer."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    legend: dict[str, str] = Field(
        default_factory=lambda: {
            level.value: RISK_COLOR_MAP[level] for level in RiskLevel
        },
        description="risk-level -> color map so the client can draw a legend.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _person_risk(person: Person) -> RiskLevel:
    """Best-effort extraction of a person's current risk classification.

    Tries a few likely attribute names so this route is resilient to small
    model differences without resorting to import-time fallbacks.
    """
    for attr in ("risk_level", "risk", "current_risk", "risk_classification"):
        if hasattr(person, attr):
            return _normalize_risk(getattr(person, attr))
    return RiskLevel.UNKNOWN


def _person_label(person: Person) -> str:
    for attr in ("full_name", "name", "display_name", "title"):
        value = getattr(person, attr, None)
        if value:
            return str(value)
    return f"Person {getattr(person, 'id', '?')}"


def _person_photo(person: Person) -> Optional[str]:
    for attr in ("photo_url", "avatar_url", "image_url", "photo"):
        value = getattr(person, attr, None)
        if value:
            return str(value)
    return None


def _person_position(person: Person) -> Optional[str]:
    for attr in ("current_position", "current_role", "position", "role"):
        value = getattr(person, attr, None)
        if value:
            return str(value)
    return None


def _person_to_node(person: Person) -> GraphNode:
    risk = _person_risk(person)
    return GraphNode(
        id=str(person.id),
        label=_person_label(person),
        risk=risk,
        color=_color_for(risk),
        photo_url=_person_photo(person),
        current_position=_person_position(person),
    )


def _extract_relationships(person: Person) -> list[tuple[str, str, Optional[str]]]:
    """Return (source_id, target_id, label) tuples for a person's relations.

    Supports a generic `relationships` collection if the model exposes one.
    Each relationship object is expected to expose a target person id and an
    optional type/label. Missing data is skipped gracefully.
    """
    edges: list[tuple[str, str, Optional[str]]] = []
    relationships = getattr(person, "relationships", None)
    if not relationships:
        return edges

    source_id = str(person.id)
    for rel in relationships:
        target_id = None
        for attr in ("target_id", "related_person_id", "person_id", "to_id"):
            value = getattr(rel, attr, None)
            if value is not None:
                target_id = str(value)
                break
        if target_id is None:
            continue
        label = None
        for attr in ("relation_type", "type", "label", "kind"):
            value = getattr(rel, attr, None)
            if value:
                label = str(value)
                break
        edges.append((source_id, target_id, label))
    return edges


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=GraphResponse,
    summary="Get the risk-colored relationship graph of persons.",
)
async def get_graph(
    risk: Optional[RiskLevel] = Query(
        default=None,
        description="Optional filter: only include persons with this risk level.",
    ),
    search: Optional[str] = Query(
        default=None,
        description="Optional name search filter (case-insensitive contains).",
    ),
    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
        description="Maximum number of persons (nodes) to return.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> GraphResponse:
    """Build and return the full person graph for the frontend.

    Nodes are colored by their current risk classification; edges represent
    known relationships between persons. Filters are optional.
    """
    stmt = select(Person)

    # Apply an optional name search if the model exposes searchable columns.
    if search:
        pattern = f"%{search.strip()}%"
        conditions = []
        for col_name in ("full_name", "name", "display_name"):
            col = getattr(Person, col_name, None)
            if col is not None:
                conditions.append(col.ilike(pattern))
        if conditions:
            stmt = stmt.where(or_(*conditions))

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    persons = result.scalars().unique().all()

    nodes: list[GraphNode] = []
    node_ids: set[str] = set()
    edges: list[GraphEdge] = []
    seen_edge_ids: set[str] = set()

    for person in persons:
        node = _person_to_node(person)

        # Apply the risk filter after normalization (handles dirty data).
        if risk is not None and node.risk != risk:
            continue

        nodes.append(node)
        node_ids.add(node.id)

    # Build edges only between nodes that are present in the result set, to
    # avoid dangling references in the rendered graph.
    for person in persons:
        source_id = str(person.id)
        if source_id not in node_ids:
            continue
        for src, tgt, label in _extract_relationships(person):
            if tgt not in node_ids:
                continue
            edge_id = f"{src}->{tgt}"
            if edge_id in seen_edge_ids:
                continue
            seen_edge_ids.add(edge_id)
            edges.append(
                GraphEdge(id=edge_id, source=src, target=tgt, label=label)
            )

    return GraphResponse(nodes=nodes, edges=edges)


@router.get(
    "/{person_id}/neighbors",
    response_model=GraphResponse,
    summary="Get a person and their direct relationship neighborhood.",
)
async def get_person_neighbors(
    person_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> GraphResponse:
    """Return the ego-graph (the person + direct neighbors) for one person."""
    center = await db.get(Person, person_id)
    if center is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found.",
        )

    nodes_by_id: dict[str, GraphNode] = {}
    center_node = _person_to_node(center)
    nodes_by_id[center_node.id] = center_node

    edges: list[GraphEdge] = []
    seen_edge_ids: set[str] = set()

    for src, tgt, label in _extract_relationships(center):
        # Resolve the neighbor on the other end of the relationship.
        neighbor_id = tgt if src == center_node.id else src
        if neighbor_id not in nodes_by_id:
            try:
                neighbor_pk = int(neighbor_id)
            except (TypeError, ValueError):
                neighbor_pk = None
            neighbor = (
                await db.get(Person, neighbor_pk) if neighbor_pk is not None else None
            )
            if neighbor is None:
                # Skip relationships pointing to persons not in the database.
                continue
            node = _person_to_node(neighbor)
            nodes_by_id[node.id] = node

        edge_id = f"{src}->{tgt}"
        if edge_id in seen_edge_ids:
            continue
        seen_edge_ids.add(edge_id)
        edges.append(GraphEdge(id=edge_id, source=src, target=tgt, label=label))

    return GraphResponse(nodes=list(nodes_by_id.values()), edges=edges)