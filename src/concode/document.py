from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class CharId:
    counter: int
    client: str


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

    def insert_after(self, after_id: CharId | None, value: str) -> CharId:
        new = Char(self._next_id(), value)
        index = 0 if after_id is None else self._index_of(after_id) + 1
        self.chars.insert(index, new)
        return new.id

    def delete(self, char_id: CharId) -> None:
        self.chars[self._index_of(char_id)].deleted = True