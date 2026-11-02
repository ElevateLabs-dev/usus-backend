"""
Voices for voice role-play, and how a scenario's emotion shapes them.

The voices are ElevenLabs voices that Vapi offers by name. ElevenLabs lets us
tune how steady (stability), expressive (style) and fast a voice sounds, so an
angry customer sounds tense and fast and a calm one sounds even.
"""

from dataclasses import dataclass

from src.domains.scenarios.models import CustomerPersona, Scenario


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    gender: str  # "female" | "male"


VOICES: tuple[Voice, ...] = (
    Voice("sarah", "Sarah", "female"),
    Voice("marissa", "Marissa", "female"),
    Voice("andrea", "Andrea", "female"),
    Voice("paula", "Paula", "female"),
    Voice("ryan", "Ryan", "male"),
    Voice("drew", "Drew", "male"),
    Voice("steve", "Steve", "male"),
    Voice("joseph", "Joseph", "male"),
)

VOICE_IDS = frozenset(voice.id for voice in VOICES)

DEFAULT_VOICE = "sarah"


@dataclass(frozen=True)
class Delivery:
    """How the voice delivers lines for an emotion."""

    mood: str
    stability: float  # lower = more emotional variation
    style: float  # higher = more exaggerated delivery
    speed: float


_DELIVERY = {
    "angry": Delivery("angry", stability=0.25, style=0.7, speed=1.08),
    "frustrated": Delivery("frustrated", stability=0.35, style=0.5, speed=1.04),
    "anxious": Delivery("anxious", stability=0.35, style=0.45, speed=1.06),
    "sad": Delivery("sad", stability=0.45, style=0.4, speed=0.94),
    "calm": Delivery("calm", stability=0.6, style=0.2, speed=1.0),
}

# Words in the scenario's "how the customer feels" field, checked in order.
_KEYWORDS = (
    ("angry", ("angry", "furious", "livid", "irate", "outraged", "hostile")),
    ("anxious", ("anxious", "worried", "nervous", "scared", "panic", "stressed")),
    ("sad", ("sad", "upset", "disappointed", "hurt", "lonely", "confused")),
    ("frustrated", ("frustrat", "annoyed", "impatient", "irritat", "fed up")),
    ("calm", ("calm", "polite", "friendly", "relaxed", "happy", "neutral")),
)

_PERSONA_MOOD = {
    CustomerPersona.ANGRY: "angry",
    CustomerPersona.FRUSTRATED: "frustrated",
    CustomerPersona.FRIENDLY: "calm",
}


def scenario_mood(scenario: Scenario) -> str:
    """The customer's starting mood: from the written emotion if it names one,
    otherwise from the persona."""
    emotion = (scenario.customer_emotion or "").lower()
    for mood, words in _KEYWORDS:
        if any(word in emotion for word in words):
            return mood
    return _PERSONA_MOOD.get(scenario.persona, "calm")


def voice_config(voice_id: str | None, mood: str) -> dict:
    """The Vapi voice settings for a voice speaking in a mood."""
    voice = voice_id if voice_id in VOICE_IDS else DEFAULT_VOICE
    delivery = _DELIVERY.get(mood, _DELIVERY["calm"])
    return {
        "provider": "11labs",
        "voiceId": voice,
        "model": "eleven_turbo_v2_5",
        "stability": delivery.stability,
        "similarityBoost": 0.75,
        "style": delivery.style,
        "speed": delivery.speed,
    }
