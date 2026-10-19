import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.security import limiter
from app.config import Settings
from app.main import create_app

PASS = {"X-Admin-Passcode": "s3cret"}


def settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "app_env": "test",
        "demo_mode": True,
        "storage_backend": "memory",
        "event_pacing_ms": 0,
        "admin_passcode": "s3cret",
        "max_games_per_day": 50,
        "max_concurrent_games": 5,
    }
    return Settings(**{**base, **overrides})


@pytest.fixture(autouse=True)
def reset_rate_limits() -> Iterator[None]:
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(settings())) as c:
        yield c


def wait_finished(client: TestClient, game_id: str, timeout: float = 30) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail: dict[str, Any] = client.get(f"/api/games/{game_id}").json()
        if detail["game"]["status"] != "running":
            return detail
        time.sleep(0.05)
    raise AssertionError("game did not finish")


class TestPublicEndpoints:
    def test_health(self, client: TestClient) -> None:
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["backend"] == "fake"
        assert body["demo_mode"] is True

    def test_security_headers(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_models_lists_roster_without_internal_extras(self, client: TestClient) -> None:
        body = client.get("/api/models").json()
        assert len(body["players"]) == 4
        assert "extra" not in body["players"][0]
        assert body["players"][0]["benchmarks"]

    def test_unknown_game_404(self, client: TestClient) -> None:
        assert client.get("/api/games/nope").status_code == 404


class TestAuth:
    def test_start_requires_passcode(self, client: TestClient) -> None:
        assert client.post("/api/games").status_code == 401
        assert client.post("/api/games", headers={"X-Admin-Passcode": "wrong"}).status_code == 401

    def test_auth_check(self, client: TestClient) -> None:
        assert client.post("/api/auth/check", headers=PASS).status_code == 204
        assert client.post("/api/auth/check").status_code == 401

    def test_prod_without_configured_passcode_is_locked(self) -> None:
        with TestClient(create_app(settings(app_env="prod", admin_passcode=None))) as c:
            assert c.post("/api/games", headers=PASS).status_code == 401

    def test_dev_without_configured_passcode_is_open(self) -> None:
        with TestClient(create_app(settings(app_env="dev", admin_passcode=None))) as c:
            assert c.post("/api/games", json={"max_rounds": 3}).status_code == 201

    def test_rounds_are_validated(self, client: TestClient) -> None:
        assert client.post("/api/games", headers=PASS, json={"max_rounds": 99}).status_code == 422


class TestGameLifecycle:
    def test_full_game_via_api_and_leaderboard(self, client: TestClient) -> None:
        response = client.post("/api/games", headers=PASS, json={"max_rounds": 3})
        assert response.status_code == 201
        game_id = response.json()["id"]

        detail = wait_finished(client, game_id)
        assert detail["game"]["status"] == "finished"
        assert detail["live"] is False
        assert detail["game"]["winners"]
        assert detail["game"]["headline"]
        types = [e["type"] for e in detail["events"]]
        assert types[0] == "game_started"
        assert types[-1] == "report"
        assert [e["seq"] for e in detail["events"]] == list(range(len(types)))

        games = client.get("/api/games").json()
        assert games[0]["id"] == game_id

        board = client.get("/api/leaderboard").json()
        assert len(board) == 4
        assert {row["lab"] for row in board} >= {"OpenAI", "Alibaba Qwen"}
        assert abs(sum(row["wins"] for row in board) - 1) < 0.02  # ties split + 2dp rounding

    def test_websocket_replays_finished_game(self, client: TestClient) -> None:
        game_id = client.post("/api/games", headers=PASS, json={"max_rounds": 3}).json()["id"]
        wait_finished(client, game_id)
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "stream_end":
                    break
        assert messages[0]["type"] == "game_started"
        assert messages[-2]["type"] == "report"

    def test_websocket_streams_live_game(self) -> None:
        with TestClient(create_app(settings(event_pacing_ms=5))) as c:
            game_id = c.post("/api/games", headers=PASS, json={"max_rounds": 3}).json()["id"]
            with c.websocket_connect(f"/ws/games/{game_id}") as ws:
                seqs = []
                while True:
                    msg = ws.receive_json()
                    if msg["type"] == "stream_end":
                        break
                    seqs.append(msg["seq"])
            assert seqs == list(range(len(seqs)))  # no gaps, no duplicates
            assert len(seqs) > 20

    def test_websocket_unknown_game(self, client: TestClient) -> None:
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            client.websocket_connect("/ws/games/000000000000") as ws,
        ):
            ws.receive_json()
        assert exc.value.code == 4404


class TestSpendGuards:
    def test_daily_cap(self) -> None:
        with TestClient(create_app(settings(max_games_per_day=1))) as c:
            assert c.post("/api/games", headers=PASS, json={"max_rounds": 3}).status_code == 201
            response = c.post("/api/games", headers=PASS, json={"max_rounds": 3})
            assert response.status_code == 429
            assert "daily" in response.json()["detail"]

    def test_concurrency_cap(self) -> None:
        with TestClient(create_app(settings(max_concurrent_games=1, event_pacing_ms=200))) as c:
            assert c.post("/api/games", headers=PASS).status_code == 201
            response = c.post("/api/games", headers=PASS)
            assert response.status_code == 429
            assert "running" in response.json()["detail"]

    def test_wrong_passcodes_are_rate_limited(self) -> None:
        with TestClient(create_app(settings())) as c:
            codes = [
                c.post("/api/auth/check", headers={"X-Admin-Passcode": f"guess{i}"}).status_code
                for i in range(12)
            ]
            assert codes[:10] == [401] * 10
            assert codes[10:] == [429, 429]  # brute force is throttled, not just counted

    def test_rate_limit_by_trusted_viewer_ip(self) -> None:
        with TestClient(create_app(settings(trust_cloudfront_headers=True))) as c:
            hdr = {**PASS, "CloudFront-Viewer-Address": "1.2.3.4:1"}
            for _ in range(10):
                c.post("/api/auth/check", headers=hdr)
            blocked = c.post("/api/auth/check", headers=hdr)
            other = c.post(
                "/api/auth/check", headers={**PASS, "CloudFront-Viewer-Address": "5.6.7.8:1"}
            )
            assert blocked.status_code == 429
            assert other.status_code == 204

    def test_viewer_header_is_ignored_unless_trusted(self) -> None:
        with TestClient(create_app(settings())) as c:
            for i in range(10):  # rotating a spoofed header must not dodge the limit
                c.post(
                    "/api/auth/check", headers={**PASS, "CloudFront-Viewer-Address": f"9.9.9.{i}:1"}
                )
            assert c.post("/api/auth/check", headers=PASS).status_code == 429

    def test_oversized_body_is_rejected(self) -> None:
        with TestClient(create_app(settings())) as c:
            response = c.post("/api/games", headers=PASS, content=b"x" * 20_000)
            assert response.status_code == 413

    def test_websocket_viewers_are_capped_per_client(self) -> None:
        with TestClient(create_app(settings(max_ws_per_client=1, event_pacing_ms=200))) as c:
            game_id = c.post("/api/games", headers=PASS, json={"max_rounds": 3}).json()["id"]
            with c.websocket_connect(f"/ws/games/{game_id}") as first:
                first.receive_json()
                with (
                    pytest.raises(WebSocketDisconnect) as exc,
                    c.websocket_connect(f"/ws/games/{game_id}") as second,
                ):
                    second.receive_json()
                assert exc.value.code == 4429

    def test_api_docs_hidden_in_production(self) -> None:
        with TestClient(create_app(settings(app_env="prod"))) as c:
            assert c.get("/api/docs").status_code == 404
            assert c.get("/api/openapi.json").status_code == 404


class TestSpa:
    def test_serves_index_and_assets_but_not_api(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<html>outsmart</html>")
        (tmp_path / "app.js").write_text("console.log(1)")
        with TestClient(create_app(settings(static_dir=tmp_path))) as c:
            assert "outsmart" in c.get("/").text
            assert "outsmart" in c.get("/games/abc").text  # client-side route
            assert c.get("/app.js").text == "console.log(1)"
            assert c.get("/api/does-not-exist").status_code == 404
            assert "outsmart" in c.get("/../../etc/passwd").text  # no traversal
