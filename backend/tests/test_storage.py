from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from app.config import Settings
from app.events.bus import EventBus, GameEvent
from app.game.state import GameConfig
from app.storage import build_repository
from app.storage.base import GameRecord, MemoryRepository, Repository, SeatInfo
from app.storage.dynamo_repo import DynamoRepository
from app.storage.sqlite_repo import SqliteRepository


def record(game_id: str, created_at: float, status: str = "running") -> GameRecord:
    return GameRecord(
        id=game_id,
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
        backend="fake",
        config=GameConfig(),
        seats=[
            SeatInfo(
                player_id="alex",
                name="Alex",
                model_key="m",
                display_name="M",
                lab="Lab",
                color="#fff",
                emoji="x",
                reasoning="none",
                provider="fake",
            )
        ],
    )


def event(game_id: str, seq: int, data: dict[str, Any] | None = None) -> GameEvent:
    return GameEvent(
        game_id=game_id, seq=seq, type="test", round=0, ts=float(seq), data=data or {"value": 1.5}
    )


def create_dynamo_table() -> Any:
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    resource.create_table(
        TableName="games",
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
            {"AttributeName": "gsi1pk", "AttributeType": "S"},
            {"AttributeName": "gsi1sk", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "gsi1",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )
    return resource


@pytest.fixture(params=["memory", "sqlite", "dynamodb"])
async def repo(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Repository]:
    if request.param == "memory":
        repository: Repository = MemoryRepository()
        await repository.init()
        yield repository
    elif request.param == "sqlite":
        repository = SqliteRepository(tmp_path / "test.db")
        await repository.init()
        yield repository
        await repository.close()
    else:
        with mock_aws():
            repository = DynamoRepository("games", "us-east-1", resource=create_dynamo_table())
            await repository.init()
            yield repository


class TestRepositoryContract:
    async def test_save_and_get(self, repo: Repository) -> None:
        await repo.save_game(record("g1", 100.0))
        loaded = await repo.get_game("g1")
        assert loaded is not None
        assert loaded.id == "g1"
        assert loaded.seats[0].name == "Alex"
        assert await repo.get_game("missing") is None

    async def test_save_replaces(self, repo: Repository) -> None:
        await repo.save_game(record("g1", 100.0))
        await repo.save_game(record("g1", 100.0, status="finished"))
        loaded = await repo.get_game("g1")
        assert loaded is not None and loaded.status == "finished"
        assert len(await repo.list_games()) == 1

    async def test_list_newest_first_with_limit(self, repo: Repository) -> None:
        for i, ts in enumerate([100.0, 300.0, 200.0]):
            await repo.save_game(record(f"g{i}", ts))
        games = await repo.list_games(limit=2)
        assert [g.id for g in games] == ["g1", "g2"]

    async def test_count_since(self, repo: Repository) -> None:
        for i, ts in enumerate([100.0, 300.0, 200.0]):
            await repo.save_game(record(f"g{i}", ts))
        assert await repo.count_games_since(150.0) == 2
        assert await repo.count_games_since(1000.0) == 0

    async def test_events_round_trip_in_order(self, repo: Repository) -> None:
        for seq in [2, 0, 1]:
            await repo.append_event(event("g1", seq))
        await repo.append_event(event("g2", 0))
        events = await repo.list_events("g1")
        assert [e.seq for e in events] == [0, 1, 2]
        assert events[0].data == {"value": 1.5}
        assert await repo.list_events("none") == []


async def test_sqlite_requires_init(tmp_path: Path) -> None:
    repository = SqliteRepository(tmp_path / "x.db")
    with pytest.raises(RuntimeError):
        await repository.get_game("x")


def test_build_repository_selects_backend(tmp_path: Path) -> None:
    assert isinstance(build_repository(Settings(storage_backend="memory")), MemoryRepository)
    assert isinstance(
        build_repository(Settings(storage_backend="sqlite", sqlite_path=tmp_path / "a.db")),
        SqliteRepository,
    )
    with mock_aws():
        assert isinstance(build_repository(Settings(storage_backend="dynamodb")), DynamoRepository)


class TestEventBus:
    async def test_fan_out_and_close(self) -> None:
        bus = EventBus()
        async with bus.subscribe("g") as q1, bus.subscribe("g") as q2:
            assert bus.subscriber_count("g") == 2
            bus.publish(event("g", 0))
            bus.publish(event("other", 0))
            bus.close("g")
            assert (await q1.get()).seq == 0  # type: ignore[union-attr]
            assert (await q2.get()).seq == 0  # type: ignore[union-attr]
            assert await q1.get() is None
        assert bus.subscriber_count("g") == 0
