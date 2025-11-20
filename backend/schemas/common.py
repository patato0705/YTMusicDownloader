# backend/schemas/common.py
"""
Common/shared schemas used across multiple modules.
"""
from __future__ import annotations
from typing import Optional, Any, List
from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    ok: bool = True


class ErrorResponse(BaseModel):
    """Error response"""
    detail: str
    ok: bool = False
    error_code: Optional[str] = None


class PaginationParams(BaseModel):
    """Pagination query parameters"""
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper"""
    items: List[Any]
    total: int
    limit: int
    offset: int
    has_more: bool
    
    @classmethod
    def create(cls, items: List[Any], total: int, limit: int, offset: int):
        return cls(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + len(items)) < total
        )