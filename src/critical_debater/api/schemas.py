"""Pydantic schemas for the debate API (v3 Phase 6)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DebateStartRequest(BaseModel):
    topic: str = Field(min_length=1, description="辩题 / debate topic")
    rounds: int = Field(default=3, ge=1, le=10)
    depth: str = Field(default="standard", pattern="^(quick|standard|deep)$")
    mode: str = Field(default="balanced", pattern="^(balanced|red_team)$")
    language: str = Field(default="bilingual", pattern="^(en|zh|bilingual)$")
    workspace: Optional[str] = Field(default=None, description="existing workspace dir; omitted → new one")


class DebateStatus(BaseModel):
    debate_id: str
    workspace: str
    topic: str
    rounds: int
    current_round: int = 0
    status: str = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None


class DebateStartResponse(BaseModel):
    debate_id: str
    workspace: str
    status: str


class ArtifactResponse(BaseModel):
    debate_id: str
    name: str
    exists: bool
    data: Any = None
