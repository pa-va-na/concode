class GCounter:
    """Grow-only counter CRDT."""

    def __init__(self, replica_id: str):
        self.replica_id = replica_id
        self.counts: dict[str, int] = {}

    def increment(self, amount: int = 1) -> None:
        self.counts[self.replica_id] = self.counts.get(self.replica_id, 0) + amount

    def value(self) -> int:
        return sum(self.counts.values())

    def merge(self, other: "GCounter") -> None:
        for replica_id, n in other.counts.items():
            self.counts[replica_id] = max(self.counts.get(replica_id, 0), n)