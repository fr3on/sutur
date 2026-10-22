"""The texts the planning tasks send to the LLM. Kept apart from the code so a review lesson is a one-line edit here (or in resources/prompt_rules.txt)."""

from __future__ import annotations

from importlib import resources

CAST_SYSTEM = "You prepare a black-and-white manga adaptation. Answer with JSON only."

PROMPT_SYSTEM = """You write drawing prompts for a black-and-white manga page, one per panel. Given a passage of a story (Arabic) you describe ONE clear picture of it in English: one sentence, 20 to 40 words.
Rules: describe what is SEEN (who, where, doing what, the shot type, light, mood). Use the character tags in curly braces exactly as given, e.g. {DUP}, whenever that character is in the picture; never write their names or looks yourself.
Never write dialogue, quotes, speech, signs, letters, books with titles or any text. Never use the words saying, asking, said, speech. Show talk as gestures or expressions.
Violence stays implied (shadows, aftermath, no blood). If the passage is only explanation, show the speaker in a calm scene or a simple symbolic picture of the idea.
Keep it in the period and place of the story. Output the prompt only."""

COVER_SYSTEM = "You write one English sentence describing a single striking cover scene for a black-and-white manga book volume."

# Extra wording added to a panel's prompt only when it mentions these things (hands and held objects go wrong otherwise).
AUTO_WORDS = [
    {"words": ["gun", "pistol", "revolver", "rifle", "weapon"],
     "text": "the weapon is held correctly in one anatomically correct hand, five fingers wrapped around the grip, finger outside the trigger guard, arm lowered or held to the side, pointed at the floor or away from anyone, seen clearly from the side"},
    {"words": ["telescope", "binoculars", "spyglass", "razor", "knife"],
     "text": "held with anatomically correct hands, five fingers on each hand, the object clear and in proportion, shown from the side in a medium shot"},
    {"words": ["hand", "hands", "handshake", "holding", "grip"], "text": "hands drawn with exactly five fingers each, natural anatomy"},
]

STYLE_PREFIX = "Black-and-white manga ink panel, pure black ink on white paper, fine ink linework, halftone screentone, {era}."
STYLE_SUFFIX = "No text, no letters, no border, no color. Strictly {era}, period clothing and period objects only. Nothing explicit or sexual."
PORTRAIT_PREFIX = "Black-and-white manga ink portrait, head and shoulders, pure black ink on white paper, fine ink linework, halftone screentone, {era}, plain light background. "
COVER_PREFIX = "Clean black ink manga cover illustration, fine linework with light gray wash, mostly white background fading softly at the bottom, vertical composition, no text, no letters, no border, no color."


def cast_request(title: str, author: str, synopsis: str, main_characters: str, sample: str, era: str | None) -> str:
    usr = f"""Book: {title} by {author}. Synopsis: {synopsis}
Main characters (Arabic): {main_characters}
Samples from across the text (Arabic): {sample}

Return JSON: {{"era": "short English phrase for the period and place, e.g. 'Paris in the 1840s, gaslit cobbled streets'",
"props_to_avoid": "modern things that must not appear",
"characters": [ {{"id": "lowercase latin id", "tag": "UPPERCASE 2-5 letters", "ar_name": "... (Arabic letters only)", "ar_role": "role in Arabic letters only, max 5 words", "en_name": "...", "en_role": "English role, max 6 words",
"look": "English visual description: age, build, hair, clothes of that period, one distinctive trait"}} ] }}
Give 6 to 9 characters who really appear in the story, spread over all the samples, the main ones first; id must be a readable English word. Animals are allowed but describe them as the animal itself (fins, tail, fur), never with a human body or clothes; no nudity, everyone modestly clothed."""
    if era:
        usr += f"\nThe story takes place in {era}. Describe every look with clothing and objects of exactly that period and place; never ancient or pharaonic dress."
    return usr


def cover_scene_request(characters: str, sample: str) -> str:
    return f"Characters: {characters}\nStory samples (Arabic): {sample}\nOne sentence, 25 to 40 words, a vertical composition, modest period clothing, no text."


def panel_prompt_request(characters: str, previous: str, passage: str) -> str:
    return f"Characters you may tag:\n{characters}\n\nPrevious passage (for continuity): {previous}\n\nPassage to illustrate:\n{passage}"


def review_rules() -> str:
    """Lessons from reviews (resources/prompt_rules.txt): appended to the system prompt, so every new volume follows them."""
    return resources.files("sutur_pipeline").joinpath("resources/prompt_rules.txt").read_text(encoding="utf-8").strip()
