from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class CharId:
    counter: int
    client: str


@dataclass(frozen=True)
class InsertOp:
    id: CharId
    after: CharId | None
    value: str


@dataclass(frozen=True)
class DeleteOp:
    id: CharId


Op = InsertOp | DeleteOp


@dataclass
class Char:
    id: CharId
    value: str
    deleted: bool = False


class Document:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.counter = 0
        self.chars: list[Char] = []
        self.outbox: list[Op] = []

    def text(self) -> str:
        return "".join(c.value for c in self.chars if not c.deleted)

    def _next_id(self) -> CharId:
        self.counter += 1
        return CharId(self.counter, self.client_id)

    def _index_of(self, char_id: CharId) -> int:
        for i, c in enumerate(self.chars):
            if c.id == char_id:
                return i
        raise KeyError(char_id)

    # --- local edits: apply now, remember to send later ---

    def insert_after(self, after_id: CharId | None, value: str) -> CharId:
        op = InsertOp(self._next_id(), after_id, value)
        self.apply(op)
        self.outbox.append(op)
        return op.id

    def delete(self, char_id: CharId) -> None:
        op = DeleteOp(char_id)
        self.apply(op)
        self.outbox.append(op)

    def take_outbox(self) -> list[Op]:
        ops, self.outbox = self.outbox, []
        return ops

    # --- applying any operation, local or remote ---

    def apply(self, op: Op) -> None:
        if isinstance(op, InsertOp):
            self._apply_insert(op)
        else:
            self._apply_delete(op)

    def _apply_insert(self, op: InsertOp) -> None:
        if any(c.id == op.id for c in self.chars):
            return  # already have it, so duplicates are harmless
        self.counter = max(self.counter, op.id.counter)
        index = 0 if op.after is None else self._index_of(op.after) + 1
        # tie-break: skip over characters with a bigger ID
        while index < len(self.chars) and self.chars[index].id > op.id:
            index += 1
        self.chars.insert(index, Char(op.id, op.value))

    def _apply_delete(self, op: DeleteOp) -> None:
        self.chars[self._index_of(op.id)].deleted = True