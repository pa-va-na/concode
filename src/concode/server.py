import asyncio

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


class Room:
    def __init__(self):
        self.clients = set()
        self.history = []  # every operation (as text), in the order the server received it


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
            room.history.append(message)
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


async def main(port: int = 8765):
    async with serve(handler, "localhost", port):
        print(f"Concode server running on ws://localhost:{port}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())