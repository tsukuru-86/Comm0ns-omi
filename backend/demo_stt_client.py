"""
Test client for the STT Provider Abstraction Demo Server.

Usage:
    # Start the server first in another terminal:
    #   cd backend && source .venv/bin/activate && python demo_stt_server.py
    #
    # Then run this client:
    #   python demo_stt_client.py
"""

import asyncio
import json
import sys

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'httpx', 'websockets'])
    import httpx

import websockets


BASE = 'http://localhost:8090'
WS_BASE = 'ws://localhost:8090'

BOLD = '\033[1m'
GREEN = '\033[32m'
CYAN = '\033[36m'
YELLOW = '\033[33m'
RESET = '\033[0m'


def header(title):
    print(f'\n{BOLD}{CYAN}{"=" * 60}{RESET}')
    print(f'{BOLD}{CYAN}  {title}{RESET}')
    print(f'{BOLD}{CYAN}{"=" * 60}{RESET}')


def show(label, data):
    print(f'  {YELLOW}{label}:{RESET}')
    if isinstance(data, dict):
        print(f'    {json.dumps(data, indent=4, ensure_ascii=False)}')
    else:
        print(f'    {data}')


async def test_health():
    header('1. Health Check')
    async with httpx.AsyncClient() as client:
        r = await client.get(f'{BASE}/health')
        show('Response', r.json())
        assert r.status_code == 200
        print(f'  {GREEN}PASS{RESET}')


async def test_providers():
    header('2. List Providers')
    async with httpx.AsyncClient() as client:
        r = await client.get(f'{BASE}/providers')
        data = r.json()
        for p in data['streaming']:
            print(f'  Streaming: {BOLD}{p["name"]}{RESET} (aliases: {p["aliases"]})')
        for p in data['batch']:
            print(f'  Batch:     {BOLD}{p["name"]}{RESET} (aliases: {p["aliases"]})')
        print(f'  {GREEN}PASS{RESET}')


async def test_select():
    header('3. Provider Selection')
    async with httpx.AsyncClient() as client:
        # Default selection
        r = await client.post(f'{BASE}/select', json={'phase': 'realtime', 'language': 'en'})
        show('Default realtime (en)', r.json())

        # With user preference
        r = await client.post(f'{BASE}/select', json={
            'phase': 'finalize', 'language': 'ja', 'user_preference': 'mock_batch',
        })
        show('User pref finalize (ja)', r.json())

        # With provider hint
        r = await client.post(f'{BASE}/select', json={
            'phase': 'realtime', 'language': 'en', 'provider_hint': 'mock_streaming',
        })
        show('Hint override (en)', r.json())
        print(f'  {GREEN}PASS{RESET}')


async def test_transcribe_url():
    header('4. Batch Transcribe (URL)')
    async with httpx.AsyncClient() as client:
        r = await client.post(f'{BASE}/transcribe/url', json={
            'audio_url': 'https://example.com/test-audio.wav',
            'language': 'en',
            'uid': 'test-user-1',
        })
        data = r.json()
        show('Provider used', data['provider'])
        show('Language', data['language'])
        for i, seg in enumerate(data['segments']):
            print(f'    Segment {i}: [{seg["start"]:.1f}s - {seg["end"]:.1f}s] '
                  f'{seg["speaker"]}: "{seg["text"]}"')
        print(f'  {GREEN}PASS{RESET}')


async def test_transcribe_url_with_terminology():
    header('5. Batch Transcribe with Terminology Correction')
    async with httpx.AsyncClient() as client:
        r = await client.post(f'{BASE}/transcribe/url', json={
            'audio_url': 'https://example.com/test-audio.wav',
            'language': 'en',
            'terminology': {'abstraction layer': 'ABSTRACTION LAYER'},
        })
        data = r.json()
        for seg in data['segments']:
            print(f'    "{seg["text"]}"')
        has_correction = any('ABSTRACTION LAYER' in seg['text'] for seg in data['segments'])
        print(f'  Terminology applied: {GREEN}YES{RESET}' if has_correction else f'  Terminology applied: {YELLOW}(text did not contain target){RESET}')
        print(f'  {GREEN}PASS{RESET}')


async def test_transcribe_bytes():
    header('6. Batch Transcribe (Bytes)')
    async with httpx.AsyncClient() as client:
        r = await client.post(f'{BASE}/transcribe/bytes', json={
            'language': 'ja',
            'uid': 'test-user-2',
        })
        data = r.json()
        show('Provider used', data['provider'])
        for seg in data['segments']:
            print(f'    "{seg["text"]}"')
        print(f'  {GREEN}PASS{RESET}')


async def test_websocket_streaming():
    header('7. WebSocket Streaming')
    uri = f'{WS_BASE}/ws/listen?language=en&uid=ws-test-user'
    try:
        async with websockets.connect(uri) as ws:
            # Receive connection confirmation
            msg = json.loads(await ws.recv())
            show('Connected', msg)
            assert msg['type'] == 'connected'
            print(f'    Provider: {BOLD}{msg["provider"]}{RESET}')

            # Send simulated audio chunks
            print('    Sending 15 audio chunks...')
            for i in range(15):
                chunk = bytes([i % 256] * 320)  # 20ms of 16kHz 16-bit audio
                await ws.send(chunk)
                await asyncio.sleep(0.02)

                # Check for transcription events
                try:
                    while True:
                        response = await asyncio.wait_for(ws.recv(), timeout=0.01)
                        evt = json.loads(response)
                        seg = evt['segment']
                        print(f'    {GREEN}Event:{RESET} [{evt["provider"]}] "{seg["text"]}" '
                              f'({seg["start"]:.1f}s-{seg["end"]:.1f}s)')
                except (asyncio.TimeoutError, Exception):
                    pass

            print(f'  {GREEN}PASS{RESET}')
    except Exception as e:
        print(f'  WebSocket error: {e}')
        raise


async def main():
    print(f'{BOLD}STT Provider Abstraction — Integration Test Client{RESET}')
    print(f'Target: {BASE}')

    # Check server is running
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f'{BASE}/health', timeout=2.0)
    except Exception:
        print(f'\n{YELLOW}Server not running. Start it first:{RESET}')
        print(f'  cd backend && source .venv/bin/activate && python demo_stt_server.py')
        sys.exit(1)

    tests = [
        test_health,
        test_providers,
        test_select,
        test_transcribe_url,
        test_transcribe_url_with_terminology,
        test_transcribe_bytes,
        test_websocket_streaming,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f'  \033[31mFAILED: {e}{RESET}')
            failed += 1

    print(f'\n{BOLD}{"=" * 60}{RESET}')
    print(f'{BOLD}  Results: {GREEN}{passed} passed{RESET}, '
          f'{BOLD}\033[31m{failed} failed{RESET}{BOLD} / {passed + failed} total{RESET}')
    print(f'{BOLD}{"=" * 60}{RESET}')

    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    asyncio.run(main())
