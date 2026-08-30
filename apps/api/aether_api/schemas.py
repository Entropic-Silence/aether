from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["user", "moderator", "admin", "owner"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORMModel):
    id: str
    email: str
    name: str
    role: str
    created_at: datetime


class ProviderIn(BaseModel):
    kind: str = "openai_compatible"
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1)
    api_key: str = ""
    headers: dict[str, str] = {}
    proxy: str = ""
    timeout_ms: int = 120000
    retry: dict[str, Any] = {"max": 2, "backoff_ms": 500}
    concurrency: int = 8
    organization: str = ""
    project: str = ""
    enabled: bool = True


class ProviderOut(ORMModel):
    id: str
    kind: str
    name: str
    base_url: str
    proxy: str
    timeout_ms: int
    retry: dict
    concurrency: int
    organization: str
    project: str
    enabled: bool
    has_api_key: bool = False
    created_at: datetime


class ModelIn(BaseModel):
    provider_id: str
    model_id: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    icon: str = ""
    model_family: str = ""
    model_type: str = "chat"
    category: str = "general"
    context_window: int = 4096
    max_output_tokens: int = 2048
    enabled: bool = True
    is_default: bool = False
    priority: int = 100
    weight: float = 1.0
    generation_defaults: dict[str, Any] = {}
    extra_body: dict[str, Any] = {}
    capabilities: dict[str, Any] = {}
    capability_overrides: dict[str, Any] = {}


class ModelPatch(BaseModel):
    display_name: str | None = None
    description: str | None = None
    icon: str | None = None
    model_family: str | None = None
    model_type: str | None = None
    category: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    priority: int | None = None
    weight: float | None = None
    generation_defaults: dict[str, Any] | None = None
    extra_body: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None
    capability_overrides: dict[str, Any] | None = None


class ModelOut(ORMModel):
    id: str
    provider_id: str
    model_id: str
    display_name: str
    description: str
    icon: str
    model_family: str
    model_type: str
    category: str
    context_window: int
    max_output_tokens: int
    enabled: bool
    is_default: bool
    priority: int
    weight: float
    generation_defaults: dict
    extra_body: dict
    capabilities: dict
    capability_overrides: dict
    effective_capabilities: dict = {}
    probe_status: str
    probed_at: datetime | None
    created_at: datetime
    provider_name: str = ""


class ConversationIn(BaseModel):
    title: str = "New chat"
    mode: str = "chat"
    model_id: str | None = None
    temporary: bool = False


class ConversationPatch(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None
    model_id: str | None = None
    project_id: str | None = None


class ConversationOut(ORMModel):
    id: str
    title: str
    mode: str
    model_id: str | None
    pinned: bool
    archived: bool
    temporary: bool
    project_id: str | None
    current_leaf_id: str | None = None
    created_at: datetime
    updated_at: datetime
    preview: str = ""


class BlockOut(BaseModel):
    id: str
    seq: int
    type: str
    data: dict


class MessageOut(ORMModel):
    id: str
    conversation_id: str
    parent_id: str | None
    role: str
    model_id: str | None
    status: str
    error: dict | None
    usage: dict | None
    created_at: datetime
    blocks: list[BlockOut] = []


class RunIn(BaseModel):
    content: str = ""
    parent_id: str | None = None
    model_id: str | None = None
    reasoning_effort: Literal["auto", "low", "medium", "high", "extra_high"] | None = None
    file_ids: list[str] = []
    web_search: bool = False


class BrandingOut(BaseModel):
    product_name: str
    logo_url: str | None
    accent_color: str
    icon_set: str
    tagline: str


class BrandingPatch(BaseModel):
    product_name: str | None = None
    logo_url: str | None = None
    accent_color: str | None = None
    icon_set: str | None = None
    tagline: str | None = None


TokenOut.model_rebuild()
