import asyncio
import json
import time
import random
import websockets

HOST = '0.0.0.0'
PORT = 80
BROADCAST_FPS = 20  # 20 updates per second

next_id = 1
clients = {}   # id -> websocket
players = {}   # id -> {name, x, y, color, hp, max_hp, invuln_until}
lock = asyncio.Lock()


async def send_line(ws, obj):
    try:
        await ws.send(json.dumps(obj) + "\n")
    except Exception:
        pass


async def broadcast(obj):
    if not clients:
        return
    to_send = json.dumps(obj) + "\n"
    coros = []
    for ws in list(clients.values()):
        coros.append(ws.send(to_send))
    # ignore individual send errors
    try:
        await asyncio.gather(*coros, return_exceptions=True)
    except Exception:
        pass


async def handle_client(ws):
    global next_id
    cid = None
    try:
        async for line in ws:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            t = msg.get('type')
            if t == 'hello':
                async with lock:
                    cid = next_id
                    next_id += 1
                    clients[cid] = ws
                    color = [random.randint(50, 255) for _ in range(3)]
                    players[cid] = {
                        'name': msg.get('name', f'Player{cid}'),
                        'x': float(msg.get('x', 100)),
                        'y': float(msg.get('y', 100)),
                        'color': msg.get('color', color),
                        'hp': 100,
                        'max_hp': 100,
                        'invuln_until': 0.0,
                    }
                await send_line(ws, {'type': 'welcome', 'id': cid})

            elif t == 'pos' and cid is not None:
                async with lock:
                    p = players.get(cid)
                    if p:
                        p['x'] = float(msg.get('x', p['x']))
                        p['y'] = float(msg.get('y', p['y']))

            elif t == 'shot' and cid is not None:
                shot = {
                    'type': 'shot',
                    'owner': cid,
                    'x': float(msg.get('x', 0)),
                    'y': float(msg.get('y', 0)),
                    'vx': float(msg.get('vx', 0)),
                    'vy': float(msg.get('vy', 0)),
                    'damage': int(msg.get('damage', 10)),
                    'size': int(msg.get('size', 6)),
                    'color': msg.get('color', [255, 90, 90])
                }
                await broadcast(shot)

            elif t == 'hit' and cid is not None:
                victim = int(msg.get('victim')) if 'victim' in msg else None
                dmg = int(msg.get('damage', 0))
                if victim is not None:
                    async with lock:
                        vp = players.get(victim)
                        if vp:
                            # Ignore damage if invulnerable
                            if time.time() >= vp.get('invuln_until', 0):
                                vp['hp'] = max(0, vp.get('hp', 100) - dmg)
                            hp_msg = {'type': 'hp', 'id': victim, 'hp': vp['hp']}
                    await broadcast(hp_msg)

            elif t == 'revive' and cid is not None:
                async with lock:
                    p = players.get(cid)
                    if p:
                        p['hp'] = p.get('max_hp', 100)
                        p['invuln_until'] = time.time() + 1.5
                        hp_msg = {'type': 'hp', 'id': cid, 'hp': p['hp']}
                await broadcast(hp_msg)

    except Exception:
        pass
    finally:
        async with lock:
            if cid in clients:
                try:
                    del clients[cid]
                except Exception:
                    pass
            if cid in players:
                try:
                    del players[cid]
                except Exception:
                    pass
        try:
            await ws.close()
        except Exception:
            pass


async def broadcast_loop():
    interval = 1.0 / BROADCAST_FPS
    while True:
        await asyncio.sleep(interval)
        async with lock:
            state = {'type': 'state', 'players': players}
        await broadcast(state)


async def start_server(host=HOST, port=PORT):
    async with websockets.serve(handle_client, host, port, max_size=2**20):
        print(f"WebSocket server listening on ws://{host}:{port}")
        await broadcast_loop()


if __name__ == '__main__':
    asyncio.run(start_server())
