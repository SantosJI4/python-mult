import asyncio
import json
import time
import random
import os
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# CORS para aceitar requisições de qualquer origem
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', 8000))  # SquaredCloud fornece PORT via variável

next_id = 1
clients = {}   # id -> websocket
players = {}   # id -> {name, x, y, color, hp, max_hp, invuln_until}


@app.get("/")
async def root():
    return {"status": "ok", "message": "Game server online"}


@app.get("/health")
async def health():
    return {"players": len(players), "clients": len(clients)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global next_id
    await websocket.accept()
    cid = None
    try:
        while True:
            line = await websocket.receive_text()
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            t = msg.get('type')
            if t == 'hello':
                cid = next_id
                next_id += 1
                clients[cid] = websocket
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
                await websocket.send_json({'type': 'welcome', 'id': cid})

            elif t == 'pos' and cid is not None:
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
                    vp = players.get(victim)
                    if vp:
                        if time.time() >= vp.get('invuln_until', 0):
                            vp['hp'] = max(0, vp.get('hp', 100) - dmg)
                        hp_msg = {'type': 'hp', 'id': victim, 'hp': vp['hp']}
                    await broadcast(hp_msg)

            elif t == 'revive' and cid is not None:
                p = players.get(cid)
                if p:
                    p['hp'] = p.get('max_hp', 100)
                    p['invuln_until'] = time.time() + 1.5
                    hp_msg = {'type': 'hp', 'id': cid, 'hp': p['hp']}
                await broadcast(hp_msg)

    except Exception:
        pass
    finally:
        if cid in clients:
            del clients[cid]
        if cid in players:
            del players[cid]


async def broadcast(obj):
    if not clients:
        return
    bad_clients = []
    for cid, ws in list(clients.items()):
        try:
            await ws.send_json(obj)
        except Exception:
            bad_clients.append(cid)
    for cid in bad_clients:
        if cid in clients:
            del clients[cid]


async def broadcast_loop():
    while True:
        await asyncio.sleep(0.05)
        state = {'type': 'state', 'players': players}
        await broadcast(state)


@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcast_loop())


if __name__ == '__main__':
    print(f"Starting server on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
