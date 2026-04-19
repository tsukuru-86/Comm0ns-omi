import asyncio
import json
import websockets


async def test():
    async with websockets.connect('ws://localhost:8090/ws/listen?language=en&uid=tsukuru') as ws:
        print('Connected:', json.loads(await ws.recv()))
        for i in range(20):
            await ws.send(bytes(320))
            await asyncio.sleep(0.02)
            try:
                msg = await asyncio.wait_for(ws.recv(), 0.01)
                print('Transcript:', json.loads(msg)['segment']['text'])
            except Exception:
                pass


asyncio.run(test())
