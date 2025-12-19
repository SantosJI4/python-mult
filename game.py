import pygame
import socket
import threading
import json
import math
import time
import random
import asyncio
import queue
try:
  import websockets
except Exception:
  websockets = None

# Configurações do jogo
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60

# Cores
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
GRAY = (60, 60, 60)
LIGHT_GRAY = (200, 200, 200)
GREEN = (0, 200, 0)
YELLOW = (240, 200, 0)

class Weapon:
  def __init__(self, name, fire_rate, bullet_speed, damage, color=(255, 80, 80), size=6):
    self.name = name
    self.fire_rate = fire_rate
    self.bullet_speed = bullet_speed
    self.damage = damage
    self.color = color
    self.size = size

class Bullet:
  def __init__(self, x, y, vx, vy, damage, color, size=6, life=2.0, owner_id=None):
    self.x = x
    self.y = y
    self.vx = vx
    self.vy = vy
    self.damage = damage
    self.color = color
    self.size = size
    self.life = life
    self.alive = True
    self.owner_id = owner_id

  def update(self, dt, walls):
    if not self.alive:
      return
    self.x += self.vx * dt
    self.y += self.vy * dt
    self.life -= dt
    if self.x < 0 or self.x > SCREEN_WIDTH or self.y < 0 or self.y > SCREEN_HEIGHT or self.life <= 0:
      self.alive = False
      return
    rect = pygame.Rect(int(self.x - self.size/2), int(self.y - self.size/2), self.size, self.size)
    for w in walls:
      if rect.colliderect(w):
        self.alive = False
        break

  def draw(self, screen):
    if self.alive:
      pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), self.size)

class Joystick:
  def __init__(self, center, radius=70):
    self.center = center
    self.radius = radius
    self.active = False
    self.pointer = center

  def start(self):
    self.active = True
    self.pointer = self.center

  def stop(self):
    self.active = False
    self.pointer = self.center

  def set_pointer(self, pos):
    dx = pos[0] - self.center[0]
    dy = pos[1] - self.center[1]
    dist = max(1.0, math.hypot(dx, dy))
    if dist > self.radius:
      scale = self.radius / dist
      dx *= scale
      dy *= scale
    self.pointer = (self.center[0] + dx, self.center[1] + dy)

  def direction(self):
    if not self.active:
      return 0.0, 0.0, 0.0
    dx = self.pointer[0] - self.center[0]
    dy = self.pointer[1] - self.center[1]
    mag = math.hypot(dx, dy)
    if mag < 5:
      return 0.0, 0.0, 0.0
    return dx / self.radius, dy / self.radius, mag / self.radius

  def draw(self, screen):
    base_color = (230, 230, 230)
    knob_color = (60, 160, 250)
    pygame.draw.circle(screen, base_color, (int(self.center[0]), int(self.center[1])), self.radius, 2)
    pygame.draw.circle(screen, LIGHT_GRAY, (int(self.center[0]), int(self.center[1])), int(self.radius * 0.6), 1)
    pygame.draw.circle(screen, knob_color, (int(self.pointer[0]), int(self.pointer[1])), 14)

class Player:
  def __init__(self, x, y, color):
    self.x = x
    self.y = y
    self.color = color
    self.speed = 5
    self.rect = pygame.Rect(x, y, 50, 50)
    self.max_hp = 100
    self.hp = 100
    self.alive = True
  
  def move(self, dx, dy):
    self.x += dx * self.speed
    self.y += dy * self.speed
    self.rect.x = int(self.x)
    self.rect.y = int(self.y)
  
  def draw(self, screen):
    pygame.draw.rect(screen, self.color, self.rect)
    # Health bar above player
    bar_w = 50
    bar_h = 6
    pct = max(0, min(1, self.hp / self.max_hp))
    bg = pygame.Rect(self.rect.x, self.rect.y - 10, bar_w, bar_h)
    fg = pygame.Rect(self.rect.x, self.rect.y - 10, int(bar_w * pct), bar_h)
    pygame.draw.rect(screen, LIGHT_GRAY, bg)
    pygame.draw.rect(screen, GREEN if pct > 0.5 else YELLOW if pct > 0.25 else RED, fg)

  def move_towards(self, tx, ty):
    dx = tx - self.x
    dy = ty - self.y
    dist = math.hypot(dx, dy)
    if dist <= 0:
      return False
    step = min(self.speed, dist)
    self.x += (dx / dist) * step
    self.y += (dy / dist) * step
    self.rect.x = int(self.x)
    self.rect.y = int(self.y)
    return True

class GameClient:
  def __init__(self):
    pygame.init()
    self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Jogo Online")
    self.clock = pygame.time.Clock()
    
    self.player = Player(100, 100, BLUE)
    self.other_players = {}
    
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.connected = False
    self.client_id = None
    # Networking mode: 'tcp' or 'ws'
    self.net_mode = 'tcp'  # set to 'ws' to use WebSocket
    self.ws_url = 'ws://localhost:8765'
    self.ws_runner = None
    
    # Controle por clique (click-to-move)
    self.target_pos = None
    # Cursor personalizado
    # No menu, manter cursor visível; no jogo, usar cursor custom.
    pygame.mouse.set_visible(True)
    # Menu state
    self.in_menu = True
    self.host = 'localhost'
    self.port = 12345
    self.name = 'Player'
    self.menu_message = ''
    # Networking throttle
    self.last_pos_send = 0.0
    self.pos_send_interval = 0.12
    # Twin-stick joysticks
    self.move_js = Joystick((80, SCREEN_HEIGHT - 80), radius=70)
    self.aim_js = Joystick((SCREEN_WIDTH - 80, SCREEN_HEIGHT - 80), radius=70)
    # Touch finger ids for mobile
    self.move_fid = None
    self.aim_fid = None
    # Weapons and bullets
    self.weapons = {
      'Pistol': Weapon('Pistol', fire_rate=4.0, bullet_speed=400, damage=20, color=(255, 90, 90), size=6),
      'SMG': Weapon('SMG', fire_rate=10.0, bullet_speed=520, damage=8, color=(255, 160, 80), size=5)
    }
    self.active_weapon = self.weapons['Pistol']
    self.last_shot = 0.0
    self.bullets = []
    # Test walls for cover
    self.walls = [
      pygame.Rect(180, 140, 120, 20),
      pygame.Rect(420, 120, 20, 140),
      pygame.Rect(580, 260, 140, 20),
      pygame.Rect(240, 360, 200, 20),
      pygame.Rect(90, 280, 20, 160),
      pygame.Rect(640, 420, 120, 20)
    ]
    # Menu controls
    self.menu_index = 0  # 0: Conectar, 1: Offline
    # Predefine botões do menu para evitar erros em eventos antes do desenho
    self.btn_connect = pygame.Rect(SCREEN_WIDTH//2 - 120, 220, 240, 50)
    self.btn_offline = pygame.Rect(SCREEN_WIDTH//2 - 120, 290, 240, 50)
    # Death menu state
    self.in_death_menu = False
    self.death_index = 0  # 0: Reviver, 1: Voltar Menu
    # Predefine death menu buttons
    self.btn_revive = pygame.Rect(SCREEN_WIDTH//2 - 140, 270, 280, 50)
    self.btn_back = pygame.Rect(SCREEN_WIDTH//2 - 140, 335, 280, 50)
    # Respawn invulnerability window
    self.invuln_until = 0.0
  
  def connect_to_server(self, host='localhost', port=12345):
    try:
      self.socket.connect((host, port))
      self.connected = True
      threading.Thread(target=self.receive_data, daemon=True).start()
      # Send hello with initial info
      self.send_line({'type': 'hello', 'name': self.name, 'x': self.player.x, 'y': self.player.y})
      return True
    except:
      return False

  class _WSRunner:
    def __init__(self, url, on_message):
      self.url = url
      self.on_message = on_message
      self.loop = None
      self.send_q = None
      self.stop = False
      self.thread = None

    def start(self):
      self.thread = threading.Thread(target=self._run, daemon=True)
      self.thread.start()

    def _run(self):
      asyncio.run(self._run_async())

    async def _run_async(self):
      self.loop = asyncio.get_running_loop()
      self.send_q = asyncio.Queue()
      try:
        async with websockets.connect(self.url, max_size=2**20) as ws:
          recv_task = asyncio.create_task(self._recv_loop(ws))
          send_task = asyncio.create_task(self._send_loop(ws))
          await asyncio.wait([recv_task, send_task], return_when=asyncio.FIRST_COMPLETED)
      except Exception:
        pass

    async def _recv_loop(self, ws):
      try:
        async for line in ws:
          try:
            msg = json.loads(line)
          except Exception:
            continue
          try:
            self.on_message(msg)
          except Exception:
            pass
      except Exception:
        pass

    async def _send_loop(self, ws):
      try:
        while not self.stop:
          obj = await self.send_q.get()
          try:
            await ws.send(json.dumps(obj) + "\n")
          except Exception:
            pass
      except Exception:
        pass

    def send(self, obj):
      if self.loop and self.send_q:
        try:
          self.loop.call_soon_threadsafe(self.send_q.put_nowait, obj)
        except Exception:
          pass

  def connect_to_ws(self, url):
    if websockets is None:
      self.menu_message = 'Biblioteca websockets não instalada.'
      return False
    try:
      # Start WS runner thread
      self.ws_runner = GameClient._WSRunner(url, self.handle_server_msg)
      self.ws_runner.start()
      self.connected = True
      # Send hello over WS
      self.send_line({'type': 'hello', 'name': self.name, 'x': self.player.x, 'y': self.player.y, 'color': self.player.color})
      return True
    except Exception:
      self.connected = False
      return False

  def send_line(self, obj):
    if not self.connected:
      return
    # Route via WS if active
    if self.ws_runner is not None:
      try:
        self.ws_runner.send(obj)
      except Exception:
        pass
      return
    # Fallback to TCP socket
    try:
      line = json.dumps(obj) + "\n"
      self.socket.sendall(line.encode('utf-8'))
    except:
      self.connected = False
  
  def send_player_data(self):
    if self.connected:
      self.send_line({'type': 'pos', 'x': self.player.x, 'y': self.player.y})
  
  def send_shot(self, b):
    if self.connected:
      self.send_line({
        'type': 'shot',
        'owner': self.client_id,
        'x': b.x,
        'y': b.y,
        'vx': b.vx,
        'vy': b.vy,
        'damage': b.damage,
        'size': b.size,
        'color': list(b.color)
      })
  
  def send_hit(self, victim_id, damage):
    if self.connected:
      self.send_line({'type': 'hit', 'victim': victim_id, 'damage': damage})
  
  def disconnect(self):
    try:
      if self.connected:
        self.socket.close()
    except:
      pass
    self.connected = False
    # Recreate socket for potential reconnection
    try:
      self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except:
      pass
  
  def receive_data(self):
    buf = ""
    while self.connected:
      try:
        data = self.socket.recv(4096)
        if not data:
          self.connected = False
          break
        buf += data.decode('utf-8', errors='ignore')
        while '\n' in buf:
          line, buf = buf.split('\n', 1)
          if not line.strip():
            continue
          try:
            msg = json.loads(line)
          except:
            continue
          self.handle_server_msg(msg)
      except:
        self.connected = False
        break

  def handle_server_msg(self, msg):
    try:
      t = msg.get('type')
      if t == 'welcome':
        self.client_id = msg.get('id')
        try:
          if self.client_id in self.other_players:
            del self.other_players[self.client_id]
        except Exception:
          pass
      elif t == 'state':
        players = msg.get('players', {})
        self.update_other_players(players)
      elif t == 'shot':
        owner = msg.get('owner')
        bx = float(msg.get('x', 0))
        by = float(msg.get('y', 0))
        bvx = float(msg.get('vx', 0))
        bvy = float(msg.get('vy', 0))
        dmg = int(msg.get('damage', 10))
        size = int(msg.get('size', 6))
        color = tuple(msg.get('color', [255, 90, 90]))
        if owner is not None and (self.client_id is not None and int(owner) == int(self.client_id)):
          pass
        else:
          self.bullets.append(Bullet(bx, by, bvx, bvy, dmg, color, size=size, owner_id=int(owner)))
      elif t == 'hp':
        pid = int(msg.get('id'))
        hpv = int(msg.get('hp'))
        if self.client_id is not None and pid == self.client_id:
          self.player.hp = hpv
        else:
          op = self.other_players.get(pid)
          if op:
            op.hp = hpv
    except Exception:
      pass

  def update_other_players(self, players):
    # players: {id: {name, x, y, color}}
    # Remove missing
    ids = set(int(k) for k in players.keys())
    for oid in list(self.other_players.keys()):
      if oid not in ids:
        del self.other_players[oid]
    # Add/update
    for k, pdata in players.items():
      try:
        pid = int(k)
      except:
        continue
      if self.client_id is not None and pid == self.client_id:
        # Skip self mirror from server
        continue
      px = float(pdata.get('x', 100))
      py = float(pdata.get('y', 100))
      color = tuple(pdata.get('color', [255, 0, 0]))
      hpv = int(pdata.get('hp', 100))
      mhp = int(pdata.get('max_hp', 100))
      if pid not in self.other_players:
        pnew = Player(int(px), int(py), color)
        pnew.hp = hpv
        pnew.max_hp = mhp
        self.other_players[pid] = pnew
      else:
        p = self.other_players[pid]
        p.x = px
        p.y = py
        p.rect.x = int(px)
        p.rect.y = int(py)
        # Update hp if provided in state
        p.max_hp = mhp
        p.hp = hpv

  def random_spawn(self):
    for _ in range(100):
      x = random.randint(20, SCREEN_WIDTH - 70)
      y = random.randint(20, SCREEN_HEIGHT - 70)
      rect = pygame.Rect(x, y, 50, 50)
      if not any(rect.colliderect(w) for w in self.walls):
        return x, y
    return 100, 100

  def revive_player(self):
    # Full heal and brief invulnerability
    self.player.hp = self.player.max_hp
    self.player.alive = True
    sx, sy = self.random_spawn()
    self.player.x = sx
    self.player.y = sy
    self.player.rect.x = int(sx)
    self.player.rect.y = int(sy)
    self.in_death_menu = False
    # Clear existing bullets to avoid instant damage on spawn
    self.bullets = []
    # 1.5s invulnerability after revive
    self.invuln_until = time.time() + 1.5
    # Clear joysticks
    self.move_js.stop()
    self.aim_js.stop()
    # Notify server of revive (authoritative hp reset)
    if self.connected:
      try:
        self.send_line({'type': 'revive'})
      except Exception:
        pass
    # Notify server of new position
    self.send_player_data()

  def create_new_player(self):
    # Randomize color and name
    new_color = (random.randint(60, 240), random.randint(60, 240), random.randint(60, 240))
    self.name = f"Player{random.randint(100, 999)}"
    sx, sy = self.random_spawn()
    self.player = Player(sx, sy, new_color)
    self.other_players = {}
    # Reset bullets and joysticks
    self.bullets = []
    self.move_js.stop()
    self.aim_js.stop()
    self.in_death_menu = False
    # If connected, reconnect to create a fresh identity on server
    if self.connected:
      self.disconnect()
      ok = self.connect_to_server(self.host, self.port)
      if not ok:
        # Fall back to offline
        self.connected = False
  
  def handle_input(self):
    if self.in_death_menu or not self.player.alive:
      return
    # Twin-stick movement and aiming/shooting
    dx, dy, mag = self.move_js.direction()
    if mag > 0:
      self.player.move(dx, dy)

    ax, ay, amag = self.aim_js.direction()
    now = time.time()
    if amag > 0.2:
      if now - self.last_shot >= (1.0 / self.active_weapon.fire_rate):
        dir_mag = math.hypot(ax, ay)
        if dir_mag > 0:
          vx = (ax / dir_mag) * self.active_weapon.bullet_speed
          vy = (ay / dir_mag) * self.active_weapon.bullet_speed
          self.bullets.append(Bullet(self.player.x + 25, self.player.y + 25, vx, vy,
                                     self.active_weapon.damage, self.active_weapon.color, self.active_weapon.size,
                                     owner_id=self.client_id))
          # Send shot to server for other clients
          self.send_shot(self.bullets[-1])
          self.last_shot = now

    if now - self.last_pos_send >= self.pos_send_interval:
      self.send_player_data()
      self.last_pos_send = now

  def draw_cursor(self, screen):
    # Desenhar um cursor customizado (cruz) na posição do mouse
    mx, my = pygame.mouse.get_pos()
    color = RED
    size = 10
    thickness = 2
    pygame.draw.line(screen, color, (mx - size, my), (mx + size, my), thickness)
    pygame.draw.line(screen, color, (mx, my - size), (mx, my + size), thickness)

  def draw_aim_feedback(self, screen):
    if self.aim_js.active:
      # draw a direction ray from player center based on joystick vector
      cx = int(self.player.rect.x + self.player.rect.w/2)
      cy = int(self.player.rect.y + self.player.rect.h/2)
      ax, ay, amag = self.aim_js.direction()
      if amag > 0.05:
        dir_mag = math.hypot(ax, ay)
        if dir_mag > 0:
          lx = cx + int((ax / dir_mag) * 140)
          ly = cy + int((ay / dir_mag) * 140)
          pygame.draw.line(screen, (255, 120, 120), (cx, cy), (lx, ly), 2)
          pygame.draw.circle(screen, (255, 120, 120), (lx, ly), 5, 1)
  
  def run(self):
    running = True

    while running:
      for event in pygame.event.get():
        if event.type == pygame.QUIT:
          running = False
        elif self.in_menu and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
          mx, my = event.pos
          # Simple buttons
          if self.btn_connect.collidepoint(mx, my):
            ok = False
            if self.net_mode == 'ws':
              ok = self.connect_to_ws(self.ws_url)
            else:
              ok = self.connect_to_server(self.host, self.port)
            if ok:
              self.in_menu = False
              pygame.mouse.set_visible(False)
              self.menu_message = ''
            else:
              self.menu_message = 'Falha ao conectar ao servidor.'
          elif self.btn_offline.collidepoint(mx, my):
            self.in_menu = False
            pygame.mouse.set_visible(False)
        elif self.in_menu and event.type == pygame.KEYDOWN:
          if event.key in (pygame.K_UP, pygame.K_w):
            self.menu_index = max(0, self.menu_index - 1)
          elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.menu_index = min(1, self.menu_index + 1)
          elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.menu_index == 0:
              ok = False
              if self.net_mode == 'ws':
                ok = self.connect_to_ws(self.ws_url)
              else:
                ok = self.connect_to_server(self.host, self.port)
              if ok:
                self.in_menu = False
                pygame.mouse.set_visible(False)
                self.menu_message = ''
              else:
                self.menu_message = 'Falha ao conectar ao servidor.'
            else:
              self.in_menu = False
              pygame.mouse.set_visible(False)
          elif event.key == pygame.K_ESCAPE:
            running = False
        elif not self.in_menu and not self.in_death_menu and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
          # Left click: prefer movement stick if inside its area, otherwise aim stick
          if math.hypot(event.pos[0]-self.move_js.center[0], event.pos[1]-self.move_js.center[1]) <= self.move_js.radius:
            self.move_js.start()
            self.move_js.set_pointer(event.pos)
          elif math.hypot(event.pos[0]-self.aim_js.center[0], event.pos[1]-self.aim_js.center[1]) <= self.aim_js.radius:
            self.aim_js.start()
            self.aim_js.set_pointer(event.pos)
        elif not self.in_menu and not self.in_death_menu and event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
          # Start aim joystick if inside its area
          if math.hypot(event.pos[0]-self.aim_js.center[0], event.pos[1]-self.aim_js.center[1]) <= self.aim_js.radius:
            self.aim_js.start()
            self.aim_js.set_pointer(event.pos)
        elif not self.in_menu and not self.in_death_menu and event.type == pygame.MOUSEMOTION:
          if self.move_js.active:
            self.move_js.set_pointer(event.pos)
          if self.aim_js.active:
            self.aim_js.set_pointer(event.pos)
        elif not self.in_menu and not self.in_death_menu and event.type == pygame.MOUSEBUTTONUP:
          if event.button == 1:
            # Stop whichever was controlled by left click
            if self.move_js.active:
              self.move_js.stop()
            elif self.aim_js.active:
              self.aim_js.stop()
          elif event.button == 3:
            self.aim_js.stop()
        # Touch controls
        elif not self.in_menu and not self.in_death_menu and event.type == pygame.FINGERDOWN:
          fx = int(event.x * SCREEN_WIDTH)
          fy = int(event.y * SCREEN_HEIGHT)
          if self.move_fid is None and math.hypot(fx-self.move_js.center[0], fy-self.move_js.center[1]) <= self.move_js.radius:
            self.move_fid = event.finger_id
            self.move_js.start()
            self.move_js.set_pointer((fx, fy))
          elif self.aim_fid is None and math.hypot(fx-self.aim_js.center[0], fy-self.aim_js.center[1]) <= self.aim_js.radius:
            self.aim_fid = event.finger_id
            self.aim_js.start()
            self.aim_js.set_pointer((fx, fy))
        elif not self.in_menu and not self.in_death_menu and event.type == pygame.FINGERMOTION:
          fx = int(event.x * SCREEN_WIDTH)
          fy = int(event.y * SCREEN_HEIGHT)
          if self.move_js.active and event.finger_id == self.move_fid:
            self.move_js.set_pointer((fx, fy))
          if self.aim_js.active and event.finger_id == self.aim_fid:
            self.aim_js.set_pointer((fx, fy))
        elif not self.in_menu and not self.in_death_menu and event.type == pygame.FINGERUP:
          if event.finger_id == self.move_fid:
            self.move_fid = None
            self.move_js.stop()
          if event.finger_id == self.aim_fid:
            self.aim_fid = None
            self.aim_js.stop()
        # Death menu interactions
        elif not self.in_menu and self.in_death_menu and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
          mx, my = event.pos
          if self.btn_revive.collidepoint(mx, my):
            self.revive_player()
          elif self.btn_back.collidepoint(mx, my):
            # Back to main menu; disconnect if connected
            if self.connected:
              self.disconnect()
            self.in_death_menu = False
            self.in_menu = True
            pygame.mouse.set_visible(True)

      if not self.in_menu:
        self.handle_input()

      # Desenhar tudo
      self.screen.fill(WHITE)

      if self.in_menu:
        self.draw_menu()
      else:
        self.player.draw(self.screen)
        # Desenhar outros jogadores
        for player in self.other_players.values():
          player.draw(self.screen)
        # Desenhar paredes
        for w in self.walls:
          pygame.draw.rect(self.screen, GRAY, w)
        # Atualizar e desenhar balas
        dt = self.clock.get_time() / 1000.0
        for b in list(self.bullets):
          b.update(dt, self.walls)
          # Bullet vs player collisions (local prototype, no server changes)
          if b.alive:
            brect = pygame.Rect(int(b.x - b.size/2), int(b.y - b.size/2), b.size, b.size)
            # Our bullets can damage other players
            if b.owner_id == self.client_id:
              for pid, op in list(self.other_players.items()):
                if brect.colliderect(op.rect):
                  op.hp = max(0, op.hp - b.damage)
                  # Report hit to server so all clients sync hp
                  try:
                    self.send_hit(pid, b.damage)
                  except Exception:
                    pass
                  b.alive = False
                  break
            # Enemy bullets (future sync) can damage us
            elif b.owner_id is not None and b.owner_id != self.client_id:
              if brect.colliderect(self.player.rect):
                # Respect respawn invulnerability
                if time.time() >= self.invuln_until:
                  self.player.hp = max(0, self.player.hp - b.damage)
                b.alive = False
          if not b.alive:
            try:
              self.bullets.remove(b)
            except ValueError:
              pass
          else:
            b.draw(self.screen)
        # Check death
        if self.player.alive and self.player.hp <= 0:
          self.player.alive = False
          self.in_death_menu = True
          # Stop joysticks
          self.move_js.stop()
          self.aim_js.stop()
        # Desenhar joysticks
        if not self.in_death_menu:
          self.move_js.draw(self.screen)
          self.aim_js.draw(self.screen)
        # Aim feedback (trajectory)
        if not self.in_death_menu:
          self.draw_aim_feedback(self.screen)
        # Desenhar cursor personalizado
        self.draw_cursor(self.screen)
        # Debug info
        self.draw_debug()
        # Death menu overlay
        if self.in_death_menu:
          self.draw_death_menu()

      pygame.display.flip()
      self.clock.tick(FPS)

    pygame.quit()
    if self.connected:
      self.socket.close()

  def draw_menu(self):
    font = pygame.font.SysFont(None, 36)
    title = font.render('Fazenda Comunitária', True, BLACK)
    self.screen.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 100))
    # Buttons
    # Destacar opção selecionada pelo teclado
    color_connect = (180, 240, 180) if self.menu_index == 0 else (200, 230, 200)
    color_offline = (180, 180, 180) if self.menu_index == 1 else (220, 220, 220)
    pygame.draw.rect(self.screen, color_connect, self.btn_connect, border_radius=6)
    pygame.draw.rect(self.screen, color_offline, self.btn_offline, border_radius=6)
    # Bordas para foco
    border_color = (60, 60, 60)
    if self.menu_index == 0:
      pygame.draw.rect(self.screen, border_color, self.btn_connect, 2, border_radius=6)
    else:
      pygame.draw.rect(self.screen, border_color, self.btn_offline, 2, border_radius=6)
    txt1 = font.render('Conectar', True, BLACK)
    txt2 = font.render('Offline', True, BLACK)
    self.screen.blit(txt1, (self.btn_connect.centerx - txt1.get_width()//2, self.btn_connect.centery - txt1.get_height()//2))
    self.screen.blit(txt2, (self.btn_offline.centerx - txt2.get_width()//2, self.btn_offline.centery - txt2.get_height()//2))
    # Dica de controles
    hint = font.render('Use ↑/↓ e Enter', True, BLACK)
    self.screen.blit(hint, (SCREEN_WIDTH//2 - hint.get_width()//2, 360))
    # Status de conexão
    if self.menu_message:
      msg = font.render(self.menu_message, True, (180, 40, 40))
      self.screen.blit(msg, (SCREEN_WIDTH//2 - msg.get_width()//2, 410))

  def draw_debug(self):
    font = pygame.font.SysFont(None, 24)
    cid = self.client_id if self.client_id is not None else '-'
    status = "DEAD" if not self.player.alive else "ALIVE"
    txt = font.render(f"ID: {cid} | {status} | Outros: {len(self.other_players)}", True, BLACK)
    self.screen.blit(txt, (10, 10))

  def draw_death_menu(self):
    # Translucent overlay
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((20, 20, 20, 160))
    self.screen.blit(overlay, (0, 0))
    font = pygame.font.SysFont(None, 42)
    title = font.render('Você morreu!', True, (250, 80, 80))
    self.screen.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 160))
    # Buttons
    pygame.draw.rect(self.screen, (210, 240, 210), self.btn_revive, border_radius=8)
    pygame.draw.rect(self.screen, (240, 210, 210), self.btn_back, border_radius=8)
    txt1 = font.render('Reviver', True, BLACK)
    txt3 = font.render('Voltar ao menu', True, BLACK)
    self.screen.blit(txt1, (self.btn_revive.centerx - txt1.get_width()//2, self.btn_revive.centery - txt1.get_height()//2))
    self.screen.blit(txt3, (self.btn_back.centerx - txt3.get_width()//2, self.btn_back.centery - txt3.get_height()//2))

if __name__ == "__main__":
  game = GameClient()
  # Abrir menu inicial; conexão é feita via menu
  game.run()