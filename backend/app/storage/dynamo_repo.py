"""DynamoDB single-table repository for production.

Key design (one table, on-demand billing):

    PK = GAME#<id>   SK = META          -> game record   (+ GSI1: gsi1pk=GAMES, gsi1sk=<created_at>)
    PK = GAME#<id>   SK = EVT#<seq:06>  -> one event

* Replaying a game = one Query on PK (events sort naturally by SK).
* Listing recent games / daily caps = Query on GSI1 sorted by creation time.
Documents are stored as JSON strings to avoid DynamoDB's float/Decimal friction.
"""

from __future__ import annotations

import asyncio
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from app.events.bus import GameEvent
from app.storage.base import GameRecord

GSI_NAME = "gsi1"
GSI_PK = "GAMES"


def _ts_key(ts: float) -> str:
    return f"{ts:017.6f}"  # fixed width -> lexicographic order == numeric order


class DynamoRepository:
    def __init__(self, table_name: str, region: str, resource: Any = None) -> None:
        self.table_name = table_name
        self._resource = resource or boto3.resource("dynamodb", region_name=region)
        self.table = self._resource.Table(table_name)

    async def init(self) -> None:
        return None  # table is provisioned by Terraform

    async def close(self) -> None:
        return None

    async def save_game(self, record: GameRecord) -> None:
        item = {
            "pk": f"GAME#{record.id}",
            "sk": "META",
            "gsi1pk": GSI_PK,
            "gsi1sk": _ts_key(record.created_at),
            "status": record.status,
            "doc": record.model_dump_json(),
        }
        await asyncio.to_thread(self.table.put_item, Item=item)

    async def get_game(self, game_id: str) -> GameRecord | None:
        resp = await asyncio.to_thread(
            self.table.get_item, Key={"pk": f"GAME#{game_id}", "sk": "META"}, ConsistentRead=True
        )
        item = resp.get("Item")
        return GameRecord.model_validate_json(item["doc"]) if item else None

    async def list_games(self, limit: int = 50) -> list[GameRecord]:
        resp = await asyncio.to_thread(
            self.table.query,
            IndexName=GSI_NAME,
            KeyConditionExpression=Key("gsi1pk").eq(GSI_PK),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [GameRecord.model_validate_json(i["doc"]) for i in resp.get("Items", [])]

    async def count_games_since(self, ts: float) -> int:
        resp = await asyncio.to_thread(
            self.table.query,
            IndexName=GSI_NAME,
            KeyConditionExpression=Key("gsi1pk").eq(GSI_PK) & Key("gsi1sk").gte(_ts_key(ts)),
            Select="COUNT",
        )
        return int(resp.get("Count", 0))

    async def append_event(self, event: GameEvent) -> None:
        item = {
            "pk": f"GAME#{event.game_id}",
            "sk": f"EVT#{event.seq:06d}",
            "doc": event.model_dump_json(),
        }
        await asyncio.to_thread(self.table.put_item, Item=item)

    async def list_events(self, game_id: str) -> list[GameEvent]:
        events: list[GameEvent] = []
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"GAME#{game_id}")
            & Key("sk").begins_with("EVT#"),
            "ConsistentRead": True,  # a viewer's backlog must include the latest event
        }
        while True:
            resp = await asyncio.to_thread(self.table.query, **kwargs)
            events.extend(GameEvent.model_validate_json(i["doc"]) for i in resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                return events
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
