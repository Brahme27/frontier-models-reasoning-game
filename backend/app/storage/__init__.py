from app.config import Settings
from app.storage.base import MemoryRepository, Repository
from app.storage.dynamo_repo import DynamoRepository
from app.storage.sqlite_repo import SqliteRepository


def build_repository(settings: Settings) -> Repository:
    if settings.storage_backend == "dynamodb":
        return DynamoRepository(settings.dynamodb_table, settings.aws_region)
    if settings.storage_backend == "memory":
        return MemoryRepository()
    return SqliteRepository(settings.sqlite_path)


__all__ = ["Repository", "build_repository"]
