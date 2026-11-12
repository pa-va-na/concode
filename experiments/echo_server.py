import asyncio
from websockets.asyncio.server import serve


async def handler(websocket):
    async for message in websocket:
        await websocket.send(f"echo: {message}")


async def main():
    async with serve(handler, "localhost", 8765):
        print("Server running on ws://localhost:8765")
        await asyncio.Future()  # keep running forever


asyncio.run(main())