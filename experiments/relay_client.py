import asyncio
import sys
from datetime import datetime
from websockets.asyncio.client import connect


async def main():
    mode = sys.argv[1]
    async with connect("ws://localhost:8765") as ws:
        if mode == "listen":
            async for message in ws:
                print("got:", message)
                print(datetime.now().strftime("%H:%M:%S.%f"))
        else:
            await ws.send(sys.argv[2])


asyncio.run(main())