"""
╔══════════════════════════════════════════════════════════════╗
║           NOVA SIEGE — Arcade Space Shooter                  ║
║           Built with Python + Pygame                         ║
╚══════════════════════════════════════════════════════════════╝

ARCHITECTURE OVERVIEW:
    Game          — Master controller: game loop, state machine, event routing
    Player        — Player ship: movement, shooting, health, animations
    Enemy         — Enemy variants: movement patterns, AI, spawning
    Bullet        — Projectile logic for both player and enemies
    Particle      — Visual effects: explosions, thrust, impact sparks
    PowerUp       — Collectible items: shield, rapid-fire, triple-shot
    UI            — HUD rendering: health bar, score, lives, messages
    SoundManager  — Placeholder audio wrapper (graceful if no files)
    StarField     — Parallax scrolling background stars

STATE MACHINE:
    MENU → PLAYING → GAME_OVER → MENU (restart)

DEPENDENCIES:
    pip install pygame
    python main.py
"""

import pygame
import random
import math
import sys
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum, auto

# ─────────────────────────────────────────────────────────────
# CONSTANTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────

# Base design resolution — game logic runs at this size
BASE_W, BASE_H = 480, 720

# Target window size (scales up on modern displays)
WIN_W, WIN_H = 480, 720

FPS = 60

# Colour palette (retro-neon aesthetic)
C_BG        = (5,   5,  18)   # Near-black deep space
C_STAR1     = (200, 200, 255)  # Far stars
C_STAR2     = (150, 180, 255)  # Mid stars
C_STAR3     = (255, 255, 255)  # Near stars
C_PLAYER    = (80,  220, 255)  # Cyan ship
C_PLAYER_DK = (30,  130, 180)  # Dark accent
C_BULLET    = (255, 255, 100)  # Player bullet
C_EBULLET   = (255,  80,  80)  # Enemy bullet
C_ENEMY_A   = (255, 100, 100)  # Scout enemy
C_ENEMY_B   = (220,  80, 220)  # Hunter enemy
C_ENEMY_C   = (255, 160,  40)  # Tank enemy
C_HEALTH    = ( 60, 220,  90)  # Health bar
C_SHIELD    = ( 60, 160, 255)  # Shield bar
C_SCORE     = (255, 240, 180)  # Score text
C_WHITE     = (255, 255, 255)
C_BLACK     = (  0,   0,   0)
C_GOLD      = (255, 200,  50)
C_RED       = (255,  60,  60)
C_ALPHA     = (255,   0, 255)   # Colour-key transparent colour (unused)

# Game balance
PLAYER_SPEED    = 280   # px/s
PLAYER_HEALTH   = 100
BULLET_SPEED    = 600
EBULLET_SPEED   = 260
ENEMY_SPAWN_CD  = 1.8   # seconds between spawns (decreases with score)
POWERUP_CHANCE  = 0.18  # probability a killed enemy drops a powerup
COMBO_WINDOW    = 2.5   # seconds to chain kills for score multiplier
PULSE_RADIUS    = 120   # px shockwave radius around player


class GameState(Enum):
    MENU      = auto()
    PLAYING   = auto()
    GAME_OVER = auto()
    PAUSED    = auto()


# ─────────────────────────────────────────────────────────────
# UTILITY HELPERS
# ─────────────────────────────────────────────────────────────

def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def lerp(a, b, t):
    return a + (b - a) * t


def distance(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def draw_text_centered(surface, text, font, color, cx, cy, shadow=True):
    """Render text centred on (cx, cy) with optional drop shadow."""
    if shadow:
        s = font.render(text, True, (0, 0, 0))
        r = s.get_rect(center=(cx + 2, cy + 2))
        surface.blit(s, r)
    img = font.render(text, True, color)
    rect = img.get_rect(center=(cx, cy))
    surface.blit(img, rect)
    return rect


def draw_rounded_rect(surface, color, rect, radius=8, alpha=255):
    """Draw an anti-aliased rounded rectangle."""
    s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), s.get_rect(), border_radius=radius)
    surface.blit(s, rect.topleft)


# ─────────────────────────────────────────────────────────────
# SOUND MANAGER (graceful fallback)
# ─────────────────────────────────────────────────────────────

class SoundManager:
    """
    Wraps pygame.mixer with placeholder paths.
    If sound files don't exist, all calls silently no-op.
    Replace paths with real .wav/.ogg files to enable audio.
    """
    SOUNDS = {
        "shoot":     "assets/shoot.wav",
        "explosion": "assets/explosion.wav",
        "powerup":   "assets/powerup.wav",
        "hit":       "assets/hit.wav",
        "gameover":  "assets/gameover.wav",
    }

    def __init__(self):
        self._cache = {}
        if not pygame.mixer.get_init():
            return
        for name, path in self.SOUNDS.items():
            if os.path.exists(path):
                try:
                    self._cache[name] = pygame.mixer.Sound(path)
                except Exception:
                    pass

    def play(self, name: str, volume: float = 0.7):
        snd = self._cache.get(name)
        if snd:
            snd.set_volume(volume)
            snd.play()


# ─────────────────────────────────────────────────────────────
# STAR FIELD (parallax background)
# ─────────────────────────────────────────────────────────────

@dataclass
class Star:
    x: float
    y: float
    speed: float
    size: int
    color: Tuple


class StarField:
    """Three-layer parallax star field that scrolls downward."""

    def __init__(self, count=120):
        self.stars: List[Star] = []
        layers = [
            (40,  1, C_STAR1),   # Far — slow, dim, tiny
            (40,  2, C_STAR2),   # Mid
            (40,  3, C_STAR3),   # Near — fast, bright, bigger
        ]
        for n, spd, col in layers:
            for _ in range(n):
                self.stars.append(Star(
                    x=random.uniform(0, BASE_W),
                    y=random.uniform(0, BASE_H),
                    speed=spd * random.uniform(0.8, 1.2),
                    size=1 if spd == 1 else (1 if spd == 2 else 2),
                    color=col,
                ))

    def update(self, dt):
        for s in self.stars:
            s.y += s.speed * 60 * dt
            if s.y > BASE_H:
                s.y = 0
                s.x = random.uniform(0, BASE_W)

    def draw(self, surface):
        for s in self.stars:
            pygame.draw.circle(surface, s.color, (int(s.x), int(s.y)), s.size)


# ─────────────────────────────────────────────────────────────
# PARTICLE SYSTEM
# ─────────────────────────────────────────────────────────────

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float       # remaining life in seconds
    max_life: float   # total life (for alpha fade)
    color: Tuple
    size: float
    gravity: float = 0.0


class ParticleSystem:
    """Lightweight particle emitter for explosions, thrust, sparks."""

    def __init__(self):
        self.particles: List[Particle] = []

    def emit_explosion(self, x, y, color, count=18, speed_range=(40, 180)):
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(*speed_range)
            life  = random.uniform(0.3, 0.8)
            self.particles.append(Particle(
                x=x, y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                life=life, max_life=life,
                color=color,
                size=random.uniform(1.5, 4),
                gravity=80,
            ))

    def emit_thrust(self, x, y):
        """Rocket exhaust from player ship."""
        for _ in range(3):
            life = random.uniform(0.1, 0.25)
            self.particles.append(Particle(
                x=x + random.uniform(-4, 4),
                y=y,
                vx=random.uniform(-20, 20),
                vy=random.uniform(60, 140),
                life=life, max_life=life,
                color=random.choice([(255, 160, 30), (255, 220, 80), (200, 80, 255)]),
                size=random.uniform(2, 5),
            ))

    def emit_hit(self, x, y):
        for _ in range(8):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(30, 120)
            life  = random.uniform(0.15, 0.35)
            self.particles.append(Particle(
                x=x, y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                life=life, max_life=life,
                color=C_WHITE,
                size=random.uniform(1, 3),
            ))

    def update(self, dt):
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life > 0:
                p.x  += p.vx * dt
                p.y  += p.vy * dt
                p.vy += p.gravity * dt
                alive.append(p)
        self.particles = alive

    def draw(self, surface):
        for p in self.particles:
            alpha_ratio = p.life / p.max_life
            alpha = int(255 * alpha_ratio)
            r, g, b = p.color
            color = (r, g, b)
            size = max(1, int(p.size * alpha_ratio))
            pygame.draw.circle(surface, color, (int(p.x), int(p.y)), size)


# ─────────────────────────────────────────────────────────────
# BULLET
# ─────────────────────────────────────────────────────────────

class Bullet:
    """
    Shared bullet class for player and enemies.
    is_player flag determines team, color, and damage.
    """

    def __init__(self, x, y, vx, vy, is_player=True):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.is_player = is_player
        self.radius = 4 if is_player else 3
        self.color   = C_BULLET if is_player else C_EBULLET
        self.damage  = 20 if is_player else 10
        self.alive   = True
        # Glow trail
        self.trail: List[Tuple] = []

    def update(self, dt):
        self.trail.append((self.x, self.y))
        if len(self.trail) > 5:
            self.trail.pop(0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        # Kill if out of bounds
        if self.y < -20 or self.y > BASE_H + 20 or self.x < -20 or self.x > BASE_W + 20:
            self.alive = False

    def draw(self, surface):
        # Draw glowing trail
        for i, (tx, ty) in enumerate(self.trail):
            alpha_ratio = (i + 1) / len(self.trail)
            r, g, b = self.color
            trail_color = (
                int(r * alpha_ratio),
                int(g * alpha_ratio),
                int(b * alpha_ratio),
            )
            pygame.draw.circle(surface, trail_color, (int(tx), int(ty)),
                               max(1, int(self.radius * alpha_ratio * 0.7)))
        # Draw bullet core
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)
        # Bright inner core
        pygame.draw.circle(surface, C_WHITE, (int(self.x), int(self.y)),
                           max(1, self.radius - 2))

    @property
    def rect(self):
        return pygame.Rect(self.x - self.radius, self.y - self.radius,
                           self.radius * 2, self.radius * 2)


# ─────────────────────────────────────────────────────────────
# POWER-UP
# ─────────────────────────────────────────────────────────────

class PowerUpType(Enum):
    HEALTH     = "health"
    SHIELD     = "shield"
    RAPID_FIRE = "rapid"
    TRIPLE     = "triple"


POWERUP_COLORS = {
    PowerUpType.HEALTH:     (60,  220, 90),
    PowerUpType.SHIELD:     (60,  160, 255),
    PowerUpType.RAPID_FIRE: (255, 220, 60),
    PowerUpType.TRIPLE:     (220, 80,  255),
}

POWERUP_LABELS = {
    PowerUpType.HEALTH:     "HP",
    PowerUpType.SHIELD:     "SH",
    PowerUpType.RAPID_FIRE: "RF",
    PowerUpType.TRIPLE:     "3X",
}


class PowerUp:
    def __init__(self, x, y, kind: PowerUpType = None):
        self.x = x
        self.y = y
        self.kind = kind or random.choice(list(PowerUpType))
        self.color = POWERUP_COLORS[self.kind]
        self.radius = 12
        self.speed  = 80
        self.alive  = True
        self.age    = 0.0      # For bob animation
        self.label  = POWERUP_LABELS[self.kind]

    def update(self, dt):
        self.y   += self.speed * dt
        self.age += dt
        if self.y > BASE_H + 30:
            self.alive = False

    def draw(self, surface, font_small):
        bob_y = int(self.y + math.sin(self.age * 4) * 4)
        # Glow halo
        glow_surf = pygame.Surface((60, 60), pygame.SRCALPHA)
        r, g, b = self.color
        pygame.draw.circle(glow_surf, (r, g, b, 50), (30, 30), 28)
        surface.blit(glow_surf, (int(self.x) - 30, bob_y - 30))
        # Core circle
        pygame.draw.circle(surface, self.color, (int(self.x), bob_y), self.radius)
        pygame.draw.circle(surface, C_WHITE, (int(self.x), bob_y), self.radius, 2)
        # Label
        txt = font_small.render(self.label, True, C_BLACK)
        surface.blit(txt, txt.get_rect(center=(int(self.x), bob_y)))

    @property
    def rect(self):
        return pygame.Rect(self.x - self.radius, self.y - self.radius,
                           self.radius * 2, self.radius * 2)


# ─────────────────────────────────────────────────────────────
# ENEMY
# ─────────────────────────────────────────────────────────────

class EnemyType(Enum):
    SCOUT  = "scout"    # Fast, low HP, straight movement
    HUNTER = "hunter"  # Tracks player, medium HP
    TANK   = "tank"    # Slow, high HP, fires faster


@dataclass
class EnemyConfig:
    hp:         int
    speed:      float
    color:      Tuple
    size:       int
    score:      int
    fire_rate:  float   # shots per second
    move_type:  str     # "straight", "sine", "track"


ENEMY_CONFIGS = {
    EnemyType.SCOUT:  EnemyConfig(20,  160, C_ENEMY_A, 16, 100, 0.6, "sine"),
    EnemyType.HUNTER: EnemyConfig(50,  110, C_ENEMY_B, 20, 250, 0.8, "track"),
    EnemyType.TANK:   EnemyConfig(120, 55,  C_ENEMY_C, 26, 500, 1.2, "straight"),
}


class Enemy:
    def __init__(self, x, y, kind: EnemyType, player_ref):
        self.x = x
        self.y = y
        self.kind = kind
        cfg = ENEMY_CONFIGS[kind]
        self.hp        = cfg.hp
        self.max_hp    = cfg.hp
        self.speed     = cfg.speed
        self.color     = cfg.color
        self.size      = cfg.size
        self.score     = cfg.score
        self.fire_rate = cfg.fire_rate
        self.move_type = cfg.move_type
        self.player    = player_ref
        self.alive     = True
        self.age       = 0.0
        self.fire_cd   = random.uniform(0, 1.0 / self.fire_rate)
        self.vx        = 0.0
        # Sine wave offset
        self.sine_amp  = random.uniform(40, 90)
        self.sine_freq = random.uniform(1.5, 3.0)
        self.origin_x  = x
        # Flash when hit
        self.hit_flash = 0.0

    def update(self, dt) -> List[Bullet]:
        self.age    += dt
        self.fire_cd -= dt
        self.hit_flash = max(0, self.hit_flash - dt)

        # Movement patterns
        if self.move_type == "straight":
            self.y += self.speed * dt
        elif self.move_type == "sine":
            self.y += self.speed * dt
            self.x = self.origin_x + math.sin(self.age * self.sine_freq) * self.sine_amp
        elif self.move_type == "track":
            # Smoothly track player X
            dx = self.player.x - self.x
            self.x += clamp(dx * 2.5 * dt, -self.speed * dt, self.speed * dt)
            self.y += self.speed * 0.55 * dt

        self.x = clamp(self.x, self.size, BASE_W - self.size)

        # Kill if off-screen (bottom)
        if self.y > BASE_H + 60:
            self.alive = False

        # Fire bullets
        new_bullets = []
        if self.fire_cd <= 0:
            self.fire_cd = 1.0 / self.fire_rate
            new_bullets = self._fire()
        return new_bullets

    def _fire(self) -> List[Bullet]:
        bullets = []
        if self.kind == EnemyType.TANK:
            # Spread shot (3 bullets)
            for angle_offset in [-15, 0, 15]:
                rad = math.radians(90 + angle_offset)
                bullets.append(Bullet(
                    self.x, self.y + self.size,
                    math.cos(rad) * EBULLET_SPEED,
                    math.sin(rad) * EBULLET_SPEED,
                    is_player=False
                ))
        else:
            bullets.append(Bullet(
                self.x, self.y + self.size,
                0, EBULLET_SPEED,
                is_player=False
            ))
        return bullets

    def take_damage(self, amount):
        self.hp -= amount
        self.hit_flash = 0.12
        if self.hp <= 0:
            self.alive = False

    def draw(self, surface):
        color = C_WHITE if self.hit_flash > 0 else self.color
        cx, cy = int(self.x), int(self.y)

        if self.kind == EnemyType.SCOUT:
            # Triangle pointing down
            pts = [
                (cx, cy + self.size),
                (cx - self.size, cy - self.size // 2),
                (cx + self.size, cy - self.size // 2),
            ]
            pygame.draw.polygon(surface, color, pts)
            pygame.draw.polygon(surface, C_WHITE, pts, 1)

        elif self.kind == EnemyType.HUNTER:
            # Diamond shape
            s = self.size
            pts = [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]
            pygame.draw.polygon(surface, color, pts)
            pygame.draw.polygon(surface, C_WHITE, pts, 1)
            # Inner glow
            pygame.draw.polygon(surface, C_WHITE,
                [(cx, cy - s//2), (cx + s//2, cy), (cx, cy + s//2), (cx - s//2, cy)], 1)

        elif self.kind == EnemyType.TANK:
            # Chunky hexagon
            pts = []
            for i in range(6):
                a = math.radians(60 * i - 30)
                pts.append((cx + math.cos(a) * self.size, cy + math.sin(a) * self.size))
            pygame.draw.polygon(surface, color, pts)
            pygame.draw.polygon(surface, C_WHITE, pts, 2)

        # Health bar above enemy
        if self.hp < self.max_hp:
            bar_w = self.size * 2
            bar_h = 4
            bx = cx - bar_w // 2
            by = cy - self.size - 8
            pygame.draw.rect(surface, (80, 0, 0), (bx, by, bar_w, bar_h))
            hp_ratio = self.hp / self.max_hp
            pygame.draw.rect(surface, C_HEALTH,
                             (bx, by, int(bar_w * hp_ratio), bar_h))

    @property
    def rect(self):
        s = self.size
        return pygame.Rect(self.x - s, self.y - s, s * 2, s * 2)


# ─────────────────────────────────────────────────────────────
# PLAYER
# ─────────────────────────────────────────────────────────────

class Player:
    """
    Player-controlled ship.
    Supports movement, shooting (normal / triple / rapid),
    shield absorption, invincibility frames after hit.
    """

    def __init__(self):
        self.x = BASE_W // 2
        self.y = BASE_H - 100
        self.speed  = PLAYER_SPEED
        self.width  = 22
        self.height = 30
        self.hp     = PLAYER_HEALTH
        self.max_hp = PLAYER_HEALTH
        self.alive  = True

        # Shooting
        self.shoot_cd  = 0.0
        self.shoot_rate = 5.0  # shots/sec (base)
        self.ammo_type  = "normal"  # "normal", "triple"
        self.rapid_fire = False

        # Power-up timers
        self.triple_timer     = 0.0
        self.rapid_fire_timer = 0.0
        self.shield_hp        = 0
        self.max_shield       = 60

        # Invincibility frames after taking damage
        self.invincible    = 0.0
        self.invincible_cd = 1.5

        # Defensive pulse ability
        self.pulse_cd      = 0.0
        self.pulse_max_cd  = 8.0

        # Visual
        self.age          = 0.0
        self.hit_flash    = 0.0
        self.tilt         = 0.0   # Banking left/right
        self.target_tilt  = 0.0

    def handle_input(self, keys, dt):
        dx = dy = 0
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: dx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: dx += 1
        if keys[pygame.K_UP]    or keys[pygame.K_w]: dy -= 1
        if keys[pygame.K_DOWN]  or keys[pygame.K_s]: dy += 1

        # Diagonal normalisation
        if dx and dy:
            factor = 1 / math.sqrt(2)
            dx *= factor
            dy *= factor

        self.target_tilt = dx * 18  # degrees of bank

        self.x += dx * self.speed * dt
        self.y += dy * self.speed * dt

        # Clamp to screen
        self.x = clamp(self.x, self.width, BASE_W - self.width)
        self.y = clamp(self.y, self.height, BASE_H - self.height)

        # Smooth tilt
        self.tilt = lerp(self.tilt, self.target_tilt, min(1, dt * 10))

    def try_shoot(self, keys, particles) -> List[Bullet]:
        """Returns list of bullets if firing, else empty list."""
        if not (keys[pygame.K_SPACE] or keys[pygame.K_z]):
            return []
        if self.shoot_cd > 0:
            return []
        rate = self.shoot_rate * (2.0 if self.rapid_fire else 1.0)
        self.shoot_cd = 1.0 / rate

        bullets = []
        if self.ammo_type == "triple":
            for offset in [-18, 0, 18]:
                rad = math.radians(-90 + offset)
                bullets.append(Bullet(
                    self.x + offset, self.y - self.height,
                    math.cos(rad) * BULLET_SPEED,
                    math.sin(rad) * BULLET_SPEED,
                    is_player=True
                ))
        else:
            bullets.append(Bullet(
                self.x, self.y - self.height,
                0, -BULLET_SPEED,
                is_player=True
            ))
        return bullets

    def update(self, dt, particles: "ParticleSystem"):
        self.age       += dt
        self.shoot_cd   = max(0, self.shoot_cd - dt)
        self.invincible = max(0, self.invincible - dt)
        self.hit_flash  = max(0, self.hit_flash - dt)
        self.pulse_cd    = max(0, self.pulse_cd - dt)

        # Power-up timers
        if self.triple_timer > 0:
            self.triple_timer -= dt
            self.ammo_type = "triple"
            if self.triple_timer <= 0:
                self.ammo_type = "normal"

        if self.rapid_fire_timer > 0:
            self.rapid_fire_timer -= dt
            self.rapid_fire = True
            if self.rapid_fire_timer <= 0:
                self.rapid_fire = False

        # Emit engine thrust particles
        particles.emit_thrust(self.x, self.y + self.height)

    def try_pulse(self, keys) -> bool:
        """Trigger a radial defensive pulse (cooldown-gated)."""
        if not keys[pygame.K_x]:
            return False
        if self.pulse_cd > 0:
            return False
        self.pulse_cd = self.pulse_max_cd
        return True

    def take_damage(self, amount):
        if self.invincible > 0:
            return
        # Shield absorbs first
        if self.shield_hp > 0:
            absorbed = min(self.shield_hp, amount)
            self.shield_hp -= absorbed
            amount -= absorbed
        if amount > 0:
            self.hp        -= amount
            self.hit_flash  = 0.15
            self.invincible = self.invincible_cd
            if self.hp <= 0:
                self.hp    = 0
                self.alive = False

    def apply_powerup(self, kind: PowerUpType):
        if kind == PowerUpType.HEALTH:
            self.hp = min(self.max_hp, self.hp + 40)
        elif kind == PowerUpType.SHIELD:
            self.shield_hp = self.max_shield
        elif kind == PowerUpType.RAPID_FIRE:
            self.rapid_fire_timer = 6.0
        elif kind == PowerUpType.TRIPLE:
            self.triple_timer = 8.0

    def draw(self, surface):
        # Blink when invincible
        if self.invincible > 0 and int(self.age * 10) % 2 == 0:
            return

        cx, cy = int(self.x), int(self.y)
        color = C_WHITE if self.hit_flash > 0 else C_PLAYER

        # Build ship polygon (accounting for tilt)
        def pt(lx, ly):
            # Simple tilt: shear x by tilt factor
            shear = self.tilt / 40
            return (cx + lx + ly * shear, cy + ly)

        hull = [
            pt(0,   -self.height),       # Nose
            pt(-8,  -self.height + 10),
            pt(-self.width, self.height),  # Left wing tip
            pt(-6,  self.height - 10),
            pt(0,   self.height - 4),    # Centre base
            pt(6,   self.height - 10),
            pt(self.width, self.height),   # Right wing tip
            pt(8,  -self.height + 10),
        ]
        pygame.draw.polygon(surface, color, hull)
        pygame.draw.polygon(surface, C_PLAYER_DK, hull, 2)

        # Cockpit window
        pygame.draw.ellipse(surface, C_PLAYER_DK,
            (cx - 5, cy - self.height + 12, 10, 14))
        pygame.draw.ellipse(surface, (180, 240, 255),
            (cx - 3, cy - self.height + 14, 6, 8))

        # Shield bubble
        if self.shield_hp > 0:
            ratio  = self.shield_hp / self.max_shield
            radius = int(self.width * 1.8 * ratio + self.width * 0.4)
            s = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
            alpha = int(80 * ratio)
            pygame.draw.circle(s, (*C_SHIELD, alpha), (radius + 2, radius + 2), radius)
            pygame.draw.circle(s, (*C_SHIELD, 160), (radius + 2, radius + 2), radius, 2)
            surface.blit(s, (cx - radius - 2, cy - radius - 2))

    @property
    def rect(self):
        hw, hh = self.width - 4, self.height - 4
        return pygame.Rect(self.x - hw, self.y - hh, hw * 2, hh * 2)


# ─────────────────────────────────────────────────────────────
# UI / HUD
# ─────────────────────────────────────────────────────────────

class UI:
    """Renders all heads-up display elements and screen overlays."""

    def __init__(self):
        pygame.font.init()
        self.font_title  = pygame.font.SysFont("consolas,monospace", 48, bold=True)
        self.font_large  = pygame.font.SysFont("consolas,monospace", 28, bold=True)
        self.font_medium = pygame.font.SysFont("consolas,monospace", 20)
        self.font_small  = pygame.font.SysFont("consolas,monospace", 14)
        self.font_tiny   = pygame.font.SysFont("consolas,monospace", 11)

        # Score pop animation
        self.score_pop   = 0.0
        self.score_flash = C_SCORE

    def draw_health_bar(self, surface, player: Player):
        """Draw player HP bar and shield bar at bottom of screen."""
        BAR_W, BAR_H = 160, 12
        x, y = 10, BASE_H - 28

        # HP background
        pygame.draw.rect(surface, (60, 0, 0), (x, y, BAR_W, BAR_H), border_radius=4)
        hp_ratio = player.hp / player.max_hp
        if hp_ratio > 0:
            hp_color = (
                int(lerp(220, 60,  1 - hp_ratio)),
                int(lerp(60,  220, hp_ratio)),
                60
            )
            pygame.draw.rect(surface, hp_color,
                (x, y, int(BAR_W * hp_ratio), BAR_H), border_radius=4)
        pygame.draw.rect(surface, C_WHITE, (x, y, BAR_W, BAR_H), 1, border_radius=4)
        label = self.font_tiny.render("HP", True, C_WHITE)
        surface.blit(label, (x + BAR_W + 4, y))

        # Shield bar
        if player.max_shield > 0:
            sy = y - 16
            pygame.draw.rect(surface, (0, 30, 80), (x, sy, BAR_W, 8), border_radius=3)
            sh_ratio = player.shield_hp / player.max_shield
            if sh_ratio > 0:
                pygame.draw.rect(surface, C_SHIELD,
                    (x, sy, int(BAR_W * sh_ratio), 8), border_radius=3)
            pygame.draw.rect(surface, C_WHITE, (x, sy, BAR_W, 8), 1, border_radius=3)
            sl = self.font_tiny.render("SH", True, C_WHITE)
            surface.blit(sl, (x + BAR_W + 4, sy - 1))

    def draw_score(self, surface, score, high_score, dt, multiplier=1, combo_time=0.0):
        """Draw score and high score with pop animation."""
        self.score_pop = max(0, self.score_pop - dt * 4)
        scale = 1.0 + self.score_pop * 0.3
        score_txt = f"{score:08d}"

        # Score
        img = self.font_large.render(score_txt, True, C_SCORE)
        if scale != 1.0:
            w, h = img.get_size()
            img = pygame.transform.scale(img, (int(w * scale), int(h * scale)))
        r = img.get_rect(topright=(BASE_W - 8, 8))
        surface.blit(img, r)

        # High score
        if high_score > 0:
            hs = self.font_tiny.render(f"HI {high_score:08d}", True, (160, 140, 100))
            surface.blit(hs, hs.get_rect(topright=(BASE_W - 8, 36)))

        # Combo multiplier indicator
        if multiplier > 1:
            col = (255, 220, 90)
            combo_txt = self.font_medium.render(f"x{multiplier} COMBO", True, col)
            surface.blit(combo_txt, combo_txt.get_rect(topright=(BASE_W - 8, 56)))
            if combo_time > 0:
                ratio = clamp(combo_time / COMBO_WINDOW, 0, 1)
                bar_w = 100
                bx, by = BASE_W - 8 - bar_w, 80
                pygame.draw.rect(surface, (35, 35, 35), (bx, by, bar_w, 7), border_radius=3)
                pygame.draw.rect(surface, col, (bx, by, int(bar_w * ratio), 7), border_radius=3)
                pygame.draw.rect(surface, C_WHITE, (bx, by, bar_w, 7), 1, border_radius=3)

    def draw_powerup_timers(self, surface, player: Player):
        """Show active power-up countdown bars."""
        x, y = 10, BASE_H - 60
        timers = []
        if player.triple_timer > 0:
            timers.append(("3X", player.triple_timer, 8.0, POWERUP_COLORS[PowerUpType.TRIPLE]))
        if player.rapid_fire_timer > 0:
            timers.append(("RF", player.rapid_fire_timer, 6.0, POWERUP_COLORS[PowerUpType.RAPID_FIRE]))
        for label, t, max_t, col in timers:
            ratio = t / max_t
            pygame.draw.rect(surface, (30, 30, 30), (x, y, 80, 8), border_radius=3)
            pygame.draw.rect(surface, col, (x, y, int(80 * ratio), 8), border_radius=3)
            pygame.draw.rect(surface, C_WHITE, (x, y, 80, 8), 1, border_radius=3)
            lbl = self.font_tiny.render(label, True, col)
            surface.blit(lbl, (x + 84, y - 1))
            y -= 14

        # Defensive pulse cooldown
        ratio = 1.0 - (player.pulse_cd / player.pulse_max_cd if player.pulse_max_cd > 0 else 0)
        ratio = clamp(ratio, 0, 1)
        pygame.draw.rect(surface, (30, 30, 30), (x, y, 80, 8), border_radius=3)
        pygame.draw.rect(surface, (80, 210, 255), (x, y, int(80 * ratio), 8), border_radius=3)
        pygame.draw.rect(surface, C_WHITE, (x, y, 80, 8), 1, border_radius=3)
        lbl = self.font_tiny.render("PULSE", True, (80, 210, 255))
        surface.blit(lbl, (x + 84, y - 1))

    def draw_wave_info(self, surface, wave, enemy_count):
        """Small wave indicator top-left."""
        txt = f"WAVE {wave}  ENEMIES {enemy_count}"
        img = self.font_tiny.render(txt, True, (120, 120, 160))
        surface.blit(img, (8, 8))

    def draw_menu(self, surface, high_score, tick):
        """Full start-menu overlay."""
        # Dim background
        dim = pygame.Surface((BASE_W, BASE_H), pygame.SRCALPHA)
        dim.fill((0, 0, 15, 180))
        surface.blit(dim, (0, 0))

        cy = BASE_H // 2
        # Title
        pulse = abs(math.sin(tick * 1.5)) * 30
        title_color = (80 + int(pulse), 220, 255)
        draw_text_centered(surface, "NOVA SIEGE",
                           self.font_title, title_color, BASE_W // 2, cy - 120)

        # Subtitle
        draw_text_centered(surface, "ARCADE SPACE SHOOTER",
                           self.font_small, (120, 180, 200), BASE_W // 2, cy - 70)

        # Controls
        controls = [
            ("MOVE",  "WASD / ARROW KEYS"),
            ("SHOOT", "SPACE"),
            ("PULSE", "X (clears bullets)"),
        ]
        for i, (action, key) in enumerate(controls):
            draw_text_centered(surface, f"{action:<7} {key}",
                               self.font_small, (160, 160, 190), BASE_W // 2, cy - 20 + i * 22)

        # Blink start prompt
        if int(tick * 2) % 2 == 0:
            draw_text_centered(surface, "PRESS SPACE TO START",
                               self.font_medium, C_GOLD, BASE_W // 2, cy + 60)

        # High score
        if high_score > 0:
            draw_text_centered(surface, f"HIGH SCORE  {high_score:08d}",
                               self.font_small, C_SCORE, BASE_W // 2, cy + 100)

        # Enemy preview (decorative)
        self._draw_enemy_icons(surface, cy + 150)

    def _draw_enemy_icons(self, surface, y):
        """Show enemy type icons as decoration on menu."""
        configs = [
            (BASE_W // 2 - 80, C_ENEMY_A, "SCOUT"),
            (BASE_W // 2,      C_ENEMY_B, "HUNTER"),
            (BASE_W // 2 + 80, C_ENEMY_C, "TANK"),
        ]
        for (x, col, lbl) in configs:
            pygame.draw.circle(surface, col, (x, y), 10)
            pygame.draw.circle(surface, C_WHITE, (x, y), 10, 1)
            t = self.font_tiny.render(lbl, True, col)
            surface.blit(t, t.get_rect(centerx=x, top=y + 14))

    def draw_game_over(self, surface, score, high_score, new_record, tick):
        """Game over overlay."""
        dim = pygame.Surface((BASE_W, BASE_H), pygame.SRCALPHA)
        dim.fill((20, 0, 0, 200))
        surface.blit(dim, (0, 0))

        cy = BASE_H // 2 - 40

        draw_text_centered(surface, "GAME OVER",
                           self.font_title, C_RED, BASE_W // 2, cy - 60)
        draw_text_centered(surface, f"SCORE  {score:08d}",
                           self.font_large, C_SCORE, BASE_W // 2, cy)

        if new_record:
            pulse = abs(math.sin(tick * 3))
            col = (
                int(lerp(255, 200, pulse)),
                int(lerp(200, 255, pulse)),
                50
            )
            draw_text_centered(surface, "★  NEW HIGH SCORE  ★",
                               self.font_medium, col, BASE_W // 2, cy + 40)
        else:
            draw_text_centered(surface, f"BEST   {high_score:08d}",
                               self.font_medium, (160, 140, 100), BASE_W // 2, cy + 40)

        if int(tick * 2) % 2 == 0:
            draw_text_centered(surface, "PRESS SPACE TO RESTART",
                               self.font_medium, C_GOLD, BASE_W // 2, cy + 90)

    def pop_score(self):
        """Trigger score pop animation."""
        self.score_pop = 1.0


# ─────────────────────────────────────────────────────────────
# ENEMY SPAWNER
# ─────────────────────────────────────────────────────────────

class EnemySpawner:
    """
    Manages enemy wave difficulty.
    Spawn rate and enemy tier probabilities scale with score.
    """

    def __init__(self):
        self.spawn_cd = ENEMY_SPAWN_CD
        self.timer    = 0.0
        self.wave     = 1

    def update(self, dt, score) -> Optional[EnemyType]:
        """Returns an EnemyType to spawn, or None."""
        # Difficulty: reduce spawn cooldown as score rises
        difficulty = min(score / 5000, 1.0)
        current_cd = lerp(ENEMY_SPAWN_CD, 0.6, difficulty)
        self.wave   = 1 + int(score / 2000)

        self.timer += dt
        if self.timer >= current_cd:
            self.timer = 0.0
            return self._pick_enemy_type(difficulty)
        return None

    def _pick_enemy_type(self, difficulty) -> EnemyType:
        r = random.random()
        # Early game: mostly scouts. Late game: more hunters and tanks.
        tank_chance   = difficulty * 0.20
        hunter_chance = 0.15 + difficulty * 0.35
        if r < tank_chance:
            return EnemyType.TANK
        elif r < tank_chance + hunter_chance:
            return EnemyType.HUNTER
        return EnemyType.SCOUT


# ─────────────────────────────────────────────────────────────
# MAIN GAME CONTROLLER
# ─────────────────────────────────────────────────────────────

class Game:
    """
    Master game controller.
    Owns game state machine, all entities, and the main game loop.
    """

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("NOVA SIEGE")

        # Responsive window — user can resize; we blit a scaled surface
        self.window = pygame.display.set_mode(
            (WIN_W, WIN_H), pygame.RESIZABLE | pygame.SCALED
        )
        # Internal render surface at fixed base resolution
        self.surface = pygame.Surface((BASE_W, BASE_H))
        self.clock   = pygame.time.Clock()

        self.sound  = SoundManager()
        self.ui     = UI()

        self.state      = GameState.MENU
        self.high_score = 0
        self.tick       = 0.0      # Monotonic time for animations

        self._init_session()

    def _init_session(self):
        """Reset all per-session game objects."""
        self.player    = Player()
        self.enemies:  List[Enemy]   = []
        self.bullets:  List[Bullet]  = []
        self.powerups: List[PowerUp] = []
        self.particles = ParticleSystem()
        self.stars     = StarField()
        self.spawner   = EnemySpawner()
        self.score     = 0
        self.new_record = False
        self.combo_chain = 0
        self.combo_timer = 0.0
        self.multiplier  = 1

    # ── Main loop ─────────────────────────────────────────────

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)  # Cap dt to avoid spiral of death after lag
            self.tick += dt

            self._handle_events()

            if self.state == GameState.PLAYING:
                self._update(dt)
            elif self.state == GameState.MENU:
                self.stars.update(dt)
            elif self.state == GameState.GAME_OVER:
                self.stars.update(dt)
                self.particles.update(dt)

            self._draw()

    # ── Event handling ────────────────────────────────────────

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.state == GameState.PLAYING:
                        pygame.quit(); sys.exit()
                if event.key == pygame.K_SPACE:
                    if self.state == GameState.MENU:
                        self._start_game()
                    elif self.state == GameState.GAME_OVER:
                        self._start_game()
                if event.key == pygame.K_p and self.state == GameState.PLAYING:
                    self.state = GameState.PAUSED
                elif event.key == pygame.K_p and self.state == GameState.PAUSED:
                    self.state = GameState.PLAYING

    def _start_game(self):
        self._init_session()
        self.state = GameState.PLAYING

    # ── Update ────────────────────────────────────────────────

    def _update(self, dt):
        keys = pygame.key.get_pressed()

        # Update background
        self.stars.update(dt)

        # Player
        self.player.handle_input(keys, dt)
        self.combo_timer = max(0, self.combo_timer - dt)
        if self.combo_timer <= 0 and self.multiplier > 1:
            self._break_combo()

        new_bullets = self.player.try_shoot(keys, self.particles)
        if new_bullets:
            self.sound.play("shoot", 0.4)
        self.bullets.extend(new_bullets)

        if self.player.try_pulse(keys):
            self._trigger_pulse()

        self.player.update(dt, self.particles)

        # Enemy spawning
        spawn_type = self.spawner.update(dt, self.score)
        if spawn_type is not None:
            x = random.uniform(30, BASE_W - 30)
            self.enemies.append(Enemy(x, -40, spawn_type, self.player))

        # Update enemies
        for enemy in self.enemies:
            new_e_bullets = enemy.update(dt)
            self.bullets.extend(new_e_bullets)

        # Update bullets
        for b in self.bullets:
            b.update(dt)

        # Update power-ups
        for p in self.powerups:
            p.update(dt)

        # Update particles
        self.particles.update(dt)

        # Collision detection
        self._check_collisions()

        # Prune dead objects
        self.enemies  = [e for e in self.enemies  if e.alive]
        self.bullets  = [b for b in self.bullets  if b.alive]
        self.powerups = [p for p in self.powerups if p.alive]

        # Player death
        if not self.player.alive:
            self._on_player_death()

    def _check_collisions(self):
        player_rect = self.player.rect

        for b in self.bullets:
            if not b.alive:
                continue
            # Player bullets hit enemies
            if b.is_player:
                for e in self.enemies:
                    if e.alive and b.rect.colliderect(e.rect):
                        e.take_damage(b.damage)
                        b.alive = False
                        self.particles.emit_hit(b.x, b.y)
                        self.sound.play("hit", 0.5)
                        if not e.alive:
                            self._on_enemy_killed(e)
                        break
            # Enemy bullets hit player
            else:
                if b.rect.colliderect(player_rect):
                    hp_before = self.player.hp + self.player.shield_hp
                    self.player.take_damage(b.damage)
                    if self.player.hp + self.player.shield_hp < hp_before:
                        self._break_combo()
                    b.alive = False
                    self.particles.emit_hit(b.x, b.y)
                    self.sound.play("hit", 0.5)

        # Enemy body collision with player
        for e in self.enemies:
            if e.alive and e.rect.colliderect(player_rect):
                hp_before = self.player.hp + self.player.shield_hp
                self.player.take_damage(25)
                if self.player.hp + self.player.shield_hp < hp_before:
                    self._break_combo()
                e.alive = False
                self.particles.emit_explosion(e.x, e.y, e.color)
                self.sound.play("explosion", 0.7)

        # Power-up collection
        for p in self.powerups:
            if p.alive and p.rect.colliderect(player_rect):
                self.player.apply_powerup(p.kind)
                p.alive = False
                self.particles.emit_explosion(p.x, p.y, p.color, count=12, speed_range=(30, 100))
                self.sound.play("powerup", 0.8)

    def _on_enemy_killed(self, enemy: Enemy):
        self.combo_chain += 1
        self.multiplier = min(5, 1 + self.combo_chain // 3)
        self.combo_timer = COMBO_WINDOW
        self.score += enemy.score * self.multiplier
        self.ui.pop_score()
        self.particles.emit_explosion(enemy.x, enemy.y, enemy.color, count=20)
        self.sound.play("explosion", 0.6)
        # Chance to drop power-up
        if random.random() < POWERUP_CHANCE:
            self.powerups.append(PowerUp(enemy.x, enemy.y))

    def _break_combo(self):
        self.combo_chain = 0
        self.combo_timer = 0.0
        self.multiplier = 1

    def _trigger_pulse(self):
        # Visual ring burst around the ship.
        self.particles.emit_explosion(self.player.x, self.player.y, (80, 210, 255), count=28, speed_range=(80, 240))

        # Clear nearby enemy bullets.
        for b in self.bullets:
            if b.alive and not b.is_player and distance(b.x, b.y, self.player.x, self.player.y) <= PULSE_RADIUS:
                b.alive = False
                self.particles.emit_hit(b.x, b.y)

        # Damage nearby enemies.
        for e in self.enemies:
            if e.alive and distance(e.x, e.y, self.player.x, self.player.y) <= PULSE_RADIUS:
                e.take_damage(35)
                if not e.alive:
                    self._on_enemy_killed(e)

    def _on_player_death(self):
        self.particles.emit_explosion(
            self.player.x, self.player.y, C_PLAYER, count=40, speed_range=(60, 240)
        )
        self.sound.play("gameover", 0.9)
        if self.score > self.high_score:
            self.high_score = self.score
            self.new_record = True
        else:
            self.new_record = False
        self.state = GameState.GAME_OVER

    # ── Draw ──────────────────────────────────────────────────

    def _draw(self):
        s = self.surface
        s.fill(C_BG)

        # Background
        self.stars.draw(s)

        if self.state == GameState.MENU:
            self.ui.draw_menu(s, self.high_score, self.tick)

        elif self.state in (GameState.PLAYING, GameState.PAUSED):
            # Game world
            for p in self.powerups:
                p.draw(s, self.ui.font_small)
            for e in self.enemies:
                e.draw(s)
            self.particles.draw(s)
            if self.player.alive:
                self.player.draw(s)
            for b in self.bullets:
                b.draw(s)

            # HUD
            self.ui.draw_health_bar(s, self.player)
            self.ui.draw_score(s, self.score, self.high_score, 0, self.multiplier, self.combo_timer)
            self.ui.draw_powerup_timers(s, self.player)
            self.ui.draw_wave_info(s, self.spawner.wave, len(self.enemies))

            if self.state == GameState.PAUSED:
                dim = pygame.Surface((BASE_W, BASE_H), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 140))
                s.blit(dim, (0, 0))
                draw_text_centered(s, "PAUSED", self.ui.font_title,
                                   C_WHITE, BASE_W // 2, BASE_H // 2)
                draw_text_centered(s, "P to resume  |  ESC to quit",
                                   self.ui.font_small, (160, 160, 160),
                                   BASE_W // 2, BASE_H // 2 + 50)

        elif self.state == GameState.GAME_OVER:
            # Faded star background with particles
            self.stars.draw(s)
            self.particles.draw(s)
            self.ui.draw_game_over(s, self.score, self.high_score,
                                   self.new_record, self.tick)

        # Blit internal surface to window (handles SCALED flag automatically)
        self.window.blit(s, (0, 0))
        pygame.display.flip()


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    game = Game()
    game.run()


# ─────────────────────────────────────────────────────────────
# EXTENSION IDEAS
# ─────────────────────────────────────────────────────────────
#
# 1. BOSS FIGHTS
#    Every 5 waves spawn a boss enemy with a multi-phase health bar,
#    unique movement patterns (spiral, charge, teleport), and
#    complex bullet patterns (radial bursts, aimed spreads).
#    Add a dramatic entrance animation and custom boss music track.
#
# 2. UPGRADE SHOP BETWEEN WAVES
#    After each wave ends (clear all enemies), open a shop overlay
#    offering 3 random permanent upgrades:
#      - Engine Boost (+15% move speed)
#      - Overcharge (+25% bullet damage)
#      - Armour Plating (+30 max HP)
#      - Auto-Repair (regen 2 HP/s)
#    Upgrades purchased with "credits" earned by killing enemies.
#
# 3. PROCEDURAL LEVEL BACKGROUNDS
#    Replace the static star field with procedurally generated
#    space environments — nebulae, asteroid belts, planet surfaces —
#    using layered Perlin-noise surfaces and sprite sheets.
#    Each zone changes visual theme and introduces environment hazards
#    (asteroids that block bullets, ion storms that reverse controls).
