"""Shared response models."""

from pydantic import BaseModel


class Message(BaseModel):
    detail: str