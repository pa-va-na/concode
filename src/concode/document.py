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


@dataclass(eq=False)  # compare by identity: much faster list lookups
class Char:
    id: CharId
    value: str
    deleted: bool = False


class Document:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.counter = 0
        self.chars: list[Char] = []
        self._by_id: dict[CharId, Char] = {}
        self.outbox: list[Op] = []

    def text(self) -> str:
        return "".join(c.value for c in self.chars if not c.deleted)

    def _next_id(self) -> CharId:
        self.counter += 1
        return CharId(self.counter, self.client_id)

    def _index_of(self, char_id: CharId) -> int:
        return self.chars.index(self._by_id[char_id])

    # --- local edits: apply now, remember to send later ---

    def insert_after(self, after_id, value):
        op = InsertOp(self._next_id(), after_id, value)
        self.apply(op)
        self.outbox.append(op)
        return op.id

    def delete(self, char_id):
        op = DeleteOp(char_id)
        self.apply(op)
        self.outbox.append(op)

    def take_outbox(self):
        ops, self.outbox = self.outbox, []
        return ops

    # --- applying any operation, local or remote ---

    def apply(self, op):
        if isinstance(op, InsertOp):
            self._apply_insert(op)
        else:
            self._apply_delete(op)

    def _apply_insert(self, op):
        if op.id in self._by_id:
            return  # already have it, so duplicates are harmless
        self.counter = max(self.counter, op.id.counter)
        index = 0 if op.after is None else self._index_of(op.after) + 1
        # tie-break: skip over characters with a bigger ID
        while index < len(self.chars) and self.chars[index].id > op.id:
            index += 1
        char = Char(op.id, op.value)
        self.chars.insert(index, char)
        self._by_id[op.id] = char

    def _apply_delete(self, op):
        self._by_id[op.id].deleted = True