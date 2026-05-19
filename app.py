"""
🌿 생태계 시뮬레이션 — Python OOP + Gradio 6
포식자(늑대) ↔ 피식자(토끼) ↔ 식물의 Lotka-Volterra 생태계
"""

import io
import math
import os
import random
from abc import ABC, abstractmethod

import gradio as gr
import matplotlib
import matplotlib.pyplot as plt
from PIL import Image as PILImage

matplotlib.use("Agg")

# ── 한글 폰트 자동 감지 (macOS / Linux / Windows) ──
import sys
from matplotlib import font_manager as _fm

_KO_CANDIDATES = [
    "Apple SD Gothic Neo", "AppleGothic",          # macOS
    "NanumGothic", "NanumBarunGothic",              # Linux (설치 시)
    "Malgun Gothic", "맑은 고딕",                   # Windows
    "Noto Sans CJK KR", "Noto Sans KR",            # 범용
]
_found = next(
    (f.name for f in _fm.fontManager.ttflist
     if any(c in f.name for c in _KO_CANDIDATES)),
    None
)
if _found:
    plt.rcParams["font.family"] = _found
else:
    # 한글 폰트 없으면 경고 억제 후 영문만 사용
    import warnings, matplotlib
    warnings.filterwarnings("ignore", category=UserWarning,
                            module="matplotlib")
    plt.rcParams["font.family"] = "DejaVu Sans"

plt.rcParams["axes.unicode_minus"] = False


# ══════════════════════════════════════════════════════
# ①  추상 기반 클래스
# ══════════════════════════════════════════════════════

class Entity(ABC):
    _id_counter = 0

    def __init__(self, name, hp, max_hp, x, y):
        Entity._id_counter += 1
        self.id     = Entity._id_counter
        self.name   = name
        self.hp     = float(hp)
        self.max_hp = float(max_hp)
        self.x      = float(x)
        self.y      = float(y)
        self.age    = 0
        self.alive  = True

    def distance_to(self, other):
        return math.hypot(self.x - other.x, self.y - other.y)

    def take_damage(self, dmg):
        self.hp = max(0.0, self.hp - dmg)
        if self.hp == 0:
            self.alive = False

    def heal(self, amt):
        self.hp = min(self.max_hp, self.hp + amt)

    def is_alive(self):
        return self.alive and self.hp > 0

    @staticmethod
    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    @abstractmethod
    def step(self, eco): ...

    @abstractmethod
    def emoji(self): ...

    @abstractmethod
    def color(self): ...


# ══════════════════════════════════════════════════════
# ②  식물
# ══════════════════════════════════════════════════════

class Plant(Entity):
    MAX_AGE  = 250
    EGAIN    = 0.4
    REPRO_P  = 0.04
    SPREAD   = 4

    def __init__(self, x, y):
        super().__init__("Plant", 10, 10, x, y)
        self.energy = random.uniform(5, 15)

    def step(self, eco):
        self.age += 1
        self.energy = min(20, self.energy + self.EGAIN)
        if self.age >= self.MAX_AGE:
            self.alive = False
            return
        if random.random() < self.REPRO_P and len(eco.plants) < eco.max_plants:
            nx = self._clamp(self.x + random.uniform(-self.SPREAD, self.SPREAD), 0, eco.size-1)
            ny = self._clamp(self.y + random.uniform(-self.SPREAD, self.SPREAD), 0, eco.size-1)
            eco.queue.append(Plant(nx, ny))

    def emoji(self): return "🌿"
    def color(self):  return "#4caf50"


# ══════════════════════════════════════════════════════
# ③  동물 추상 클래스
# ══════════════════════════════════════════════════════

class Animal(Entity, ABC):
    def __init__(self, name, hp, max_hp, x, y, speed, energy, max_energy):
        super().__init__(name, hp, max_hp, x, y)
        self.speed      = speed
        self.energy     = float(energy)
        self.max_energy = float(max_energy)
        self.repro_cd   = 0

    def _move_to(self, tx, ty, size):
        dx, dy = tx - self.x, ty - self.y
        dist   = math.hypot(dx, dy) or 1e-9
        s      = min(self.speed, dist)
        self.x = self._clamp(self.x + s*dx/dist, 0, size-1)
        self.y = self._clamp(self.y + s*dy/dist, 0, size-1)
        self._burn(0.4)

    def move_toward(self, tx, ty, eco): self._move_to(tx, ty, eco.size)
    def move_away(self, tx, ty, eco):   self._move_to(2*self.x - tx, 2*self.y - ty, eco.size)

    def wander(self, eco):
        a = random.uniform(0, 2*math.pi)
        self.x = self._clamp(self.x + self.speed*math.cos(a), 0, eco.size-1)
        self.y = self._clamp(self.y + self.speed*math.sin(a), 0, eco.size-1)
        self._burn(0.2)

    def _burn(self, amt):
        self.energy = max(0, self.energy - amt)
        if self.energy == 0:
            self.take_damage(1)

    def nearest(self, pool):
        alive = [e for e in pool if e.is_alive() and e is not self]
        return min(alive, key=lambda e: self.distance_to(e), default=None)

    def in_range(self, other, r):
        return self.distance_to(other) <= r


# ══════════════════════════════════════════════════════
# ④  토끼
# ══════════════════════════════════════════════════════

class Rabbit(Animal):
    def __init__(self, x, y):
        super().__init__("Rabbit", 30, 30, x, y, 2.0, 40, 60)

    def step(self, eco):
        self.age += 1
        self.repro_cd = max(0, self.repro_cd - 1)

        wolf = self.nearest(eco.wolves)
        if wolf and self.in_range(wolf, 10):
            self.move_away(wolf.x, wolf.y, eco)
        else:
            plant = self.nearest(eco.plants)
            if plant: self.move_toward(plant.x, plant.y, eco)
            else:     self.wander(eco)

        for p in eco.plants:
            if p.is_alive() and self.in_range(p, 2.5):
                self.energy = min(self.max_energy, self.energy + p.energy*0.6)
                self.heal(8)
                p.alive = False
                eco.log(f"🐰 토끼#{self.id} 풀을 먹었습니다")
                break

        if self.repro_cd == 0 and self.energy > 25 and len(eco.rabbits) < eco.max_prey:
            partner = self.nearest(eco.rabbits)
            if partner and self.in_range(partner, 6) and random.random() < 0.12:
                eco.queue.append(Rabbit(
                    self._clamp(self.x + random.uniform(-3,3), 0, eco.size-1),
                    self._clamp(self.y + random.uniform(-3,3), 0, eco.size-1),
                ))
                self.repro_cd = 25
                self.energy  -= 12
                eco.log(f"🐣 토끼#{self.id} 새끼를 낳았습니다!")

        self._burn(0.1)
        if self.age >= 160: self.alive = False

    def emoji(self): return "🐰"
    def color(self):  return "#29b6f6"


# ══════════════════════════════════════════════════════
# ⑤  늑대
# ══════════════════════════════════════════════════════

class Wolf(Animal):
    def __init__(self, x, y):
        super().__init__("Wolf", 70, 70, x, y, 2.8, 80, 100)

    def step(self, eco):
        self.age += 1
        self.repro_cd = max(0, self.repro_cd - 1)

        rabbit = self.nearest(eco.rabbits)
        if rabbit and self.in_range(rabbit, 14):
            self.move_toward(rabbit.x, rabbit.y, eco)
        else:
            self.wander(eco)

        for r in eco.rabbits:
            if r.is_alive() and self.in_range(r, 3):
                if random.random() < 0.55:
                    self.energy = min(self.max_energy, self.energy + 45)
                    self.heal(20)
                    r.alive = False
                    eco.log(f"🐺 늑대#{self.id} → 토끼#{r.id} 사냥!")
                break

        if self.repro_cd == 0 and self.energy > 55 and len(eco.wolves) < eco.max_pred:
            partner = self.nearest(eco.wolves)
            if partner and self.in_range(partner, 8) and random.random() < 0.06:
                eco.queue.append(Wolf(
                    self._clamp(self.x + random.uniform(-4,4), 0, eco.size-1),
                    self._clamp(self.y + random.uniform(-4,4), 0, eco.size-1),
                ))
                self.repro_cd = 50
                self.energy  -= 25
                eco.log(f"🐺 늑대#{self.id} 새끼를 낳았습니다!")

        self._burn(0.6)
        if self.age >= 200: self.alive = False

    def emoji(self): return "🐺"
    def color(self):  return "#ef5350"


# ══════════════════════════════════════════════════════
# ⑥  생태계 관리자
# ══════════════════════════════════════════════════════

class Ecosystem:
    def __init__(self, size, n_plants, n_prey, n_pred):
        self.size      = int(size)
        self.tick      = 0
        self.max_plants = 200
        self.max_prey   = 150
        self.max_pred   = 40
        self.queue = []
        self._log  = []

        r = lambda: (random.uniform(0, self.size), random.uniform(0, self.size))
        self.plants  = [Plant (*r()) for _ in range(int(n_plants))]
        self.rabbits = [Rabbit(*r()) for _ in range(int(n_prey))]
        self.wolves  = [Wolf  (*r()) for _ in range(int(n_pred))]

        self.hist = {"tick":[], "plants":[], "rabbits":[], "wolves":[]}

    def step(self, n=1):
        for _ in range(n):
            self.tick += 1
            self.queue.clear()

            for e in list(self.plants):
                if e.is_alive(): e.step(self)
            for e in list(self.rabbits):
                if e.is_alive(): e.step(self)
            for e in list(self.wolves):
                if e.is_alive(): e.step(self)

            self.plants  = [e for e in self.plants  if e.is_alive()]
            self.rabbits = [e for e in self.rabbits if e.is_alive()]
            self.wolves  = [e for e in self.wolves  if e.is_alive()]

            for e in self.queue:
                if isinstance(e, Plant):   self.plants.append(e)
                elif isinstance(e, Rabbit): self.rabbits.append(e)
                elif isinstance(e, Wolf):   self.wolves.append(e)

            self.hist["tick"].append(self.tick)
            self.hist["plants"].append(len(self.plants))
            self.hist["rabbits"].append(len(self.rabbits))
            self.hist["wolves"].append(len(self.wolves))
            if len(self.hist["tick"]) > 300:
                for k in self.hist: self.hist[k] = self.hist[k][-300:]

    def add(self, kind, n):
        for _ in range(int(n)):
            x = random.uniform(0, self.size)
            y = random.uniform(0, self.size)
            if kind == "plant":   self.plants.append(Plant(x, y))
            elif kind == "rabbit": self.rabbits.append(Rabbit(x, y))
            elif kind == "wolf":   self.wolves.append(Wolf(x, y))

    def log(self, msg):
        self._log.append(f"[T{self.tick:04d}] {msg}")
        if len(self._log) > 80: self._log = self._log[-80:]

    def recent_log(self, n=20):
        return "\n".join(reversed(self._log[-n:]))

    @property
    def stats(self):
        return dict(tick=self.tick, plants=len(self.plants),
                    rabbits=len(self.rabbits), wolves=len(self.wolves))

    def is_collapsed(self):
        return len(self.rabbits) == 0 and len(self.wolves) == 0


# ══════════════════════════════════════════════════════
# ⑦  시각화
# ══════════════════════════════════════════════════════

BG    = "#0d1117"
PANEL = "#161b22"
BORD  = "#30363d"


def _to_pil(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return PILImage.open(buf).copy()


def _base(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)
    for sp in ax.spines.values(): sp.set_edgecolor(BORD)
    ax.tick_params(colors="#8b949e", labelsize=9)
    return fig, ax


def render_map(eco):
    plt.close("all")
    fig, ax = _base(6, 6)
    ax.set_xlim(0, eco.size)
    ax.set_ylim(0, eco.size)
    ax.set_aspect("equal")
    ax.set_title(f"Ecosystem Map  —  Turn {eco.tick}",
                 color="#e6edf3", fontsize=13, pad=8)

    if eco.plants:
        ax.scatter([p.x for p in eco.plants], [p.y for p in eco.plants],
                   c="#4caf50", marker="^", s=22, alpha=0.75,
                   edgecolors="none", zorder=1, label=f"Plant {len(eco.plants)}")
    if eco.rabbits:
        ax.scatter([r.x for r in eco.rabbits], [r.y for r in eco.rabbits],
                   c="#29b6f6", marker="o", s=55, alpha=0.90,
                   edgecolors="none", zorder=2, label=f"Rabbit {len(eco.rabbits)}")
    if eco.wolves:
        ax.scatter([w.x for w in eco.wolves], [w.y for w in eco.wolves],
                   c="#ef5350", marker="D", s=90, alpha=0.95,
                   edgecolors="none", zorder=3, label=f"Wolf {len(eco.wolves)}")

    ax.legend(loc="upper right", facecolor=PANEL, edgecolor=BORD,
              labelcolor="white", fontsize=10, framealpha=0.85)
    fig.tight_layout(pad=0.5)
    return _to_pil(fig)


def render_chart(eco):
    plt.close("all")
    fig, ax = _base(9, 3.5)
    h = eco.hist
    if not h["tick"]:
        ax.text(0.5, 0.5, "Press [Run] to start",
                ha="center", va="center", color="#8b949e",
                fontsize=13, transform=ax.transAxes)
        fig.tight_layout(pad=0.5)
        return _to_pil(fig)

    t = h["tick"]
    for key, col, lbl in [("plants","#4caf50","Plant"),
                           ("rabbits","#29b6f6","Rabbit"),
                           ("wolves","#ef5350","Wolf")]:
        ax.fill_between(t, h[key], alpha=0.13, color=col)
        ax.plot(t, h[key], color=col, lw=2.0, label=lbl)

    ax.set_title("Population Over Time", color="#e6edf3", fontsize=12, pad=6)
    ax.set_xlabel("Turn", color="#8b949e", fontsize=9)
    ax.set_ylabel("Count", color="#8b949e", fontsize=9)
    ax.grid(color=BORD, alpha=0.5, lw=0.5)
    ax.legend(facecolor=PANEL, edgecolor=BORD, labelcolor="white", fontsize=9)
    fig.tight_layout(pad=0.5)
    return _to_pil(fig)


def render_stats(eco):
    s = eco.stats
    status = "🔴 붕괴" if eco.is_collapsed() else "🟢 진행 중"
    rows = [("⏱ 턴", s["tick"],"#ffd666"),
            ("🌿 식물", s["plants"],"#4caf50"),
            ("🐰 토끼", s["rabbits"],"#29b6f6"),
            ("🐺 늑대", s["wolves"],"#ef5350")]
    trs = "".join(
        f"<tr><td style='padding:5px 10px;color:#8b949e'>{l}</td>"
        f"<td style='padding:5px 10px;color:{c};font-weight:700;text-align:right'>{v}</td></tr>"
        for l,v,c in rows)
    return (f"<div style='background:{PANEL};border:1px solid {BORD};"
            f"border-radius:10px;padding:14px;font-family:monospace'>"
            f"<div style='color:#e6edf3;margin-bottom:8px'>"
            f"📊 통계 <span style='float:right'>{status}</span></div>"
            f"<table width='100%' style='border-collapse:collapse'>{trs}</table></div>")


def _empty_img(msg="초기화 버튼을 먼저 눌러주세요"):
    plt.close("all")
    fig, ax = _base(6, 6)
    ax.text(0.5, 0.5, msg, ha="center", va="center",
            color="#8b949e", fontsize=13, transform=ax.transAxes)
    fig.tight_layout(pad=0.5)
    return _to_pil(fig)


def _empty_stats():
    return (f"<div style='background:{PANEL};border:1px solid {BORD};"
            f"border-radius:10px;padding:14px;color:#8b949e;"
            f"font-family:monospace'>먼저 초기화하세요</div>")


# ══════════════════════════════════════════════════════
# ⑧  전역 상태 (리스트 컨테이너 = 스레드 안전)
# ══════════════════════════════════════════════════════

_S = [None]   # _S[0] 에 Ecosystem 저장


def _all(eco):
    return render_map(eco), render_chart(eco), render_stats(eco), eco.recent_log()


def handle_init(size, n_plants, n_prey, n_pred):
    Entity._id_counter = 0
    _S[0] = Ecosystem(size, n_plants, n_prey, n_pred)
    _S[0].log("🌍 생태계가 초기화되었습니다.")
    return _all(_S[0])


def handle_step(n_steps):
    if _S[0] is None:
        return _empty_img(), _empty_img(), _empty_stats(), ""
    _S[0].step(int(n_steps))
    return _all(_S[0])


def handle_add(kind, count):
    if _S[0] is None:
        return _empty_stats(), ""
    _S[0].add(kind, count)
    _S[0].log(f"➕ {kind} {int(count)}마리 추가")
    return render_stats(_S[0]), _S[0].recent_log()


def handle_event(etype):
    eco = _S[0]
    if eco is None:
        return _empty_img(), _empty_img(), _empty_stats(), ""
    if etype == "drought" and eco.plants:
        victims = random.sample(eco.plants, min(len(eco.plants)//2, len(eco.plants)))
        for p in victims: p.alive = False
        eco.plants = [p for p in eco.plants if p.is_alive()]
        eco.log("☀️ 가뭄! 식물 절반 고사")
    elif etype == "epidemic" and eco.rabbits:
        for r in eco.rabbits: r.take_damage(20)
        eco.rabbits = [r for r in eco.rabbits if r.is_alive()]
        eco.log("🦠 토끼 전염병 발생!")
    elif etype == "hunt" and eco.wolves:
        victims = random.sample(eco.wolves, max(1, len(eco.wolves)//3))
        for w in victims: w.alive = False
        eco.wolves = [w for w in eco.wolves if w.is_alive()]
        eco.log("🏹 사냥꾼! 늑대 1/3 제거")
    return _all(eco)


# ══════════════════════════════════════════════════════
# ⑨  Gradio UI
# ══════════════════════════════════════════════════════

CSS = """
.gradio-container { background:#0d1117 !important; font-family:'Segoe UI',system-ui,sans-serif !important; }
footer { display:none !important; }
.block { background:#161b22 !important; border:1px solid #30363d !important; border-radius:10px !important; }
button.primary   { background:linear-gradient(135deg,#238636,#2ea043) !important; border:none !important; color:#fff !important; }
button.secondary { background:linear-gradient(135deg,#1158c7,#388bfd) !important; border:none !important; color:#fff !important; }
label > span { color:#8b949e !important; font-size:12px !important; }
textarea { background:#161b22 !important; color:#e6edf3 !important; border:1px solid #30363d !important; }
"""

HEADER = """
<div style='background:linear-gradient(135deg,#0d1117,#161b22);border:1px solid #30363d;
            border-radius:12px;padding:18px 24px;margin-bottom:4px'>
  <h1 style='margin:0;font-size:1.5rem;color:#e6edf3'>🌿 생태계 시뮬레이션</h1>
  <p style='margin:5px 0 0;color:#8b949e;font-size:0.85rem'>
    Python <b style='color:#52c41a'>OOP</b> 기반 포식자&ndash;피식자 생태계 &nbsp;|&nbsp;
    <code style='color:#40a9ff'>Entity &rarr; Animal &rarr; Wolf / Rabbit</code>
  </p>
</div>"""

OOP_CARD = """
<div style='background:#161b22;border:1px solid #30363d;border-radius:10px;
            padding:12px;font-family:monospace;font-size:11px;color:#8b949e;line-height:1.9'>
<span style='color:#ffd666'>📐 클래스 계층</span><br>
<span style='color:#52c41a'>Entity</span>(ABC) — id·hp·x·y·age<br>
 ├ <span style='color:#52c41a'>Plant</span>  — 광합성·번식<br>
 └ <span style='color:#40a9ff'>Animal</span>(ABC) — 이동·섭식·번식<br>
   ├ <span style='color:#40a9ff'>Rabbit</span> — 도주·초식<br>
   └ <span style='color:#ef5350'>Wolf</span>   — 추격·사냥
</div>"""


with gr.Blocks(title="생태계 시뮬레이션") as demo:
    gr.HTML(HEADER)

    with gr.Row():
        with gr.Column(scale=1, min_width=260):
            gr.HTML(OOP_CARD)

            with gr.Group():
                gr.Markdown("### ⚙️ 초기 설정")
                sl_size  = gr.Slider(20, 100, value=60, step=10, label="생태계 크기")
                sl_plant = gr.Slider(10, 150, value=60, step=10, label="초기 식물")
                sl_prey  = gr.Slider(5,   80, value=25, step=5,  label="초기 토끼")
                sl_pred  = gr.Slider(1,   20, value=6,  step=1,  label="초기 늑대")
                btn_init = gr.Button("🔄 초기화", variant="primary")

            with gr.Group():
                gr.Markdown("### ▶️ 실행")
                sl_steps = gr.Slider(1, 100, value=20, step=1, label="실행 턴 수")
                btn_step = gr.Button("▶  실행", variant="secondary")

            with gr.Group():
                gr.Markdown("### ➕ 개체 추가")
                dd_kind = gr.Dropdown(
                    choices=["plant", "rabbit", "wolf"],
                    value="rabbit", label="종류")
                sl_addN = gr.Slider(1, 30, value=5, step=1, label="추가 수")
                btn_add = gr.Button("➕ 추가")

            with gr.Group():
                gr.Markdown("### 💥 이벤트")
                btn_drought  = gr.Button("☀️ 가뭄")
                btn_epidemic = gr.Button("🦠 토끼 전염병")
                btn_hunt     = gr.Button("🏹 늑대 사냥꾼")

        with gr.Column(scale=3):
            out_stats = gr.HTML(_empty_stats())
            with gr.Row():
                out_map   = gr.Image(label="생태계 지도",  type="pil",
                                     height=460)
                out_chart = gr.Image(label="개체 수 변화", type="pil",
                                     height=460)
            out_log = gr.Textbox(label="📋 이벤트 로그", lines=8, interactive=False)

    OUTS = [out_map, out_chart, out_stats, out_log]

    btn_init.click(handle_init,
                   inputs=[sl_size, sl_plant, sl_prey, sl_pred],
                   outputs=OUTS)
    btn_step.click(handle_step, inputs=[sl_steps], outputs=OUTS)
    btn_add.click(handle_add,   inputs=[dd_kind, sl_addN],
                  outputs=[out_stats, out_log])
    btn_drought.click( lambda: handle_event("drought"),  outputs=OUTS)
    btn_epidemic.click(lambda: handle_event("epidemic"), outputs=OUTS)
    btn_hunt.click(    lambda: handle_event("hunt"),     outputs=OUTS)


# ══════════════════════════════════════════════════════
# ⑩  진입점
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    port      = int(os.environ.get("PORT", 7860))
    on_render = bool(os.environ.get("RENDER"))
    host      = "0.0.0.0" if on_render else "127.0.0.1"

    print(f"\n{'='*46}")
    print(f"  🌿 생태계 시뮬레이션")
    print(f"  👉 http://localhost:{port}")
    print(f"{'='*46}\n")

    demo.launch(
        server_name=host,
        server_port=port,
        inbrowser=False,
        share=False,
        css=CSS,
    )