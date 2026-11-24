# backend/schemas/common.py
"""Schemas shared by several routers."""
from __future__ import annotations
from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    ok: bool = True
