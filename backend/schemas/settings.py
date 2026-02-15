# backend/schemas/settings.py
"""
Pydantic schemas for settings management endpoints.
"""
from __future__ import annotations
from typing import Any, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class SettingResponse(BaseModel):
    """Response model for a setting"""
    key: str
    value: Any  # Can be int, bool, str, dict depending on type
    type: str  # "string", "int", "bool", "json"
    description: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[int] = None
    
    model_config = {"from_attributes": True}


class SettingUpdateRequest(BaseModel):
    """Request to update a setting value"""
    value: Any = Field(..., description="New value for the setting")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"value": 12},
                {"value": True},
                {"value": "best"},
                {"value": {"key": "value"}},
            ]
        }
    }