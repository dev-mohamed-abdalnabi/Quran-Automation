"""مكتبة برومتات الصور للفيديوهات الطويلة.

بدل قائمة ثابتة، البرومت بيتركّب من 4 عناصر: أسلوب × ألوان × مشهد × إضاءة.
ده بيدّي آلاف التركيبات المختلفة، وكل تركيبة بتتسجل في السجل عشان ما تتكررش.
كل البرومتات بدون بشر أو وجوه أو كتابة (الـAI بيبوّظ الحروف، والنص بنكتبه إحنا).
"""

NEGATIVE = "no people, no faces, no animals, no text, no letters, no watermark, no logo"

SCENES = [
    "misty mountain valley at dawn with layered ridges",
    "vast golden desert dunes under a starry sky",
    "calm turquoise lake reflecting snowy peaks",
    "ancient olive grove at sunrise with soft rays through the leaves",
    "interior of a grand dome with intricate Islamic geometric patterns and beams of light",
    "distant silhouette of a mosque with slender minarets across a still lake at twilight",
    "endless night sky full of stars over quiet sand dunes",
    "tall waterfall in a lush green forest wrapped in soft mist",
    "crescent moon above a sea of quiet clouds",
    "palm oasis with crystal clear water in the desert",
    "rolling green hills after rain with a faint rainbow",
    "snowy pine forest on a silent winter morning",
    "rocky coastline with gentle waves rolling in",
    "empty arched courtyard of an ornate mosque with a small fountain and sunlight through the arches",
    "glowing lanterns in an empty old stone alley at night",
    "sea of clouds between mountain peaks at sunrise",
    "endless lavender field under soft morning light",
    "blossoming branches leaning over calm water",
    "sandstone canyon with warm walls and shafts of light",
    "aurora glowing over a frozen lake",
    "ornate arabesque ceiling with golden patterns and warm lamp light",
    "quiet riverside with tall reeds at dusk",
    "ancient stone bridge over a misty river",
    "golden wheat field swaying in a gentle breeze",
    "empty tropical beach with turquoise water and white sand",
    "moonlit garden with white jasmine flowers and a small stone fountain",
    "rocky highlands with low clouds and a glowing horizon",
    "macro view of dew drops on green leaves",
    "long avenue of tall cypress trees in soft fog",
    "blue mosaic tile wall with delicate Islamic floral patterns",
]

STYLES = [
    "cinematic photograph, ultra realistic, 35mm lens",
    "soft watercolor painting on textured paper",
    "epic digital matte painting",
    "minimalist flat illustration with smooth gradients",
    "oil painting with visible painterly brush strokes",
    "dreamy 3D render with soft volumetric light",
    "layered paper-cut art with depth",
    "ethereal concept art, highly detailed",
    "vintage travel poster illustration",
    "luminous gouache illustration, gentle grain",
]

PALETTES = [
    "deep emerald green and gold",
    "midnight blue and silver",
    "warm amber and burgundy",
    "teal and sand",
    "soft rose and cream",
    "indigo and turquoise",
    "charcoal and copper",
    "ivory and sage green",
    "twilight purple and gold",
    "ocean blue and white",
]

LIGHTS = [
    "golden hour light",
    "soft dawn light",
    "gentle moonlight",
    "glowing volumetric rays",
    "blue hour ambience",
    "warm lantern glow",
    "soft diffused overcast light",
    "sunset afterglow",
]

# ألوان تقريبية لكل باليت (تُستخدم في الصورة الاحتياطية لو الـAI والـPexels فشلوا).
PALETTE_RGB = [
    ((6, 60, 48), (212, 175, 55)),
    ((10, 20, 60), (190, 200, 215)),
    ((90, 40, 20), (140, 30, 50)),
    ((20, 100, 105), (215, 190, 145)),
    ((200, 140, 150), (245, 235, 215)),
    ((40, 40, 130), (40, 190, 190)),
    ((45, 45, 55), (190, 110, 60)),
    ((235, 230, 210), (130, 165, 130)),
    ((70, 30, 110), (212, 175, 55)),
    ((20, 80, 160), (235, 245, 255)),
]


def total_combinations():
    return len(STYLES) * len(PALETTES) * len(SCENES) * len(LIGHTS)


def prompt_id(style, palette, scene, light):
    """رقم فريد لكل تركيبة (يُخزَّن في السجل)."""
    return ((style * len(PALETTES) + palette) * len(SCENES) + scene) * len(LIGHTS) + light


def build_prompt(style, palette, scene, light, kind="background"):
    parts = [
        STYLES[style],
        SCENES[scene],
        LIGHTS[light],
        f"color palette of {PALETTES[palette]}",
        "calm peaceful spiritual mood",
        "wide 16:9 composition",
        "high detail",
    ]
    if kind == "thumbnail":
        parts.append("dramatic hero shot with one strong focal point, high contrast, open space in the center for a title")
    else:
        parts.append("soft and uncluttered with open space in the center")
    parts.append(NEGATIVE)
    return ", ".join(parts)


def _pick_avoiding(rng, count, recent):
    recent = [r for r in recent if r is not None][-3:]
    options = [i for i in range(count) if i not in recent] or list(range(count))
    return rng.choice(options)


def plan_video(rng, n_images, used_ids=(), recent_styles=(), recent_palettes=()):
    """يخطط هوية الفيديو: أسلوب وألوان ثابتين (قالب السورة) ومشاهد/إضاءات متنوعة.

    بيرجع dict فيه: style, palette, items (لكل صورة خلفية)، thumb (الصورة المصغرة).
    كل عنصر فيه scene, light, id, prompt.
    """
    used = set(used_ids)
    style = _pick_avoiding(rng, len(STYLES), recent_styles)
    palette = _pick_avoiding(rng, len(PALETTES), recent_palettes)

    order = []
    while len(order) < n_images + 1:
        block = list(range(len(SCENES)))
        rng.shuffle(block)
        order.extend(block)

    def make(scene, kind):
        lights = list(range(len(LIGHTS)))
        rng.shuffle(lights)
        chosen = next(
            (l for l in lights if prompt_id(style, palette, scene, l) not in used),
            lights[0],
        )
        pid = prompt_id(style, palette, scene, chosen)
        used.add(pid)
        return {
            "scene": scene,
            "light": chosen,
            "id": pid,
            "prompt": build_prompt(style, palette, scene, chosen, kind),
        }

    items = [make(order[i], "background") for i in range(n_images)]
    thumb = make(order[n_images], "thumbnail")
    return {"style": style, "palette": palette, "items": items, "thumb": thumb}
