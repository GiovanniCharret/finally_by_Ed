"""Chat route — delegates to app.llm.chat.handle_chat_message."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.llm.chat import handle_chat_message

from .dependencies import get_db, get_price_cache

router = APIRouter(tags=["chat"])


class ChatRequestBody(BaseModel):
    message: str


@router.post("/chat")
async def chat_endpoint(
    req: ChatRequestBody,
    db: Any = Depends(get_db),
    price_cache: Any = Depends(get_price_cache),
) -> Any:
    if not req.message or not req.message.strip():
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "empty_message",
                    "message": "Chat message cannot be empty.",
                }
            },
        )
    return await handle_chat_message(req.message, db, price_cache)
