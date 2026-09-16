import math
import random
import os

# Prevent SDL2 from synthesizing a MOUSEBUTTONDOWN for every touch on Android.
# Without this, a single tap fires both FINGERDOWN and MOUSEBUTTONDOWN,
# double-triggering menu/shop actions (e.g. a shop purchase running twice).
os.environ["SDL_TOUCH_MOUSE_EVENTS"] = "0"
os.environ["SDL_MOUSE_TOUCH_EVENTS"] = "0"

import pygame

# Survivor Rush V5
# Controls: WASD / Arrow keys / on-screen joystick
# Goal: survive, level up, defeat the boss, and collect coins.

pygame.init()
try:
    pygame.mixer.pre_init(44100, -16, 1, 512)
    pygame.mixer.init()
except Exception:
    pass

# ---------- adaptive full-screen mobile resolution ----------
# Keep the existing game coordinate system, but widen the logical viewport
# to exactly match the real device aspect ratio. This avoids letterbox bars
# while preserving proportions. The final logical frame is scaled uniformly
# to the display height.
real_screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
DISPLAY_W, DISPLAY_H = real_screen.get_size()
if DISPLAY_W <= 0 or DISPLAY_H <= 0:
    DISPLAY_W, DISPLAY_H = 1100, 700

HEIGHT = 700
DISPLAY_ASPECT = DISPLAY_W / max(1, DISPLAY_H)
WIDTH = max(1000, round(HEIGHT * DISPLAY_ASPECT))

WORLD_W, WORLD_H = 3200, 2200
FPS = 60
camera = pygame.Vector2(0, 0)

_scale = DISPLAY_H / HEIGHT
_scaled_size = (DISPLAY_W, DISPLAY_H)
_blit_pos = (0, 0)

def to_logical(px, py):
    """Convert real-screen pixel coordinates into logical game coordinates."""
    return px / _scale, py / _scale

screen = pygame.Surface((WIDTH, HEIGHT))
pygame.display.set_caption("Survivor Rush V6")
clock = pygame.time.Clock()

FONT = pygame.font.SysFont("arial", 22, bold=True)
SMALL = pygame.font.SysFont("arial", 17, bold=True)
BIG = pygame.font.SysFont("arial", 46, bold=True)
TITLE = pygame.font.SysFont("arial", 72, bold=True)

# ---------- worlds ----------
# Distinct stages the game cycles through: each has its own map size, color
# palette, and enemy-kind bias. Round 1 uses WORLDS[0], round 2 uses
# WORLDS[1], and so on, wrapping back around after the last one.
WORLDS = [
    {
        "name": "Neon Grid",
        "size": (3200, 2200),
        "bg": (6,9,17), "grid": (14,20,33), "border": (55,75,100),
        "rock": (24,33,47), "rock_hl": (45,58,73),
        "crystal": (25,70,105), "crystal_edge": (65,155,195), "crystal_core": (130,230,250),
        "ruin": (22,29,42), "ruin_edge": (48,62,80), "ruin_core": (10,15,24),
        "kinds": {"normal": 0, "fast": 0, "tank": 0},
    },
    {
        "name": "Crimson Wastes",
        "size": (3600, 2000),
        "bg": (18,6,8), "grid": (35,12,15), "border": (120,40,45),
        "rock": (45,18,20), "rock_hl": (75,30,30),
        "crystal": (90,20,25), "crystal_edge": (200,70,60), "crystal_core": (255,150,110),
        "ruin": (40,15,15), "ruin_edge": (85,35,30), "ruin_core": (18,8,8),
        "kinds": {"normal": 0, "fast": 1, "tank": 3},
    },
    {
        "name": "Frozen Expanse",
        "size": (2800, 2400),
        "bg": (8,14,22), "grid": (18,32,45), "border": (110,170,210),
        "rock": (30,45,60), "rock_hl": (55,75,95),
        "crystal": (40,90,120), "crystal_edge": (140,220,240), "crystal_core": (220,250,255),
        "ruin": (25,38,50), "ruin_edge": (60,95,120), "ruin_core": (12,20,28),
        "kinds": {"normal": -1, "fast": 4, "tank": 0},
    },
    {
        "name": "Toxic Swamp",
        "size": (3400, 2300),
        "bg": (8,16,8), "grid": (16,32,14), "border": (70,140,50),
        "rock": (22,38,18), "rock_hl": (40,65,32),
        "crystal": (30,80,25), "crystal_edge": (110,210,70), "crystal_core": (200,255,150),
        "ruin": (20,32,16), "ruin_edge": (48,80,35), "ruin_core": (10,16,8),
        "kinds": {"normal": 1, "fast": 1, "tank": 1},
    },
    {
        "name": "Void Sector",
        "size": (4000, 2600),
        "bg": (10,6,20), "grid": (28,15,45), "border": (140,70,200),
        "rock": (35,20,50), "rock_hl": (60,35,80),
        "crystal": (60,25,95), "crystal_edge": (170,90,230), "crystal_core": (230,190,255),
        "ruin": (28,16,42), "ruin_edge": (75,40,110), "ruin_core": (14,8,20),
        "kinds": {"normal": -1, "fast": 2, "tank": 4},
    },
]
WORLD_THEME = WORLDS[0]

def apply_world_theme(rn):
    """Sets the world size/palette/enemy-mix for the given round number.
    Worlds cycle in sequence: round 1 -> WORLDS[0], round 2 -> WORLDS[1], ..."""
    global WORLD_W, WORLD_H, WORLD_THEME
    WORLD_THEME = WORLDS[(rn-1) % len(WORLDS)]
    WORLD_W, WORLD_H = WORLD_THEME["size"]

# Maximum number of enemies alive at one time.
MAX_ENEMIES = 12
PLAYER_FIRE_RANGE = 750.0
ROUND_LENGTH = 60.0
ROUND_BOSS_TIME = 50.0
BOSS_GUARD_RADIUS = 360.0
PORTAL_RADIUS = 48.0

# ---------- sound ----------
def tone(freq, duration=0.07, volume=0.20):
    try:
        sample_rate = 44100
        n = int(sample_rate * duration)
        buf = bytearray()
        for i in range(n):
            t = i / sample_rate
            env = min(1, i / (n * .08)) * max(0, 1 - i / n)
            v = int(32767 * volume * env * math.sin(2 * math.pi * freq * t))
            buf += int(v).to_bytes(2, "little", signed=True)
        return pygame.mixer.Sound(buffer=bytes(buf))
    except Exception:
        return None

S_SHOOT = tone(720, .035, .10)
S_HIT = tone(130, .055, .13)
S_COIN = tone(1050, .08, .16)
S_LEVEL = tone(520, .22, .16)
S_BOSS = tone(75, .65, .22)
S_DASH = tone(240, .12, .15)
S_WIN = tone(900, .5, .18)
S_HEAL = tone(880, .16, .18)

def play(s):
    if s:
        s.play()

# ---------- helpers ----------
def clamp(v, a, b):
    return max(a, min(b, v))

def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def text(msg, pos, color=(240,240,245), font=FONT, center=False):
    img = font.render(str(msg), True, color)
    r = img.get_rect()
    if center:
        r.center = pos
    else:
        r.topleft = pos
    screen.blit(img, r)

def world_to_screen(x, y):
    return x - camera.x, y - camera.y + 80

def draw_heart(cx, cy, size, color, outline=None):
    points = []
    for t in range(0, 360, 15):
        a = math.radians(t)
        x = 16 * math.sin(a) ** 3
        y = -(13*math.cos(a) - 5*math.cos(2*a) - 2*math.cos(3*a) - math.cos(4*a))
        points.append((cx + x*size/16, cy + y*size/16))
    pygame.draw.polygon(screen, color, points)
    if outline:
        pygame.draw.polygon(screen, outline, points, 2)

# Cache glow surfaces by (radius, color, alpha) instead of rebuilding a
# fresh SRCALPHA surface with 5 blended circles every single call, every
# frame. This was the main source of frame-rate dips (and therefore the
# perceived player "slowdown", since dt is capped and can't compensate for
# slow frames) -- it got worse near the boss because the boss and portal
# both draw large glow radii every frame once the boss spawns, on top of
# every enemy's own glow.
_glow_cache = {}

def circle_glow(pos, radius, color, alpha=45):
    r = max(1, int(radius))
    key = (r, color, alpha)
    surf = _glow_cache.get(key)
    if surf is None:
        surf = pygame.Surface((r*4, r*4), pygame.SRCALPHA)
        for k in range(5, 0, -1):
            rr = int(r * (k / 3))
            a = max(1, alpha // k)
            pygame.draw.circle(surf, (*color, a), (r*2, r*2), rr)
        _glow_cache[key] = surf
    sx, sy = world_to_screen(pos[0], pos[1])
    screen.blit(surf, (sx-r*2, sy-r*2))

# ---------- particles ----------
particles = []
floating = []

def burst(x, y, color, amount=10, speed=100):
    for _ in range(amount):
        ang = random.random() * math.tau
        sp = random.uniform(speed*.35, speed)
        particles.append({
            "x": x, "y": y,
            "vx": math.cos(ang)*sp, "vy": math.sin(ang)*sp,
            "life": random.uniform(.3,.7),
            "max": .7, "color": color,
            "size": random.randint(2,5)
        })

def float_text(msg, x, y, color=(255,230,100)):
    floating.append([msg, x, y, 1.0, color])

# ---------- player ----------
class Player:
    def __init__(self):
        self.x, self.y = WORLD_W/2, WORLD_H/2
        self.radius = 22
        self.speed = 260
        self.hp = 100
        self.maxhp = 100
        self.damage = 18
        self.fire_rate = .16
        self.fire_timer = 0
        self.bullet_speed = 650
        self.multishot = 1
        self.xp = 0
        self.level = 1
        self.next_xp = 60
        self.coins = 0
        self.lives = 1
        self.invuln = 0
        self.dash_cd = 0
        self.facing = pygame.Vector2(1,0)
        self.shield = 0
        self.regen = 0
        self.vampire = 0
        self.lightning = 0
        self.fire = 0

    def update(self, dt, keys, joy):
        v = pygame.Vector2(0,0)
        if keys[pygame.K_a] or keys[pygame.K_LEFT]: v.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: v.x += 1
        if keys[pygame.K_w] or keys[pygame.K_UP]: v.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]: v.y += 1

        if joy.length() > .18:
            v += joy

        if v.length_squared():
            v = v.normalize()
            self.facing = v
            self.x += v.x * self.speed * dt
            self.y += v.y * self.speed * dt

        self.x = clamp(self.x, 35, WORLD_W-35)
        self.y = clamp(self.y, 35, WORLD_H-35)

        self.fire_timer -= dt
        self.invuln = max(0, self.invuln-dt)
        self.dash_cd = max(0, self.dash_cd-dt)

        if self.regen:
            self.hp = min(self.maxhp, self.hp + self.regen*dt)

    def dash(self):
        if self.dash_cd > 0:
            return
        d = self.facing if self.facing.length_squared() else pygame.Vector2(1,0)
        self.x = clamp(self.x + d.x*130, 35, WORLD_W-35)
        self.y = clamp(self.y + d.y*130, 35, WORLD_H-35)
        self.invuln = .35
        self.dash_cd = 3.0
        burst(self.x, self.y, (90,210,255), 18, 180)
        play(S_DASH)

    def shoot(self):
        # Manual aim only: bullets travel in the direction the player is facing.
        # No enemy targeting or automatic aim correction.
        if self.fire_timer > 0:
            return
        self.fire_timer = self.fire_rate

        # self.facing is a pygame.Vector2, not an angle.
        # Copy and normalize it so the bullet gets a fixed direction.
        direction = pygame.Vector2(self.facing)
        if direction.length_squared() == 0:
            direction = pygame.Vector2(1, 0)
        else:
            direction = direction.normalize()

        spawn_distance = 28
        spread_deg = 9  # angle between multishot bullets
        count = max(1, self.multishot)
        start_angle = -spread_deg * (count - 1) / 2

        for i in range(count):
            angle = math.radians(start_angle + i * spread_deg)
            cs, sn = math.cos(angle), math.sin(angle)
            dx = direction.x * cs - direction.y * sn
            dy = direction.x * sn + direction.y * cs

            bx = self.x + dx * spawn_distance
            by = self.y + dy * spawn_distance

            bullets.append({
                "x": bx, "y": by,
                "dx": dx, "dy": dy,
                "vx": dx * self.bullet_speed, "vy": dy * self.bullet_speed,
                "life": PLAYER_FIRE_RANGE / self.bullet_speed + 0.15,
                "damage": self.damage,
            })

        play(S_SHOOT)

    def draw(self):
        sx,sy=world_to_screen(self.x,self.y); cx,cy=int(sx),int(sy)
        d=pygame.Vector2(self.facing)
        if d.length_squared()==0: d=pygame.Vector2(1,0)
        else: d=d.normalize()
        side=pygame.Vector2(-d.y,d.x)
        if self.shield:
            circle_glow((self.x,self.y),40,(70,190,255),50)
            pygame.draw.circle(screen,(100,220,255),(cx,cy),35,2)
        pygame.draw.ellipse(screen,(5,8,14),(cx-32,cy+17,64,19))
        pts=[pygame.Vector2(cx,cy)+d*30,pygame.Vector2(cx,cy)-d*20+side*20,
             pygame.Vector2(cx,cy)-d*27,pygame.Vector2(cx,cy)-d*20-side*20]
        pygame.draw.polygon(screen,(22,70,125),[(int(p.x),int(p.y)) for p in pts])
        pts2=[pygame.Vector2(cx,cy)+d*24,pygame.Vector2(cx,cy)-d*13+side*14,
              pygame.Vector2(cx,cy)-d*13-side*14]
        pygame.draw.polygon(screen,(55,175,250),[(int(p.x),int(p.y)) for p in pts2])
        pygame.draw.polygon(screen,(190,240,255),[(int(p.x),int(p.y)) for p in pts2],2)
        core=pygame.Vector2(cx,cy)+d*3
        pygame.draw.circle(screen,(10,30,52),(int(core.x),int(core.y)),11)
        pygame.draw.circle(screen,(90,230,255),(int(core.x),int(core.y)),6)
        pygame.draw.circle(screen,(240,255,255),(int(core.x),int(core.y)),2)
        for sign in (-1,1):
            p=pygame.Vector2(cx,cy)-d*17+side*(sign*13)
            pygame.draw.circle(screen,(100,220,255),(int(p.x),int(p.y)),5)
            pygame.draw.line(screen,(255,170,60),(int(p.x),int(p.y)),(int(p.x-d.x*11),int(p.y-d.y*11)),3)
        a=pygame.Vector2(cx,cy)+d*8; z=pygame.Vector2(cx,cy)+d*35
        pygame.draw.line(screen,(240,245,255),(int(a.x),int(a.y)),(int(z.x),int(z.y)),7)
        pygame.draw.line(screen,(65,125,180),(int(a.x),int(a.y)),(int(z.x),int(z.y)),3)
        if self.hp<self.maxhp:
            w=58
            pygame.draw.rect(screen,(25,25,35),(cx-w//2,cy-43,w,6),border_radius=3)
            pygame.draw.rect(screen,(70,225,120),(cx-w//2,cy-43,int(w*max(0,self.hp/self.maxhp)),6),border_radius=3)

class Enemy:
    def __init__(self, kind, t):
        # Spawn enemies around the player in the larger world.
        angle = random.random() * math.tau
        spawn_dist = random.uniform(650, 900)
        self.x = clamp(player.x + math.cos(angle) * spawn_dist, 45, WORLD_W-45)
        self.y = clamp(player.y + math.sin(angle) * spawn_dist, 45, WORLD_H-45)

        self.kind = kind
        scale = 1.0 + (round_no - 1) * 0.22

        if kind == "fast":
            self.radius, self.speed = 14, (150 + t*1.0) * min(scale, 2.0)
            self.hp = self.maxhp = (30 + t*.35) * scale
            self.damage = 9 * scale
            self.fire_rate = max(.55, 1.15 / min(scale, 1.8))
            self.bullet_speed = 290 * min(scale, 1.7)
        elif kind == "tank":
            self.radius, self.speed = 28, (55 + t*.25) * min(scale, 1.55)
            self.hp = self.maxhp = (125 + t*1.5) * scale
            self.damage = 15 * scale
            self.fire_rate = max(.9, 1.8 / min(scale, 1.7))
            self.bullet_speed = 220 * min(scale, 1.6)
        else:
            self.radius, self.speed = 18, (95 + t*.5) * min(scale, 1.75)
            self.hp = self.maxhp = (45 + t*.8) * scale
            self.damage = 11 * scale
            self.fire_rate = max(.7, 1.35 / min(scale, 1.7))
            self.bullet_speed = 250 * min(scale, 1.6)

        self.hit_flash = 0
        self.fire_timer = self.fire_rate
        self.move_timer = random.uniform(.5, 2.0)
        self.strafe_dir = random.choice([-1, 1])
        self.wander_angle = random.random() * math.tau

        # Each enemy guards its own spawn location instead of chasing forever.
        self.anchor_x, self.anchor_y = self.x, self.y
        self.leash_radius = random.uniform(650, 820)
        self.engaged = True

    def update(self, dt, all_enemies=(), allow_fire=True):
        to_player = pygame.Vector2(player.x-self.x, player.y-self.y)
        d = to_player.length()
        anchor_dist = math.hypot(player.x-self.anchor_x, player.y-self.anchor_y)

        # Disengage and head home once the player strays far from this
        # enemy's territory; re-engage if the player wanders back in.
        if self.engaged and anchor_dist > self.leash_radius:
            self.engaged = False
        elif not self.engaged and anchor_dist <= self.leash_radius * 0.7:
            self.engaged = True

        if self.engaged and d > 1:
            # Ranged movement: approach/retreat to a preferred distance,
            # then strafe around the player instead of colliding with them.
            toward = to_player.normalize()
            perpendicular = pygame.Vector2(-toward.y, toward.x) * self.strafe_dir
            preferred = 280 if self.kind == "fast" else (340 if self.kind == "tank" else 310)

            if d < preferred - 45:
                movement = -toward * .75 + perpendicular * .55
            elif d > preferred + 70:
                movement = toward * .70 + perpendicular * .55
            else:
                movement = perpendicular * .95

            self.move_timer -= dt
            if self.move_timer <= 0:
                self.move_timer = random.uniform(.6, 1.8)
                self.strafe_dir *= -1
                self.wander_angle = random.random() * math.tau

            movement += pygame.Vector2(
                math.cos(self.wander_angle),
                math.sin(self.wander_angle)
            ) * .22
        else:
            # Not engaged: head back toward home territory and idle there.
            home_vec = pygame.Vector2(self.anchor_x-self.x, self.anchor_y-self.y)
            if home_vec.length() > 12:
                movement = home_vec.normalize() * .8
            else:
                self.move_timer -= dt
                if self.move_timer <= 0:
                    self.move_timer = random.uniform(1.0, 2.2)
                    self.wander_angle = random.random() * math.tau
                movement = pygame.Vector2(
                    math.cos(self.wander_angle), math.sin(self.wander_angle)
                ) * .3

        # Keep enemies from stacking on top of each other.
        separation = pygame.Vector2(0, 0)
        for other in all_enemies:
            if other is self:
                continue
            gap = self.radius + other.radius + 16
            ox, oy = self.x-other.x, self.y-other.y
            dd = math.hypot(ox, oy)
            if 0 < dd < gap:
                separation += pygame.Vector2(ox, oy) * ((gap-dd)/gap) / dd
        movement += separation * 1.3

        if movement.length_squared():
            movement = movement.normalize()
            self.x += movement.x * self.speed * dt
            self.y += movement.y * self.speed * dt

        self.x = clamp(self.x, 35, WORLD_W-35)
        self.y = clamp(self.y, 35, WORLD_H-35)

        # Fire a projectile toward the player's current position.
        self.fire_timer -= dt
        if self.engaged and allow_fire and self.fire_timer <= 0 and d > 1:
            self.fire_timer = self.fire_rate
            aim = pygame.Vector2(player.x-self.x, player.y-self.y)
            if aim.length_squared():
                aim = aim.normalize()

                # Slight aim error keeps the attacks dodgeable.
                error = random.uniform(-.10, .10)
                cs, sn = math.cos(error), math.sin(error)
                aim = pygame.Vector2(
                    aim.x*cs - aim.y*sn,
                    aim.x*sn + aim.y*cs
                )

                enemy_bullets.append({
                    "x": self.x + aim.x*(self.radius+5),
                    "y": self.y + aim.y*(self.radius+5),
                    "vx": aim.x*self.bullet_speed,
                    "vy": aim.y*self.bullet_speed,
                    "dx": aim.x,
                    "dy": aim.y,
                    "life": 4.0,
                    "damage": self.damage,
                    "kind": self.kind
                })

        self.hit_flash = max(0, self.hit_flash-dt)

    def draw(self):
        sx,sy=world_to_screen(self.x,self.y); cx,cy=int(sx),int(sy)
        if self.kind=="fast": main,light,dark=(240,55,105),(255,160,195),(100,18,60)
        elif self.kind=="tank": main,light,dark=(125,75,190),(215,170,250),(50,25,85)
        else: main,light,dark=(245,145,55),(255,225,135),(110,50,15)
        if self.hit_flash>0: main=light
        circle_glow((self.x,self.y),self.radius+10,main,28)
        aim=pygame.Vector2(player.x-self.x,player.y-self.y)
        if aim.length_squared()==0: aim=pygame.Vector2(1,0)
        else: aim=aim.normalize()
        side=pygame.Vector2(-aim.y,aim.x)
        if self.kind=="fast":
            p=[pygame.Vector2(cx,cy)+aim*(self.radius+6),
               pygame.Vector2(cx,cy)-aim*self.radius+side*self.radius,
               pygame.Vector2(cx,cy)-aim*self.radius-side*self.radius]
            pygame.draw.polygon(screen,dark,[(int(x.x),int(x.y)) for x in p])
            pygame.draw.circle(screen,main,(cx,cy),self.radius-2)
            pygame.draw.line(screen,light,(cx-int(aim.x*8),cy-int(aim.y*8)),
                             (cx+int(aim.x*12),cy+int(aim.y*12)),5)
        elif self.kind=="tank":
            r=self.radius
            pygame.draw.rect(screen,dark,(cx-r,cy-r,r*2,r*2),border_radius=8)
            pygame.draw.rect(screen,main,(cx-r+4,cy-r+4,r*2-8,r*2-8),border_radius=6)
            pygame.draw.rect(screen,light,(cx-r+10,cy-r+10,r*2-20,r*2-20),3,border_radius=4)
            pygame.draw.line(screen,light,(cx-r+7,cy),(cx+r-7,cy),3)
            pygame.draw.line(screen,light,(cx,cy-r+7),(cx,cy+r-7),3)
        else:
            pygame.draw.circle(screen,dark,(cx,cy),self.radius+3)
            pygame.draw.circle(screen,main,(cx,cy),self.radius)
            pygame.draw.circle(screen,light,(cx,cy),self.radius-5,2)
            pygame.draw.circle(screen,dark,(cx,cy),self.radius//2)
            pygame.draw.line(screen,light,(cx-int(aim.x*5),cy-int(aim.y*5)),
                             (cx+int(aim.x*9),cy+int(aim.y*9)),4)
        eye=pygame.Vector2(cx,cy)+aim*(self.radius*.45)
        pygame.draw.circle(screen,(255,245,170),(int(eye.x),int(eye.y)),5)
        pygame.draw.circle(screen,(70,20,30),(int(eye.x+aim.x*2),int(eye.y+aim.y*2)),2)
        if self.hp<self.maxhp:
            w=self.radius*2+12
            pygame.draw.rect(screen,(25,25,35),(cx-w/2,cy-self.radius-13,w,6),border_radius=3)
            pygame.draw.rect(screen,(75,220,120),(cx-w/2,cy-self.radius-13,int(w*max(0,self.hp/self.maxhp)),6),border_radius=3)

class Boss:
    def __init__(self):
        # Boss is permanently stationed at the portal until the player gets close.
        self.x, self.y = portal_x, portal_y
        self.guard_x, self.guard_y = portal_x, portal_y
        self.aggro = False
        self.radius = 52
        scale = 1.0 + (round_no - 1) * 0.35
        self.maxhp = (1500 + round_no*180) * scale
        self.hp = self.maxhp
        self.speed = (75 + round_no*3) * min(scale, 1.8)
        self.damage = 12 * scale
        self.bullet_speed = 180 * min(scale, 1.8)
        self.attack_timer = 1.0
        self.spin = 0
        self.dead = False

    def update(self,dt):
        dvec = pygame.Vector2(player.x-self.x, player.y-self.y)
        d = dvec.length()

        # Boss guards the portal. It only leaves the portal when the player
        # enters its aggro radius. Once activated, it follows the player
        # until the boss or player dies.
        if not self.aggro and d <= BOSS_GUARD_RADIUS:
            self.aggro = True
            play(S_BOSS)
            float_text("BOSS AGGRO!", self.x, self.y-80, (255,90,120))
            burst(self.x,self.y,(255,70,110),35,190)

        if self.aggro and d > 1:
            direction = dvec.normalize()
            self.x += direction.x*self.speed*dt
            self.y += direction.y*self.speed*dt

            # Boss can never leave the world.
            self.x = clamp(self.x,80,WORLD_W-80)
            self.y = clamp(self.y,80,WORLD_H-80)

        self.attack_timer -= dt
        self.spin += dt

        # Boss shoots at the player's current position, but every shot travels
        # in a fixed straight line after being fired.
        if self.aggro and self.attack_timer <= 0:
            self.attack_timer = 1.0
            aim = pygame.Vector2(player.x-self.x, player.y-self.y)
            if aim.length_squared():
                aim = aim.normalize()
                for offset in (-.16, 0, .16):
                    cs, sn = math.cos(offset), math.sin(offset)
                    a = pygame.Vector2(
                        aim.x*cs-aim.y*sn,
                        aim.x*sn+aim.y*cs
                    )
                    boss_bullets.append({
                        "x":self.x,"y":self.y,
                        "vx":a.x*self.bullet_speed,
                        "vy":a.y*self.bullet_speed,
                        "dx":a.x,"dy":a.y,
                        "life":4
                    })
            burst(self.x,self.y,(255,80,120),12,130)

    def draw(self):
        px,py=world_to_screen(portal_x,portal_y); pcx,pcy=int(px),int(py)
        circle_glow((portal_x,portal_y),78,(60,180,255),42)
        pygame.draw.circle(screen,(25,65,145),(pcx,pcy),PORTAL_RADIUS+6,4)
        pygame.draw.circle(screen,(90,220,255),(pcx,pcy),PORTAL_RADIUS,4)
        pygame.draw.circle(screen,(10,25,55),(pcx,pcy),PORTAL_RADIUS-13)
        for i in range(4):
            a=self.spin*(1.2+i*.15)+i*math.tau/4
            pygame.draw.line(screen,(120,240,255),(int(pcx+math.cos(a)*12),int(pcy+math.sin(a)*12)),
                             (int(pcx+math.cos(a)*40),int(pcy+math.sin(a)*40)),3)
        sx,sy=world_to_screen(self.x,self.y); cx,cy=int(sx),int(sy)
        circle_glow((self.x,self.y),88,(255,40,100),48)
        pygame.draw.circle(screen,(55,8,30),(cx,cy),self.radius+9)
        pygame.draw.circle(screen,(150,28,75),(cx,cy),self.radius)
        pygame.draw.circle(screen,(240,75,115),(cx,cy),self.radius-7,3)
        for i in range(6):
            a=self.spin*.9+i*math.tau/6; q=pygame.Vector2(math.cos(a),math.sin(a))
            pygame.draw.line(screen,(255,165,70),(int(cx+q.x*37),int(cy+q.y*37)),
                             (int(cx+q.x*68),int(cy+q.y*68)),8)
            pygame.draw.circle(screen,(255,220,120),(int(cx+q.x*68),int(cy+q.y*68)),5)
        pygame.draw.circle(screen,(35,7,25),(cx,cy),25)
        pygame.draw.circle(screen,(255,100,140),(cx,cy),17,3)
        pygame.draw.circle(screen,(255,240,245),(cx,cy),9)
        pygame.draw.circle(screen,(75,8,30),(cx,cy),4)
        w=420
        pygame.draw.rect(screen,(35,15,25),(WIDTH/2-w/2,65,w,18),border_radius=8)
        pygame.draw.rect(screen,(245,55,105),(WIDTH/2-w/2,65,w*max(0,self.hp/self.maxhp),18),border_radius=8)
        pygame.draw.rect(screen,(255,150,175),(WIDTH/2-w/2,65,w,18),2,border_radius=8)
        text("BOSS",(WIDTH/2,74),(255,255,255),SMALL,True)
        text("GUARDING PORTAL" if not self.aggro else "ATTACKING!",
             (sx,sy-self.radius-32),(100,210,255) if not self.aggro else (255,100,120),SMALL,True)

def self_bullet_speed(b):
    return math.hypot(b["vx"], b["vy"])

# ---------- game objects ----------
player = Player()
enemies = []
bullets = []
boss_bullets = []
enemy_bullets = []
gems = []
hearts = []  # red heart pickups that heal the player
boss = None
round_no = 1
round_time = 0.0
kills = 0
spawn_timer = 0
boss_spawned = False
boss_defeated = False
portal_x = WORLD_W/2
portal_y = WORLD_H/2
round_transition = 0.0
round_banner = 0.0
state = "menu"

# permanent progression
save = {"coins":0, "damage":0, "hp":0, "speed":0}

def reset_run():
    global camera, player,enemies,bullets,boss_bullets,enemy_bullets,gems,hearts,boss,round_no,round_time,kills,spawn_timer,boss_spawned,boss_defeated,portal_x,portal_y,round_transition,round_banner,state,particles,floating
    round_no=1
    apply_world_theme(round_no)
    player = Player()
    camera.x = clamp(player.x - WIDTH/2, 0, WORLD_W-WIDTH)
    camera.y = clamp(player.y - HEIGHT/2, 0, WORLD_H-HEIGHT)
    player.damage += save["damage"]*2
    player.maxhp += save["hp"]*10
    player.hp = player.maxhp
    player.speed += save["speed"]*12
    enemies=[]; bullets=[]; boss_bullets=[]; enemy_bullets=[]; gems=[]; hearts=[]
    boss=None; round_no=1; round_time=0.0; kills=0; spawn_timer=0
    boss_spawned=False; boss_defeated=False
    portal_x=WORLD_W/2; portal_y=WORLD_H/2
    round_transition=0.0; round_banner=2.5
    particles=[]; floating=[]
    state="playing"

def gain_xp(v):
    player.xp += v
    while player.xp >= player.next_xp:
        player.xp -= player.next_xp
        player.level += 1
        player.next_xp = int(player.next_xp*1.32)
        player.hp = min(player.maxhp, player.hp+20)
        play(S_LEVEL)
        burst(player.x,player.y,(80,220,255),30,180)
        float_text("LEVEL UP!",player.x,player.y-40,(100,230,255))
        global state
        global choices
        choices = random.sample(upgrade_choices(), 3)
        state="levelup"
        return

def kill_enemy(e):
    global kills
    kills += 1
    value = 2 if e.kind=="tank" else 1
    player.coins += value
    save["coins"] += value
    gems.append([e.x,e.y, value])
    gain_xp(18 if e.kind=="tank" else 10)
    burst(e.x,e.y,(255,170,70),15,130)
    play(S_COIN)
    if random.random() < 0.12:
        hearts.append([e.x, e.y])

def spawn_enemy():
    tw = WORLD_THEME["kinds"]
    normal_n = max(1, (5 - round_no//2) + tw.get("normal", 0))
    fast_n = max(1, min(5, 1 + round_no//2) + tw.get("fast", 0))
    tank_n = max(0, (min(4, round_no-1) if round_no >= 2 else 0) + tw.get("tank", 0))
    kinds = ["normal"] * normal_n + ["fast"] * fast_n + ["tank"] * tank_n
    enemies.append(Enemy(random.choice(kinds), round_no*25))

def upgrade_choices():
    return [
        ("POWER", "Damage +8", "damage"),
        ("RAPID", "Fire rate +18%", "rapid"),
        ("MULTI", "Extra projectile", "multi"),
        ("SHIELD", "Shield +1", "shield"),
        ("REGEN", "Regeneration +2 HP/s", "regen"),
        ("LIGHT", "Lightning strikes nearby", "light"),
        ("FIRE", "Burn aura damage", "fire"),
        ("VITAL", "Max HP +30", "vital"),
    ]

choices = []

def choose_upgrade(idx):
    global choices, state
    name,desc,key = choices[idx]
    if key=="damage": player.damage += 8
    elif key=="rapid": player.fire_rate=max(.11,player.fire_rate*.82)
    elif key=="multi": player.multishot=min(5,player.multishot+1)
    elif key=="shield": player.shield += 1
    elif key=="regen": player.regen += 2
    elif key=="light": player.lightning += 1
    elif key=="fire": player.fire += 1
    elif key=="vital":
        player.maxhp += 30
        player.hp += 30
    choices = []
    state="playing"

# ---------- mobile controls ----------
# Controls are kept in logical coordinates, so their physical size grows
# naturally with the device scale.
JOY_RADIUS = 82
JOY_KNOB_RADIUS = 38
JOY_TOUCH_RADIUS = 120
joy_center=pygame.Vector2(115,HEIGHT-105)
joy_pos=joy_center.copy()
joy_active=False
joy_finger_id=None
joy_vector=pygame.Vector2(0,0)

DASH_RADIUS = 58
dash_center=pygame.Vector2(WIDTH-115,HEIGHT-105)
dash_pressed=False

def get_joy():
    global joy_pos, joy_vector
    if not joy_active:
        joy_pos=joy_center.copy()
        # Smoothly return the movement vector to zero.
        joy_vector *= 0.72
        if joy_vector.length_squared() < 0.0004:
            joy_vector.update(0,0)
        return joy_vector.copy()

    d=joy_pos-joy_center
    if d.length()>JOY_RADIUS:
        d.scale_to_length(JOY_RADIUS)

    target=d/JOY_RADIUS
    # Smooth joystick input to reduce Android touch jitter.
    joy_vector += (target-joy_vector)*0.35
    return joy_vector.copy()

def dash_rect():
    return pygame.Rect(
        int(dash_center.x-DASH_RADIUS),
        int(dash_center.y-DASH_RADIUS),
        int(DASH_RADIUS*2),
        int(DASH_RADIUS*2),
    )

def draw_mobile_controls():
    # Joystick
    pygame.draw.circle(screen,(20,25,38),
                       (int(joy_center.x),int(joy_center.y)),JOY_RADIUS)
    pygame.draw.circle(screen,(65,80,105),
                       (int(joy_center.x),int(joy_center.y)),JOY_RADIUS,3)
    p=joy_pos if joy_active else joy_center
    pygame.draw.circle(screen,(80,120,160),
                       (int(p.x),int(p.y)),JOY_KNOB_RADIUS)
    pygame.draw.circle(screen,(125,165,205),
                       (int(p.x),int(p.y)),JOY_KNOB_RADIUS,3)

    # Dash button
    pygame.draw.circle(screen,(35,45,65),
                       (int(dash_center.x),int(dash_center.y)),DASH_RADIUS)
    pygame.draw.circle(screen,(100,150,205),
                       (int(dash_center.x),int(dash_center.y)),DASH_RADIUS,3)
    if player.dash_cd <= 0:
        text("DASH",dash_center,(120,220,255),SMALL,True)
    else:
        text(f"{player.dash_cd:.1f}",dash_center,(150,165,185),SMALL,True)

# ---------- menus ----------
def button(rect,label,enabled=True):
    r=pygame.Rect(rect)
    mouse=pygame.mouse.get_pos()
    hover=r.collidepoint(mouse)
    fill=(55,75,105) if enabled else (45,45,55)
    if hover and enabled: fill=(75,100,135)
    pygame.draw.rect(screen,fill,r,border_radius=12)
    pygame.draw.rect(screen,(120,140,170),r,2,border_radius=12)
    text(label,r.center,(245,245,250),FONT,True)
    return r

def draw_background():
    th = WORLD_THEME
    screen.fill(th["bg"])
    grid=80
    start_x=int(camera.x//grid)*grid; start_y=int(camera.y//grid)*grid
    for wx in range(start_x-grid,int(camera.x+WIDTH)+grid,grid):
        sx=int(wx-camera.x); pygame.draw.line(screen,th["grid"],(sx,80),(sx,HEIGHT),1)
    for wy in range(start_y-grid,int(camera.y+HEIGHT)+grid,grid):
        sy=int(wy-camera.y+80); pygame.draw.line(screen,th["grid"],(0,sy),(WIDTH,sy),1)
    rng=random.Random(round_no*917)
    for _ in range(42):
        wx=rng.randint(80,WORLD_W-80); wy=rng.randint(120,WORLD_H-80)
        sx,sy=wx-camera.x,wy-camera.y+80
        if -100<sx<WIDTH+100 and 70<sy<HEIGHT+100:
            size=rng.randint(12,35); kind=rng.choice(("rock","crystal","ruin"))
            if kind=="rock":
                pygame.draw.circle(screen,th["rock"],(int(sx),int(sy)),size)
                pygame.draw.circle(screen,th["rock_hl"],(int(sx-size*.25),int(sy-size*.25)),max(2,size//4))
            elif kind=="crystal":
                pts=[(int(sx),int(sy-size*1.5)),(int(sx+size*.65),int(sy)),
                     (int(sx),int(sy+size*1.2)),(int(sx-size*.65),int(sy))]
                pygame.draw.polygon(screen,th["crystal"],pts)
                pygame.draw.polygon(screen,th["crystal_edge"],pts,2)
                pygame.draw.line(screen,th["crystal_core"],(int(sx),int(sy-size*1.1)),(int(sx),int(sy+size*.7)),2)
            else:
                r=pygame.Rect(int(sx-size),int(sy-size*.7),size*2,int(size*1.4))
                pygame.draw.rect(screen,th["ruin"],r,border_radius=6)
                pygame.draw.rect(screen,th["ruin_edge"],r,2,border_radius=6)
                pygame.draw.rect(screen,th["ruin_core"],(r.x+6,r.y+6,r.w-12,r.h-12),border_radius=3)
    pygame.draw.rect(screen,th["border"],pygame.Rect(int(-camera.x),int(80-camera.y),WORLD_W,WORLD_H),3)

def draw_hud():
    # top panel
    pygame.draw.rect(screen,(14,18,29),(0,0,WIDTH,80))
    pygame.draw.line(screen,(55,65,85),(0,79),(WIDTH,79),2)

    # hp
    pygame.draw.rect(screen,(35,35,45),(20,17,250,22),border_radius=8)
    pygame.draw.rect(screen,(225,65,85),(20,17,250*max(0,player.hp/player.maxhp),22),border_radius=8)
    text(f"HP {int(player.hp)}/{int(player.maxhp)}",(28,18),(255,255,255),SMALL)

    # xp
    xpw=260
    pygame.draw.rect(screen,(35,35,45),(300,17,xpw,16),border_radius=6)
    pygame.draw.rect(screen,(75,180,255),(300,17,xpw*player.xp/player.next_xp,16),border_radius=6)
    text(f"LV {player.level}",(300,40),(100,210,255),SMALL)

    text(f"ROUND {round_no}",(590,18),(255,215,90),FONT)
    text(WORLD_THEME["name"],(590,44),(150,170,200),SMALL)
    if boss and not boss.aggro:
        text("Find the portal boss", (WIDTH/2, 102), (100,210,255), SMALL, True)
    elif boss and boss.aggro:
        text("DEFEAT THE BOSS", (WIDTH/2, 102), (255,100,120), SMALL, True)
    text(f"ENEMIES {len(enemies)}/{MAX_ENEMIES}",(740,18),(240,240,245),FONT)
    text(f"KILLS {kills}",(940,18),(240,240,245),FONT)

    if player.dash_cd<=0:
        text("SPACE: DASH",(20,52),(100,220,255),SMALL)
    else:
        text(f"DASH {player.dash_cd:.1f}",(20,52),(130,140,160),SMALL)

def draw_joystick():
    pygame.draw.circle(screen,(20,25,38),(int(joy_center.x),int(joy_center.y)),58)
    pygame.draw.circle(screen,(65,80,105),(int(joy_center.x),int(joy_center.y)),58,2)
    p=joy_pos if joy_active else joy_center
    pygame.draw.circle(screen,(80,120,160),(int(p.x),int(p.y)),27)
    pygame.draw.circle(screen,(125,165,205),(int(p.x),int(p.y)),27,2)

def update_effects(dt):
    for p in particles[:]:
        p["life"]-=dt
        p["x"]+=p["vx"]*dt
        p["y"]+=p["vy"]*dt
        p["vx"]*=.96; p["vy"]*=.96
        if p["life"]<=0: particles.remove(p)
    for f in floating[:]:
        f[3]-=dt
        f[2]-=30*dt
        if f[3]<=0: floating.remove(f)

def draw_effects():
    for p in particles:
        px, py = world_to_screen(p["x"], p["y"])
        pygame.draw.circle(screen,p["color"],(int(px),int(py)),p["size"])
    for f in floating:
        fx, fy = world_to_screen(f[1], f[2])
        text(f[0],(fx,fy),f[4],SMALL,True)

# ---------- Android touch support ----------
def finger_pos(event):
    # event.x / event.y are normalized [0, 1] across the *real* device
    # window (including any letterbox bars), so convert through real
    # screen pixels first, then into logical game coordinates.
    px = event.x * DISPLAY_W
    py = event.y * DISPLAY_H
    return to_logical(px, py)

# ---------- main loop ----------
running=True
while running:
    # Keep movement time-based. A small upper clamp prevents a long pause
    # (for example when Android resumes the app) from causing a huge jump.
    dt=min(clock.tick(FPS)/1000, .050)
    for event in pygame.event.get():
        if event.type==pygame.QUIT:
            running=False

        if event.type==pygame.KEYDOWN:
            if event.key==pygame.K_ESCAPE:
                if state=="playing": state="menu"
            if event.key==pygame.K_SPACE and state=="playing":
                player.dash()

        if event.type==pygame.FINGERDOWN:
            mx, my = finger_pos(event)

            if state=="menu":
                if button((WIDTH//2-130,310,260,58),"PLAY").collidepoint(mx,my):
                    reset_run()
                elif button((WIDTH//2-130,385,260,58),"SHOP").collidepoint(mx,my):
                    state="shop"
                elif button((WIDTH//2-130,460,260,58),"QUIT").collidepoint(mx,my):
                    running=False

            elif state=="shop":
                if button((WIDTH//2-220,210,200,55),"DAMAGE  50").collidepoint(mx,my) and save["coins"]>=50:
                    save["coins"]-=50; save["damage"]+=1
                if button((WIDTH//2+20,210,200,55),"HP  50").collidepoint(mx,my) and save["coins"]>=50:
                    save["coins"]-=50; save["hp"]+=1
                if button((WIDTH//2-220,285,200,55),"SPEED  50").collidepoint(mx,my) and save["coins"]>=50:
                    save["coins"]-=50; save["speed"]+=1
                if button((WIDTH//2-130,510,260,55),"BACK").collidepoint(mx,my):
                    state="menu"

            elif state=="levelup":
                for i in range(3):
                    r=pygame.Rect(90+i*330,270,290,150)
                    if r.collidepoint(mx,my):
                        choose_upgrade(i)

            elif state in ("gameover","win"):
                if button((WIDTH//2-130,440,260,58),"PLAY AGAIN").collidepoint(mx,my):
                    reset_run()
                if button((WIDTH//2-130,510,260,58),"MENU").collidepoint(mx,my):
                    state="menu"

            elif state=="playing":
                # The left touch controls movement; the right touch control
                # triggers dash. Track the finger so a second finger cannot
                # accidentally take over or release the joystick.
                if math.hypot(mx-joy_center.x,my-joy_center.y) < JOY_TOUCH_RADIUS and my > HEIGHT-210:
                    if joy_finger_id is None:
                        joy_finger_id = event.finger_id
                        joy_active=True
                        joy_pos=pygame.Vector2(mx,my)
                elif math.hypot(mx-dash_center.x,my-dash_center.y) <= DASH_RADIUS*1.35:
                    player.dash()
                    dash_pressed=True

        if event.type==pygame.FINGERMOTION:
            if joy_active and event.finger_id == joy_finger_id:
                mx, my = finger_pos(event)
                joy_pos=pygame.Vector2(mx,my)

        if event.type==pygame.FINGERUP:
            if event.finger_id == joy_finger_id:
                joy_active=False
                joy_finger_id=None
                joy_pos=joy_center.copy()

        if event.type==pygame.MOUSEBUTTONDOWN:
            mx,my=to_logical(*event.pos)
            if state=="menu":
                if button((WIDTH//2-130,310,260,58),"PLAY").collidepoint(mx,my):
                    reset_run()
                elif button((WIDTH//2-130,385,260,58),"SHOP").collidepoint(mx,my):
                    state="shop"
                elif button((WIDTH//2-130,460,260,58),"QUIT").collidepoint(mx,my):
                    running=False
            elif state=="shop":
                if button((WIDTH//2-220,210,200,55),"DAMAGE  50").collidepoint(mx,my) and save["coins"]>=50:
                    save["coins"]-=50; save["damage"]+=1
                if button((WIDTH//2+20,210,200,55),"HP  50").collidepoint(mx,my) and save["coins"]>=50:
                    save["coins"]-=50; save["hp"]+=1
                if button((WIDTH//2-220,285,200,55),"SPEED  50").collidepoint(mx,my) and save["coins"]>=50:
                    save["coins"]-=50; save["speed"]+=1
                if button((WIDTH//2-130,510,260,55),"BACK").collidepoint(mx,my):
                    state="menu"
            elif state=="levelup":
                for i in range(3):
                    r=pygame.Rect(90+i*330,270,290,150)
                    if r.collidepoint(mx,my):
                        choose_upgrade(i)
            elif state in ("gameover","win"):
                if button((WIDTH//2-130,440,260,58),"PLAY AGAIN").collidepoint(mx,my):
                    reset_run()
                if button((WIDTH//2-130,510,260,58),"MENU").collidepoint(mx,my):
                    state="menu"
            elif state=="playing":
                if math.hypot(mx-joy_center.x,my-joy_center.y)<JOY_TOUCH_RADIUS and my>HEIGHT-210:
                    joy_active=True
                    joy_pos=pygame.Vector2(mx,my)
                elif math.hypot(mx-dash_center.x,my-dash_center.y)<=DASH_RADIUS*1.35:
                    player.dash()

        if event.type==pygame.MOUSEMOTION and joy_active:
            joy_pos=pygame.Vector2(to_logical(*event.pos))

        if event.type==pygame.MOUSEBUTTONUP:
            joy_active=False
            joy_pos=joy_center.copy()

    draw_background()

    if state=="menu":
        circle_glow((WIDTH/2,170),100,(60,160,255),35)
        text("SURVIVOR", (WIDTH/2,145), (95,205,255), TITLE, True)
        text("RUSH", (WIDTH/2,205), (255,215,90), TITLE, True)
        text("V5  •  SURVIVE • UPGRADE • DEFEAT THE BOSS",
             (WIDTH/2,265),(170,185,210),SMALL,True)
        button((WIDTH//2-130,310,260,58),"PLAY")
        button((WIDTH//2-130,385,260,58),"SHOP")
        button((WIDTH//2-130,460,260,58),"QUIT")
        text(f"Permanent coins: {save['coins']}",(WIDTH/2,555),(255,215,90),FONT,True)
        text("WASD / ARROWS to move  •  SPACE to dash",(WIDTH/2,600),(135,150,175),SMALL,True)

    elif state=="shop":
        text("PERMANENT SHOP",(WIDTH/2,105),(100,210,255),BIG,True)
        text(f"Coins: {save['coins']}",(WIDTH/2,155),(255,215,90),FONT,True)
        button((WIDTH//2-220,210,200,55),"DAMAGE  50")
        button((WIDTH//2+20,210,200,55),"HP  50")
        button((WIDTH//2-220,285,200,55),"SPEED  50")
        text(f"Damage level: {save['damage']}",(WIDTH//2-120,370),(190,200,220),SMALL,True)
        text(f"HP level: {save['hp']}",(WIDTH//2+120,370),(190,200,220),SMALL,True)
        text(f"Speed level: {save['speed']}",(WIDTH//2-120,405),(190,200,220),SMALL,True)
        button((WIDTH//2-130,510,260,55),"BACK")

    elif state=="playing":
        round_time += dt
        round_banner = max(0, round_banner-dt)

        # Each round has its own 60-second world phase.
        # At 50 seconds the single boss of the round appears.
        spawn_timer -= dt
        if spawn_timer <= 0 and len(enemies) < MAX_ENEMIES and not boss:
            spawn_timer = 0.35
            while len(enemies) < MAX_ENEMIES:
                spawn_enemy()

        if round_time >= ROUND_BOSS_TIME and not boss_spawned:
            # Choose the portal/boss location once for this world.
            random.seed(round_no * 991)
            portal_x = random.randint(350, WORLD_W-350)
            portal_y = random.randint(300, WORLD_H-300)

            boss = Boss()
            boss_spawned = True
            boss_defeated = False
            play(S_BOSS)
            float_text(f"ROUND {round_no} BOSS!", player.x, player.y-70, (255,80,110))

        # Defeating the boss completes the round and creates a new world.
        if boss_spawned and boss_defeated and boss is None and round_time >= ROUND_BOSS_TIME:
            # The victory state is handled below only for the final boss.
            round_no += 1
            apply_world_theme(round_no)
            round_time = 0.0
            boss_spawned = False
            boss_defeated = False
            round_banner = 3.0
            enemies.clear()
            enemy_bullets.clear()
            bullets.clear()

            # Generate a fresh world/arena feel by moving the player to a new area.
            random.seed(round_no * 991)
            portal_x = random.randint(350, WORLD_W-350)
            portal_y = random.randint(300, WORLD_H-300)

            # Start the player away from the guarded portal.
            for _ in range(30):
                player.x = random.randint(500, WORLD_W-500)
                player.y = random.randint(400, WORLD_H-400)
                if dist((player.x,player.y),(portal_x,portal_y)) > 700:
                    break

            camera.x = clamp(player.x - WIDTH/2, 0, WORLD_W-WIDTH)
            camera.y = clamp(player.y - HEIGHT/2, 0, WORLD_H-HEIGHT)
            burst(player.x, player.y, (100,220,255), 70, 250)
            float_text(f"ROUND {round_no}", player.x, player.y-70, (100,220,255))

        keys=pygame.key.get_pressed()
        joy=get_joy()
        player.update(dt,keys,joy)
        player.shoot()

        MAX_ACTIVE_ATTACKERS = 4
        engaged = [e for e in enemies if e.engaged]
        engaged.sort(key=lambda e: (e.x-player.x)**2 + (e.y-player.y)**2)
        attackers = set(id(e) for e in engaged[:MAX_ACTIVE_ATTACKERS])
        for e in enemies:
            e.update(dt, enemies, allow_fire=(id(e) in attackers))

        # bullets
        for b in bullets[:]:
            # TRUE STRAIGHT-LINE PROJECTILE:
            # dx/dy are saved when fired and never changed afterward.
            b["x"] += b["dx"] * self_bullet_speed(b) * dt
            b["y"] += b["dy"] * self_bullet_speed(b) * dt
            b["life"] -= dt
            hit=False
            for e in enemies[:]:
                if dist((b["x"],b["y"]),(e.x,e.y)) < e.radius+6:
                    e.hp-=b["damage"]
                    e.hit_flash=.08
                    burst(b["x"],b["y"],(255,210,100),4,80)
                    play(S_HIT)
                    hit=True
                    if e.hp<=0:
                        enemies.remove(e)
                        kill_enemy(e)
                    break
            if boss and not boss.dead and not hit and dist((b["x"],b["y"]),(boss.x,boss.y))<boss.radius+7:
                boss.hp-=b["damage"]
                burst(b["x"],b["y"],(255,100,130),5,80)
                hit=True
                if boss.hp<=0:
                    boss.dead=True
                    bx, by = boss.x, boss.y
                    reward = 100 + round_no*25
                    player.coins += reward
                    save["coins"] += reward
                    play(S_WIN)
                    burst(player.x,player.y,(255,215,80),100,260)
                    for _ in range(3):
                        hearts.append([bx+random.uniform(-30,30), by+random.uniform(-30,30)])
                    boss_defeated = True
                    boss = None
            sbx, sby = world_to_screen(b["x"], b["y"])
            if hit or b["life"]<=0 or not(-20<sbx<WIDTH+20 and 80<sby<HEIGHT+20):
                if b in bullets: bullets.remove(b)

        # Enemy projectiles damage the player; enemies themselves do not ram.
        for b in enemy_bullets[:]:
            # Enemy shot direction is locked at the instant it is fired.
            speed = math.hypot(b["vx"], b["vy"])
            b["x"] += b["dx"] * speed * dt
            b["y"] += b["dy"] * speed * dt
            b["life"] -= dt

            if dist((b["x"],b["y"]),(player.x,player.y)) < player.radius + 8:
                if player.invuln <= 0:
                    # Enemies haven't found their aim yet on round 1 — most shots whiff.
                    hit_chance = 0.10 if round_no == 1 else 1.0
                    if random.random() < hit_chance:
                        if player.shield > 0:
                            player.shield -= 1
                        else:
                            player.hp -= b["damage"]
                        player.invuln = .35
                        burst(player.x,player.y,(255,80,100),10,120)
                        play(S_HIT)
                        if player.hp <= 0:
                            state = "gameover"
                    else:
                        float_text("MISS", player.x, player.y-25, (170,195,225))
                if b in enemy_bullets:
                    enemy_bullets.remove(b)
                continue

            sbx, sby = world_to_screen(b["x"], b["y"])
            if b["life"] <= 0 or not (-30 < sbx < WIDTH+30 and 70 < sby < HEIGHT+30):
                if b in enemy_bullets:
                    enemy_bullets.remove(b)

        # boss bullets
        for b in boss_bullets[:]:
            # Boss shot direction is locked at the instant it is fired.
            b["x"] += b["vx"] * dt
            b["y"] += b["vy"] * dt
            b["life"] -= dt
            if dist((b["x"],b["y"]),(player.x,player.y))<player.radius+8 and player.invuln<=0:
                if player.shield>0:
                    player.shield-=1
                else:
                    player.hp-=boss.damage if boss else 12
                player.invuln=.35
                burst(player.x,player.y,(255,80,100),10,120)
                play(S_HIT)
                if player.hp<=0:
                    state="gameover"
            sbx, sby = world_to_screen(b["x"], b["y"])
            if b["life"]<=0 or not(-30<sbx<WIDTH+30 and 70<sby<HEIGHT+30):
                boss_bullets.remove(b)

        if boss:
            boss.update(dt)

        # Player abilities affect nearby enemies, but enemy contact causes no damage.
        for e in enemies[:]:
            if player.fire and dist((e.x,e.y),(player.x,player.y)) < 100:
                e.hp -= player.fire*7*dt
                e.hit_flash=.04

            if player.lightning and random.random() < player.lightning*.7*dt and dist((e.x,e.y),(player.x,player.y)) < 170:
                e.hp -= 35
                burst(e.x,e.y,(120,220,255),12,160)
                float_text("⚡",e.x,e.y-25,(130,220,255))
                if e.hp<=0 and e in enemies:
                    enemies.remove(e)
                    kill_enemy(e)

        # collect gems
        for g in gems[:]:
            d=dist((g[0],g[1]),(player.x,player.y))
            if d<120:
                v=pygame.Vector2(player.x-g[0],player.y-g[1])
                if v.length_squared():
                    v=v.normalize()
                    g[0]+=v.x*320*dt; g[1]+=v.y*320*dt
            if d<player.radius+12:
                gain_xp(g[2]*9)
                float_text(f"+{g[2]} XP",g[0],g[1])
                gems.remove(g)

        # collect hearts (heal on pickup)
        for h in hearts[:]:
            d=dist((h[0],h[1]),(player.x,player.y))
            if d<130:
                v=pygame.Vector2(player.x-h[0],player.y-h[1])
                if v.length_squared():
                    v=v.normalize()
                    h[0]+=v.x*340*dt; h[1]+=v.y*340*dt
            if d<player.radius+12:
                heal_amt = 20
                healed = min(player.maxhp, player.hp+heal_amt) - player.hp
                player.hp = min(player.maxhp, player.hp+heal_amt)
                float_text(f"+{int(healed) if healed else heal_amt} HP", h[0], h[1], (255,90,115))
                burst(h[0],h[1],(255,90,115),14,140)
                play(S_HEAL)
                hearts.remove(h)

        update_effects(dt)

        # Camera is locked to the player: the world scrolls as the player moves.
        camera.x = clamp(player.x - WIDTH/2, 0, WORLD_W-WIDTH)
        camera.y = clamp(player.y - (80 + (HEIGHT-80)/2), 0, WORLD_H-(HEIGHT-80))

        # Portal for the current world. Before the boss arrives it is the
        # destination that the boss will guard later.
        px, py = world_to_screen(portal_x, portal_y)
        if not boss:
            circle_glow((portal_x,portal_y),60,(60,160,255),28)
            pygame.draw.circle(screen,(45,120,210),(int(px),int(py)),PORTAL_RADIUS,5)
            pygame.draw.circle(screen,(100,220,255),(int(px),int(py)),PORTAL_RADIUS-10,3)

        # draw gems
        for g in gems:
            gx, gy = world_to_screen(g[0], g[1])
            pygame.draw.polygon(screen,(90,240,190),[
                (gx,gy-7),(gx+7,gy),(gx,gy+7),(gx-7,gy)
            ])

        # draw hearts (healing pickups)
        for h in hearts:
            hx, hy = world_to_screen(h[0], h[1])
            bob = math.sin(pygame.time.get_ticks()*.004 + h[0]) * 3
            circle_glow((h[0], h[1]-bob), 20, (255,70,100), 35)
            draw_heart(hx, hy-bob, 20, (255,60,95), (255,190,205))

        for e in enemies: e.draw()

        # Enemy bullets
        for b in enemy_bullets:
            c = (255,100,130)
            if b.get("kind") == "fast":
                c = (255,130,170)
            elif b.get("kind") == "tank":
                c = (190,120,255)
            bx,by=world_to_screen(b["x"],b["y"])
            dx,dy=b.get("dx",0),b.get("dy",0)
            pygame.draw.line(screen,c,(int(bx-dx*16),int(by-dy*16)),(int(bx),int(by)),5)
            pygame.draw.circle(screen,c,(int(bx),int(by)),7)
            pygame.draw.circle(screen,(255,235,235),(int(bx),int(by)),2)

        # Player energy bolts with straight trails.
        for b in bullets:
            bx,by=world_to_screen(b["x"],b["y"])
            pygame.draw.line(screen,(255,170,55),(int(bx-b["dx"]*18),int(by-b["dy"]*18)),(int(bx),int(by)),5)
            pygame.draw.circle(screen,(255,225,100),(int(bx),int(by)),6)
            pygame.draw.circle(screen,(255,255,240),(int(bx),int(by)),2)

        # Boss bullets
        for b in boss_bullets:
            bx,by=world_to_screen(b["x"],b["y"])
            dx,dy=b.get("dx",0),b.get("dy",0)
            pygame.draw.line(screen,(255,40,110),(int(bx-dx*22),int(by-dy*22)),(int(bx),int(by)),7)
            pygame.draw.circle(screen,(255,90,150),(int(bx),int(by)),9)
            pygame.draw.circle(screen,(255,220,235),(int(bx),int(by)),3)

        if boss: boss.draw()

        player.draw()
        draw_effects()
        draw_hud()
        draw_mobile_controls()

        if round_banner > 0:
            alpha = min(255, int(round_banner/3.0*255))
            banner = pygame.Surface((WIDTH,90), pygame.SRCALPHA)
            banner.fill((10,18,35, min(180,alpha)))
            screen.blit(banner,(0,105))
            if boss_spawned and boss:
                text(f"ROUND {round_no} — BOSS FIGHT", (WIDTH/2,150),
                     (255,90,120), BIG, True)
            else:
                text(f"ROUND {round_no} — {WORLD_THEME['name'].upper()}", (WIDTH/2,150),
                     (100,220,255), BIG, True)

    elif state=="levelup":
        # Freeze game while choosing.
        draw_hud()
        text("LEVEL UP!",(WIDTH/2,145),(100,225,255),BIG,True)
        text("Choose one upgrade",(WIDTH/2,195),(190,200,220),FONT,True)
        for i,(name,desc,key) in enumerate(choices):
            r=pygame.Rect(90+i*330,270,290,150)
            pygame.draw.rect(screen,(24,32,48),r,border_radius=16)
            pygame.draw.rect(screen,(85,120,160),r,2,border_radius=16)
            text(name,(r.centerx,300),(255,215,90),BIG,True)
            text(desc,(r.centerx,355),(215,225,240),SMALL,True)
            text(f"CHOICE {i+1}",(r.centerx,395),(100,210,255),SMALL,True)

    elif state in ("gameover","win"):
        draw_hud()
        overlay=pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA)
        overlay.fill((0,0,0,170))
        screen.blit(overlay,(0,0))
        if state=="win":
            text("BOSS DEFEATED!",(WIDTH/2,190),(255,220,90),BIG,True)
            text("+100 COINS",(WIDTH/2,245),(100,230,180),FONT,True)
        else:
            text("GAME OVER",(WIDTH/2,190),(255,80,100),BIG,True)
        text(f"Round {round_no}   •   Level {player.level}   •   Kills {kills}",
             (WIDTH/2,305),(220,225,235),FONT,True)
        button((WIDTH//2-130,440,260,58),"PLAY AGAIN")
        button((WIDTH//2-130,510,260,58),"MENU")

    # The logical surface is sized to the device aspect ratio, so this is
    # a uniform scale with no letterbox bars and no aspect-ratio distortion.
    # Use the faster scale operation on Android; smoothscale here costs a
    # full-frame high-quality resize every frame.
    if _scale == 1.0 and screen.get_size() == real_screen.get_size():
        real_screen.blit(screen, (0,0))
    else:
        scaled = pygame.transform.scale(screen, _scaled_size)
        real_screen.blit(scaled, _blit_pos)
    pygame.display.flip()

pygame.quit()
