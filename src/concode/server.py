import argparse
import asyncio
import json

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


class Room:
    def __init__(self):
        self.clients = set()
        self.history = []  # every operation (as text), in the order the server received it
        self.seeded = False  # has someone already been allowed to load a file into this room?


rooms: dict[str, Room] = {}


async def handler(websocket):
    name = websocket.request.path.strip("/") or "default"
    room = rooms.setdefault(name, Room())

    # Catch the new client up on everything that happened before it joined.
    sent = 0
    while sent < len(room.history):
        await websocket.send(room.history[sent])
        sent += 1
    room.clients.add(websocket)

    try:
        async for message in websocket:
            try:
                kind = json.loads(message).get("type")
            except (ValueError, AttributeError):
                continue  # not valid JSON: ignore it

            if kind == "seed_request":
                # "May I load my file into this room?" Only the first asker, and
                # only if the room is still empty, gets a yes.
                granted = not room.history and not room.seeded
                if granted:
                    room.seeded = True
                await websocket.send(json.dumps({"type": "seed", "granted": granted}))
                continue

            if kind in ("insert", "delete"):
                room.history.append(message)  # edits are remembered for late joiners
            # anything else (like run output) is passed on but not remembered
            for other in list(room.clients):
                if other is not websocket:
                    try:
                        await other.send(message)
                    except ConnectionClosed:
                        pass  # that client just left; it will be removed shortly
    except ConnectionClosed:
        pass  # this client left (closing the window counts)
    finally:
        room.clients.discard(websocket)


async def run(host: str = "localhost", port: int = 8765) -> None:
    async with serve(handler, host, port):
        print(f"Concode server running on ws://{host}:{port}")
        await asyncio.Future()


# Kept so older code and tests can still call server.main(port)
async def main(port: int = 8765) -> None:
    await run("localhost", port)


def cli() -> None:
    parser = argparse.ArgumentParser(description="Run a Concode server.")
    parser.add_argument("--host", default="localhost",
                        help="address to listen on (use 0.0.0.0 to accept other computers)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(run(args.host, args.port))


if __name__ == "__main__":
    cli()