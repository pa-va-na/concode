import asyncio


async def worker(name, delay):
    for i in range(3):
        await asyncio.sleep(delay)
        print(f"{name} step {i}")


async def main():
    await asyncio.gather(worker("A", 1), worker("B", 1.4))


asyncio.run(main())