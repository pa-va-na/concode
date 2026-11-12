import asyncio
import sys
from uuid import uuid4

from textual.app import App, ComposeResult
from textual.widgets import Static, TextArea
from websockets.asyncio.client import connect

from concode.document import Document
from concode.protocol import decode, encode


class SharedTextArea(TextArea):
    """A TextArea with undo/redo switched off.

    The built-in undo knows nothing about other people's edits and would
    corrupt the shared document, so we disable it for now.
    """

    def action_undo(self) -> None:
        pass

    def action_redo(self) -> None:
        pass


class Editor(App):
    CSS = """
    #status { height: 1; background: $primary; color: $text; padding: 0 1; }
    """
    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(self, room: str = "default", url: str = "ws://localhost:8765"):
        super().__init__()
        self.room = room
        self.url = url
        self.doc = Document(uuid4().hex[:8])  # random unique client ID
        self.outgoing: asyncio.Queue[str] = asyncio.Queue()
        self.state = "connecting"

    def compose(self) -> ComposeResult:
        yield Static(self._status_text(), id="status")
        yield SharedTextArea(id="editor")

    def on_mount(self) -> None:
        self.query_one(SharedTextArea).focus()
        self.run_worker(self._network())

    # ---------- status bar ----------

    def _status_text(self) -> str:
        return (
            f"concode | room: {self.room} | you: {self.doc.client_id} | "
            f"{self.state} | Ctrl+Q to quit"
        )

    def _set_state(self, state: str) -> None:
        self.state = state
        self.query_one("#status", Static).update(self._status_text())

    # ---------- helpers ----------

    def _visible(self):
        return [c for c in self.doc.chars if not c.deleted]

    # ---------- local edits: the screen changed, so tell the CRDT ----------

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._sync_local()

    def _sync_local(self) -> None:
        editor = self.query_one(SharedTextArea)
        new, old = editor.text, self.doc.text()
        if new == old:
            return
        visible = self._visible()

        prefix = 0
        while prefix < min(len(old), len(new)) and old[prefix] == new[prefix]:
            prefix += 1
        suffix = 0
        while (
            suffix < min(len(old), len(new)) - prefix
            and old[-1 - suffix] == new[-1 - suffix]
        ):
            suffix += 1

        for char in visible[prefix : len(old) - suffix]:
            self.doc.delete(char.id)
        anchor = visible[prefix - 1].id if prefix > 0 else None
        for ch in new[prefix : len(new) - suffix]:
            anchor = self.doc.insert_after(anchor, ch)

        for op in self.doc.take_outbox():
            self.outgoing.put_nowait(encode(op))

    # ---------- remote edits: someone else changed the document ----------

    def _apply_remote(self, op) -> None:
        editor = self.query_one(SharedTextArea)
        self._sync_local()  # never overwrite something typed but not yet synced

        # Remember the cursor as "just after this character", not as a number.
        offset = editor.document.get_index_from_location(editor.cursor_location)
        visible = self._visible()
        anchor_id = visible[offset - 1].id if offset > 0 else None

        self.doc.apply(op)

        if self.doc.text() == editor.text:
            return
        if anchor_id is None:
            new_offset = 0
        else:
            index = self.doc._index_of(anchor_id)
            new_offset = sum(1 for c in self.doc.chars[: index + 1] if not c.deleted)

        editor.load_text(self.doc.text())
        editor.move_cursor(editor.document.get_location_from_index(new_offset))

    # ---------- networking ----------

    async def _network(self) -> None:
        try:
            async with connect(f"{self.url}/{self.room}") as ws:
                self._set_state("connected")

                async def sender() -> None:
                    while True:
                        await ws.send(await self.outgoing.get())

                send_task = asyncio.create_task(sender())
                try:
                    async for message in ws:
                        self._apply_remote(decode(message))
                finally:
                    send_task.cancel()
            self._set_state("disconnected")
        except OSError:
            self._set_state("could not connect (is the server running?)")


def main() -> None:
    room = sys.argv[1] if len(sys.argv) > 1 else "default"
    Editor(room).run()


if __name__ == "__main__":
    main()