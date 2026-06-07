from datetime import datetime, date
from enum import Enum
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, HttpUrl


class RiskCategory(str, Enum):
    """Risk classification aligned with models/person.py."""
    CLEAN = "clean"
    SUSPECT = "suspect"
    INFILTRATOR = "infiltrator"
    TRANSFORMED = "transformed"
    UNKNOWN = "unknown"


class ConfidentialityLevel(str, Enum):
    PUBLIC = "public"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"


class PersonPosition(BaseModel):
    """A position/role held by a person (current or previous)."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    title: str = Field(..., min_length=1, max_length=512)
    organization: Optional[str] = Field(None, max_length=512)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool = False
    description: Optional[str] = None


class PersonPositionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    organization: Optional[str] = Field(None, max_length=512)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool = False
    description: Optional[str] = None


class PersonBase(BaseModel):
    """Shared person fields."""
    full_name: str = Field(..., min_length=1, max_length=512)
    aliases: List[str] = Field(default_factory=list)
    national_id: Optional[str] = Field(None, max_length=64)
    date_of_birth: Optional[date] = None
    nationality: Optional[str] = Field(None, max_length=128)
    photo_url: Optional[str] = Field(None, max_length=2048)
    biography: Optional[str] = None
    notes: Optional[str] = None
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.RESTRICTED


class PersonCreate(PersonBase):
    """Payload for creating a new person profile."""
    positions: List[PersonPositionCreate] = Field(default_factory=list)


class PersonUpdate(BaseModel):
    """Partial update payload — all fields optional."""
    full_name: Optional[str] = Field(None, min_length=1, max_length=512)
    aliases: Optional[List[str]] = None
    national_id: Optional[str] = Field(None, max_length=64)
    date_of_birth: Optional[date] = None
    nationality: Optional[str] = Field(None, max_length=128)
    photo_url: Optional[str] = Field(None, max_length=2048)
    biography: Optional[str] = None
    notes: Optional[str] = None
    confidentiality: Optional[ConfidentialityLevel] = None
    risk_category: Optional[RiskCategory] = None
    risk_score: Optional[float] = Field(None, ge=0.0, le=100.0)


class PersonInDB(PersonBase):
    """Full person representation as stored / returned from DB."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    risk_category: RiskCategory = RiskCategory.UNKNOWN
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    positions: List[PersonPosition] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None


class PersonRead(PersonInDB):
    """Alias returned to API clients."""
    pass


class PersonSummary(BaseModel):
    """Lightweight representation for lists and graph nodes."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    photo_url: Optional[str] = None
    risk_category: RiskCategory = RiskCategory.UNKNOWN
    risk_score: float = 0.0
    current_position: Optional[str] = None
    nationality: Optional[str] = None


class PersonList(BaseModel):
    """Paginated list response."""
    total: int
    items: List[PersonSummary] = Field(default_factory=list)
    page: int = 1
    page_size: int = 50