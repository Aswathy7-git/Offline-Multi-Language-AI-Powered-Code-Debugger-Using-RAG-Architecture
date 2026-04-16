from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field # type: ignore

from .config import MAX_SNIPPET_CHARS # type: ignore


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(StrictModel):
    username: str = Field(min_length=3, max_length=64, pattern="^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class DebugRequest(StrictModel):
    file_path: str = Field(min_length=1, max_length=4096)
    mode: str = Field(default="full", pattern="^(full|fast)$")
    language: Optional[str] = Field(default=None, pattern="(?i)^(python|c|java)$")


class SnippetRequest(StrictModel):
    code: str = Field(min_length=1, max_length=MAX_SNIPPET_CHARS)
    mode: str = Field(default="full", pattern="^(full|fast)$")
    language: Optional[str] = Field(default=None, pattern="(?i)^(python|c|java)$")


class DiffRequest(StrictModel):
    original: str
    fixed: str


class ComplexityRequest(StrictModel):
    code: str = Field(min_length=1, max_length=MAX_SNIPPET_CHARS)


class ApplyFixRequest(StrictModel):
    file_path: str = Field(min_length=1, max_length=4096)
    fixed_code: str = Field(min_length=1, max_length=MAX_SNIPPET_CHARS)


class ValidateFixRequest(StrictModel):
    original: str = Field(min_length=1, max_length=MAX_SNIPPET_CHARS)
    fixed: str = Field(min_length=1, max_length=MAX_SNIPPET_CHARS)
    include_security: bool = True


class BatchDebugRequest(StrictModel):
    file_paths: list[str] = Field(min_length=1, max_length=25)
    mode: str = Field(default="full", pattern="^(full|fast)$")
    max_concurrency: int = Field(default=3, ge=1, le=8)


class DebugResponse(BaseModel):
    error: Optional[str] = None
    error_type: Optional[str] = None
    line_number: Optional[int] = None
    status: Optional[str] = None
    patch_required: Optional[str] = None
    analysis: Optional[str] = None
    explanation: Optional[str] = None
    bug_type: Optional[str] = None
    cause: Optional[str] = None
    suggested_fix: Optional[str] = None
    verification: Optional[str] = None
    fixed_code: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[int] = None
    complexity: Optional[dict[str, Any]] = None
    security_audit: Optional[dict[str, Any]] = None
    topology: Optional[dict[str, Any]] = None
    metrics: Optional[dict[str, float]] = None
    total_time: Optional[float] = None
    source_path: Optional[str] = None
    source_code: Optional[str] = None
    pipeline_mode: Optional[str] = None
    success: bool
    is_bug: bool
    language: Optional[str] = None
