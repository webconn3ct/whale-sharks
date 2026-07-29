"""In-process singleton cache. All API reads hit this; nothing here ever
triggers a live scan. Snapshots are immutable — refresh() does an atomic
reference swap so concurrent readers never observe partial state."""

from app.api.schemas import ConsensusSnapshot


class ConsensusCache:
    def __init__(self) -> None:
        self._snapshot: ConsensusSnapshot | None = None

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    @property
    def snapshot(self) -> ConsensusSnapshot | None:
        return self._snapshot

    def refresh(self, snapshot: ConsensusSnapshot) -> None:
        self._snapshot = snapshot


cache = ConsensusCache()
