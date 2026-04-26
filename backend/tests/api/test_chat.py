"""Tests for the /api/chat route."""

from __future__ import annotations


def test_chat_with_mock_returns_message(client, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert "message" in body
    assert isinstance(body["message"], str) and body["message"]
    assert body["trades"] == []
    assert body["watchlist_changes"] == []
    assert body["action_results"] == []


def test_chat_empty_message_rejected(client, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_message"


def test_chat_persists_messages(client, monkeypatch, db_conn) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    response = client.post("/api/chat", json={"message": "what is up"})
    assert response.status_code == 200

    import asyncio

    async def _read():
        async with db_conn.execute(
            "SELECT role, content FROM chat_messages ORDER BY created_at"
        ) as cursor:
            return list(await cursor.fetchall())

    rows = asyncio.get_event_loop().run_until_complete(_read())
    assert [r[0] for r in rows] == ["user", "assistant"]
    assert rows[0][1] == "what is up"
