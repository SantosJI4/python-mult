import socket
import threading
import json
import time
import random

HOST = '0.0.0.0'
PORT = 12345
BROADCAST_FPS = 20  # 20 updates per second

next_id = 1
clients = {}   # id -> socket
players = {}   # id -> {name, x, y, color, hp, max_hp}
lock = threading.Lock()


def send_line(sock, obj):
    try:
        line = json.dumps(obj) + "\n"
        sock.sendall(line.encode('utf-8'))
    except Exception:
        pass


def handle_client(sock, addr):
    global next_id
    sock.settimeout(15)
    cid = None
    buf = ""
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            buf += data.decode('utf-8', errors='ignore')
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                t = msg.get('type')
                if t == 'hello':
                    with lock:
                        cid = next_id
                        next_id += 1
                        clients[cid] = sock
                        color = [random.randint(50, 255) for _ in range(3)]
                        players[cid] = {
                            'name': msg.get('name', f'Player{cid}'),
                            'x': float(msg.get('x', 100)),
                            'y': float(msg.get('y', 100)),
                            'color': color,
                            'hp': 100,
                            'max_hp': 100,
                            'invuln_until': 0.0,
                        }
                    send_line(sock, {'type': 'welcome', 'id': cid})
                elif t == 'pos' and cid is not None:
                    with lock:
                        p = players.get(cid)
                        if p:
                            p['x'] = float(msg.get('x', p['x']))
                            p['y'] = float(msg.get('y', p['y']))
                elif t == 'shot' and cid is not None:
                    # Broadcast shot event to all clients
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
                    with lock:
                        targets = list(clients.values())
                    for s in targets:
                        send_line(s, shot)
                elif t == 'hit' and cid is not None:
                    # Reduce victim hp and broadcast hp update
                    victim = int(msg.get('victim')) if 'victim' in msg else None
                    dmg = int(msg.get('damage', 0))
                    if victim is not None:
                        with lock:
                            vp = players.get(victim)
                            if vp:
                                # Ignore damage if victim is invulnerable (e.g., just revived)
                                if time.time() >= vp.get('invuln_until', 0):
                                    vp['hp'] = max(0, vp.get('hp', 100) - dmg)
                                hp_msg = {'type': 'hp', 'id': victim, 'hp': vp['hp']}
                                targets = list(clients.values())
                        for s in targets:
                            send_line(s, hp_msg)
                elif t == 'revive' and cid is not None:
                    # Restore player's hp to max and broadcast hp update
                    with lock:
                        p = players.get(cid)
                        if p:
                            p['hp'] = p.get('max_hp', 100)
                            # Set short invulnerability window
                            p['invuln_until'] = time.time() + 1.5
                            hp_msg = {'type': 'hp', 'id': cid, 'hp': p['hp']}
                            targets = list(clients.values())
                    for s in targets:
                        send_line(s, hp_msg)
                elif t == 'ping':
                    send_line(sock, {'type': 'pong'})
    except Exception:
        pass
    finally:
        with lock:
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
            sock.close()
        except Exception:
            pass


def broadcast_loop():
    interval = 1.0 / BROADCAST_FPS
    while True:
        time.sleep(interval)
        with lock:
            state = {
                'type': 'state',
                'players': players
            }
            targets = list(clients.values())
        for s in targets:
            send_line(s, state)


def start_server(host=HOST, port=PORT):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(64)
    print(f"Server listening on {host}:{port}")

    threading.Thread(target=broadcast_loop, daemon=True).start()

    try:
        while True:
            sock, addr = srv.accept()
            threading.Thread(target=handle_client, args=(sock, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        try:
            srv.close()
        except Exception:
            pass


if __name__ == '__main__':
    start_server()
