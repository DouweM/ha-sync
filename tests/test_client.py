"""Tests for HAClient entity-registry discovery."""

import pytest

from ha_sync.client import HAClient


class TestGetScenes:
    """Tests for HAClient.get_scenes()."""

    @pytest.mark.asyncio
    async def test_returns_unique_id_not_object_id(self) -> None:
        """Scenes must be discovered by unique_id (the storage config id).

        HA's /api/config/scene/config/<id> endpoint is keyed by the scene's
        numeric storage id, exposed as unique_id in the entity registry. UI
        scenes have an object_id (slugified name) that differs from that id, so
        returning the object_id makes the config fetch 404.
        """
        client = HAClient("http://test", "token")
        client._entity_registry_cache = [
            {"entity_id": "scene.good_morning", "unique_id": "1779999288609"},
            {"entity_id": "automation.foo", "unique_id": "abc"},
        ]

        assert await client.get_scenes() == ["1779999288609"]


class FakeWSMessage:
    def __init__(self, type_, data=None):
        self.type = type_
        self._data = data

    def json(self):
        import json

        return json.loads(self._data)


class FakeWS:
    """Scripted WebSocket: queues of messages to yield per receive() call."""

    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def receive(self):
        return self.messages.pop(0)

    async def close(self):
        pass


class TestSendCommandReconnect:
    """send_command must survive a WebSocket that HA closed mid-session.

    The connection can idle out while other syncers do slow HTTP work; the old
    code crashed with "Received message 257:None is not WSMsgType.TEXT" and the
    push reported "No changes" even though nothing was saved.
    """

    @pytest.mark.asyncio
    async def test_reconnects_and_retries_on_closed_connection(self, monkeypatch) -> None:
        import json

        import aiohttp

        client = HAClient("http://test", "token")

        dead_ws = FakeWS([FakeWSMessage(aiohttp.WSMsgType.CLOSED)])
        live_ws = FakeWS(
            [
                FakeWSMessage(
                    aiohttp.WSMsgType.TEXT,
                    json.dumps({"id": 2, "type": "result", "success": True, "result": {"ok": 1}}),
                )
            ]
        )
        client._ws = dead_ws  # type: ignore[assignment]

        async def fake_connect():
            client._ws = live_ws  # type: ignore[assignment]

        async def fake_cleanup():
            client._ws = None

        monkeypatch.setattr(client, "connect", fake_connect)
        monkeypatch.setattr(client, "_cleanup_ws", fake_cleanup)

        result = await client.send_command("lovelace/config/save", config={"a": 1})

        assert result == {"ok": 1}
        # The command was re-sent on the new connection.
        assert live_ws.sent == [{"id": 2, "type": "lovelace/config/save", "config": {"a": 1}}]

    @pytest.mark.asyncio
    async def test_raises_after_second_closed_connection(self, monkeypatch) -> None:
        import aiohttp

        from ha_sync.client import ConnectionFailed

        client = HAClient("http://test", "token")
        client._ws = FakeWS([FakeWSMessage(aiohttp.WSMsgType.CLOSED)])  # type: ignore[assignment]

        async def fake_connect():
            client._ws = FakeWS([FakeWSMessage(aiohttp.WSMsgType.CLOSED)])  # type: ignore[assignment]

        async def fake_cleanup():
            client._ws = None

        monkeypatch.setattr(client, "connect", fake_connect)
        monkeypatch.setattr(client, "_cleanup_ws", fake_cleanup)

        with pytest.raises(ConnectionFailed):
            await client.send_command("lovelace/config/save", config={"a": 1})
