import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Input, Static, TextArea
from websockets.asyncio.client import connect

from concode.document import Document
from concode.protocol import decode, encode

LANGUAGES = {
    ".py": "python", ".js": "javascript", ".json": "json", ".md": "markdown",
    ".html": "html", ".css": "css", ".rs": "rust", ".go": "go", ".java": "java",
    ".sh": "bash", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".sql": "sql",
}


# Which program runs which language.
RUNNERS = {"python": sys.executable, "javascript": "node"}
RUN_TIMEOUT = 60  # seconds before a run is stopped (protects against infinite loops)
MAX_OUTPUT = 20_000  # characters of output we keep


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
    #editor { height: 1fr; }
    #output { height: 10; border-top: solid $primary; }
    #stdin { height: 3; }
    """
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+s", "save", "Save"),
        ("f5", "run", "Run"),
        ("ctrl+r", "run", "Run"),
        ("escape", "stop", "Stop"),
        ("ctrl+t", "stop", "Stop"),
    ]
    run_timeout = RUN_TIMEOUT

    def __init__(
        self,
        room: str = "default",
        url: str = "ws://localhost:8765",
        file: str | None = None,
        language: str | None = None,
    ):
        super().__init__()
        self.room = room
        self.url = url
        self.file = Path(file) if file else None
        self.file_text = (
            self.file.read_text(encoding="utf-8")
            if self.file and self.file.exists()
            else None  # a new file: start empty, Ctrl+S will create it
        )
        self.language = language or (
            LANGUAGES.get(self.file.suffix.lower()) if self.file else None
        )
        self.doc = Document(uuid4().hex[:8])  # random unique client ID
        self.outgoing: asyncio.Queue[str] = asyncio.Queue()
        self.state = "connecting"
        self._run_busy = False
        self._run_proc = None  # the program currently running, if any
        self._run_transcript = ""  # everything it has printed (plus what was typed to it)
        self._run_stopped = False

    def compose(self) -> ComposeResult:
        yield Static(self._status_text(), id="status")
        yield SharedTextArea(id="editor", show_line_numbers=True, tab_behavior="indent")
        yield TextArea("", id="output", read_only=True)
        yield Input(id="stdin", placeholder="Program input: type here and press Enter")

    def on_mount(self) -> None:
        editor = self.query_one(SharedTextArea)
        if self.language:
            try:
                editor.language = self.language
            except Exception:
                self.language = None  # highlighting not installed: carry on without it
        self.query_one("#stdin", Input).display = False  # only shown while a program runs
        editor.focus()
        self.run_worker(self._network())

    # ---------- status bar ----------

    def _status_text(self) -> str:
        return (
            f"concode | room: {self.room} | you: {self.doc.client_id} | "
            f"{self.language or 'plain text'} | {self.state} | "
            "Ctrl+R run | Esc stop | Ctrl+S save | Ctrl+Q quit"
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

    # ---------- saving and loading a file ----------

    def action_save(self) -> None:
        self._sync_local()
        path = self.file or Path(f"concode-{self.room}.txt")
        try:
            path.write_text(self.query_one(SharedTextArea).text, encoding="utf-8")
        except OSError as error:
            self.notify(f"Could not save {path}: {error}", severity="error")
            return
        self.notify(f"Saved {path}")

    def _handle_seed_reply(self, granted: bool) -> None:
        if not self.file_text:
            return
        if granted:
            editor = self.query_one(SharedTextArea)
            editor.load_text(self.file_text)
            self._sync_local()  # turns the whole file into insert operations
            editor.move_cursor((0, 0))
            self.notify(f"Loaded {self.file} into the room")
        else:
            self.notify("This room already has content, so your file was not loaded.")

    # ---------- running code ----------

    def _show_output(self, header: str, text: str) -> None:
        output = self.query_one("#output", TextArea)
        output.load_text(f"{header}\n{text}")
        output.move_cursor(output.document.end)  # scroll to the newest line

    def _add_output(self, text: str) -> None:
        self._run_transcript = (self._run_transcript + text)[-MAX_OUTPUT:]
        self._show_output(f"Running {self.language} ...", self._run_transcript)

    def action_run(self) -> None:
        if not self._run_busy:
            self.run_worker(self._run_code())

    def action_stop(self) -> None:
        if self._run_proc is not None:
            self._run_stopped = True
            self._run_proc.kill()

    async def action_quit(self) -> None:
        self.action_stop()  # don't leave a running program behind
        await super().action_quit()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """The person typed a line for the running program."""
        if event.input.id != "stdin" or self._run_proc is None:
            return
        line = event.value
        event.input.value = ""
        self._add_output(line + "\n")  # show what was typed, like a terminal would
        try:
            self._run_proc.stdin.write((line + "\n").encode("utf-8"))
            await self._run_proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the program already finished

    async def _run_code(self) -> None:
        runner = RUNNERS.get(self.language or "")
        if runner is None or (runner != sys.executable and shutil.which(runner) is None):
            self._show_output(
                "Run",
                f"Cannot run '{self.language or 'plain text'}' yet. "
                "Python and JavaScript (needs Node.js) are supported.",
            )
            return
        self._sync_local()
        code = self.query_one(SharedTextArea).text
        self._run_busy = True
        self._run_transcript = ""
        self._run_stopped = False
        stdin_box = self.query_one("#stdin", Input)
        stdin_box.value = ""
        stdin_box.display = True
        stdin_box.focus()
        self._show_output(
            f"Running {self.language} ... (type input below, Esc to stop)", ""
        )
        try:
            await self._execute(runner, code)
        finally:
            self._run_busy = False
            self._run_proc = None
        try:
            stdin_box.display = False
            self.query_one(SharedTextArea).focus()
            output = self._run_transcript or "(no output)"
            self._show_output("Output (run by you)", output)
        except NoMatches:
            return  # the editor was closed while the program was running
        self.outgoing.put_nowait(json.dumps({
            "type": "output", "by": self.doc.client_id, "text": output,
        }))

    async def _execute(self, runner: str, code: str) -> None:
        name = self.file.name if self.file else (
            "main.py" if self.language == "python" else "main.js"
        )
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / name
            script.write_text(code, encoding="utf-8")
            # Run in the current folder so the program can import and open your other files.
            python_path = os.pathsep.join(
                [os.getcwd()] + ([os.environ["PYTHONPATH"]] if "PYTHONPATH" in os.environ else [])
            )
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": python_path}
            arguments = [runner, "-u", str(script)] if self.language == "python" else [runner, str(script)]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *arguments,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )
            except OSError as error:
                self._run_transcript = f"Could not start {runner}: {error}"
                return
            self._run_proc = proc

            async def pump() -> None:
                while True:
                    chunk = await proc.stdout.read(1024)
                    if not chunk:
                        break
                    self._add_output(chunk.decode("utf-8", errors="replace"))
                await proc.wait()

            try:
                await asyncio.wait_for(pump(), self.run_timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                self._add_output(
                    f"\nStopped: the program ran for more than {self.run_timeout} seconds."
                )
                return
            if self._run_stopped:
                self._add_output("\n[stopped]")
            elif proc.returncode != 0:
                self._add_output(f"\n[exited with code {proc.returncode}]")

    # ---------- networking ----------

    async def _network(self) -> None:
        try:
            async with connect(f"{self.url}/{self.room}") as ws:
                self._set_state("connected")

                async def sender() -> None:
                    while True:
                        await ws.send(await self.outgoing.get())

                send_task = asyncio.create_task(sender())
                if self.file_text:
                    self.outgoing.put_nowait(json.dumps({"type": "seed_request"}))
                try:
                    async for message in ws:
                        data = json.loads(message)
                        if data.get("type") == "seed":
                            self._handle_seed_reply(data["granted"])
                        elif data.get("type") == "output":
                            self._show_output(
                                f"Output (run by {data.get('by', '?')})",
                                str(data.get("text", ""))[:MAX_OUTPUT],
                            )
                        else:
                            self._apply_remote(decode(message))
                finally:
                    send_task.cancel()
            self._set_state("disconnected")
        except OSError:
            self._set_state("could not connect (is the server running?)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collaborative terminal editor.")
    parser.add_argument("room", nargs="?", default="default", help="room name to join")
    parser.add_argument("--server", default="ws://localhost:8765",
                        help="server address, e.g. ws://192.168.1.5:8765")
    parser.add_argument("--file", help="file to open (or create) and save to; loaded into the room if it is empty")
    parser.add_argument("--language", help="syntax highlighting, e.g. python, javascript")
    args = parser.parse_args()
    if args.file and Path(args.file).is_dir():
        parser.error(f"{args.file} is a folder, not a file")
    Editor(args.room, args.server, args.file, args.language).run()


if __name__ == "__main__":
    main()