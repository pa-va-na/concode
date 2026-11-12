import asyncio
from websockets.asyncio.client import connect


async def main():
    async with connect("ws://localhost:8765") as ws:
        await ws.send("hello")
        print(await ws.recv())


asyncio.run(main())