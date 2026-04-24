"""Character CRUD contracts."""

from __future__ import annotations

from app.domain.cards import (
    CharacterDeleteResult,
    delete_character_preserving_thread_snapshots,
)


class FakeCharacterRepository:
    def __init__(self) -> None:
        self.thread_snapshot = {
            "thread_id": "thread-1",
            "character_id": "character-1",
            "character_snapshot": {
                "name": "Historical Character",
                "first_mes": "This opening line must survive deletion.",
            },
        }

    async def delete_character_preserving_thread_snapshots(
        self,
        character_id: str,
    ) -> CharacterDeleteResult:
        assert character_id == "character-1"
        return CharacterDeleteResult(
            character_id=character_id,
            deleted_at="2026-04-24T00:00:00Z",
            preserved_thread_ids=(self.thread_snapshot["thread_id"],),
            strategy="soft_delete",
        )


async def test_character_delete_preserves_existing_thread_snapshot() -> None:
    repository = FakeCharacterRepository()

    result = await delete_character_preserving_thread_snapshots(
        "character-1",
        repository=repository,
    )

    assert result.deleted_at is not None
    assert result.strategy in {"soft_delete", "detach_threads"}
    assert result.preserved_thread_ids == ("thread-1",)
    assert repository.thread_snapshot["character_snapshot"]["name"] == "Historical Character"
    assert (
        repository.thread_snapshot["character_snapshot"]["first_mes"]
        == "This opening line must survive deletion."
    )
