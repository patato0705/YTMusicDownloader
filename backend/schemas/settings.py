# backend/schemas/settings.py
"""
Pydantic schemas for settings management endpoints.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class SettingResponse(BaseModel):
    """Response model for a setting"""
    key: str
    value: Any  # Can be int, bool, str, dict depending on type
    type: str  # "string", "int", "bool", "json"
    description: Optional[str] = None
    allowed_values: Optional[List[Dict[str, str]]] = None
    min: Optional[int] = None  # lower bound for int settings
    max: Optional[int] = None  # upper bound for int settings
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

class YoutubeCookiesStatus(BaseModel):
    """State of the admin-uploaded YouTube account cookie jar"""
    present: bool
    cookie_count: int = 0
    size_bytes: int = 0
    modified_at: Optional[datetime] = None


class YoutubeCookiesUpload(BaseModel):
    """A Netscape-format cookies.txt, as exported by a browser extension"""
    content: str = Field(..., min_length=1, max_length=512 * 1024)
