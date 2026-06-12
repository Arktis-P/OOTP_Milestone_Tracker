"""Player registry for future manual player additions."""

from __future__ import annotations

from core.stats.aggregator import Aggregator


class PlayerRegistry:
    """Hook for adding players outside normal import paths."""

    def __init__(self, aggregator: Aggregator) -> None:
        self.aggregator = aggregator

    def add_player_stub(self, full_name: str) -> int:
        """Future: allocate player_id and INSERT into players."""
        raise NotImplementedError("선수 추가 기능은 추후 지원됩니다")
