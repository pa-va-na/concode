import asyncio
from websockets.asyncio.server import serve

clients = set()


async def handler(websocket):
    clients.add(websocket)
    try:
        async for message in websocket:
            for other in list(clients):
                if other is not websocket:
                    await other.send(message)
    finally:
        clients.remove(websocket)


async def main():
    async with serve(handler, "localhost", 8765):
        print("Relay running on ws://localhost:8765")
        await asyncio.Future()


asyncio.run(main())