import asyncio
import sys
from uuid import uuid4

from websockets.asyncio.client import connect

from concode.document import Document
from concode.protocol import decode, encode


async def receive(ws, doc):
    async for message in ws:
        doc.apply(decode(message))
        print(f"\n[text] {doc.text()}")


async def send_edits(ws, doc):
    while True:
        line = await asyncio.to_thread(input, "> ")
        command, _, argument = line.partition(" ")
        if command == "add":
            last = doc.chars[-1].id if doc.chars else None
            for ch in argument:
                last = doc.insert_after(last, ch)
        elif command == "del":
            visible = [c for c in doc.chars if not c.deleted]
            n = int(argument)
            if 1 <= n <= len(visible):
                doc.delete(visible[n - 1].id)
        elif command == "quit":
            return
        for op in doc.take_outbox():
            await ws.send(encode(op))
        print(f"[text] {doc.text()}")


async def main(room):
    doc = Document(uuid4().hex[:8])  # random unique client ID
    async with connect(f"ws://localhost:8765/{room}") as ws:
        receiver = asyncio.create_task(receive(ws, doc))
        await send_edits(ws, doc)
        receiver.cancel()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "default"))