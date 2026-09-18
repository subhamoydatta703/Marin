"""
Kokoro TTS — tuned for Marin's conversational, expressive voice.

Uses Kokoro's punctuation-driven prosody system to get natural pacing:
  - Commas, dashes → short breath pauses
  - Ellipsis (...) → trailing off / hesitation
  - ! → energy and emphasis
  - ? → rising intonation
  - . → sentence-ending pause with reset

The LLM prompt already produces expressive punctuation (trailing off,
stretched words, fillers, repetition) — this module just makes sure
that punctuation reaches Kokoro cleanly, without artifacts that would
break the prosody or cause unnatural pauses.
"""

import re
from kokoro import KPipeline
import sounddevice as sd

# American English, CUDA — loaded once at import time
pipeline = KPipeline(lang_code='a', device='cuda')


def _clean_for_speech(text: str) -> str:
    """Prepare LLM output for Kokoro's prosody engine.
    
    Goals:
      - Strip anything that would be read literally (markdown, brackets, asterisks)
      - Normalize punctuation so Kokoro's prosody rules fire correctly
      - Preserve expressive markers the LLM uses (ellipsis, !, ?, dashes)
      - No artificial pauses — pacing comes from punctuation alone
    """
    # Strip any residual action narration *laughs*, *sighs*, etc.
    text = re.sub(r'\*[^*]+\*', '', text)

    # Strip any bracketed markers that might have leaked through
    text = re.sub(r'\[[^\]]*\]', '', text)

    # Normalize multiple periods into proper ellipsis (Kokoro treats ... as hesitation)
    text = re.sub(r'\.{2,}', '...', text)

    # Normalize multiple exclamation/question marks to single (Kokoro only needs one)
    text = re.sub(r'!{2,}', '!', text)
    text = re.sub(r'\?{2,}', '?', text)

    # Convert stretched words (nooo, waittt, reallyyy) — keep the stretch,
    # Kokoro handles repeated letters reasonably well for pacing
    # But cap extreme stretches (5+ repeated chars) to 3
    text = re.sub(r'(.)\1{4,}', r'\1\1\1', text)

    # Normalize double spaces and trim
    text = re.sub(r'\s+', ' ', text).strip()

    # Only inject a comma after true interjections at the START of a sentence/clause
    # (e.g. "^ugh " or "^wait "), NEVER in the middle of sentences where words like
    # 'so', 'like', 'right' would be falsely matched.
    LEADING_INTERJECTIONS = r'ugh|wait|hey|dude|oh|umm|hmm'
    text = re.sub(
        rf'(?i)(^|(?<=[.!?])\s*)({LEADING_INTERJECTIONS})\s+(?=[a-z])',
        r'\1\2, ',
        text
    )

    # Handle repeated reaction words: "no no no" → "no, no, no,"
    text = re.sub(
        r'(?i)\b(no|wait|hey)(?:\s+\1){1,}',
        lambda m: ', '.join([m.group(1)] * (m.group(0).lower().count(m.group(1).lower()))) + ',',
        text
    )

    return text


def speak_kokoro(text: str, voice: str = "af_heart", speed: float = 0.88):
    """Generate and play speech smoothly for Marin's responses.
    
    Args:
        text: LLM response text
        voice: Kokoro voice slug — af_heart is warm and natural
        speed: 0.88 is a natural, conversational speaking rate
    """
    
    if not text or not text.strip():
        return

    cleaned = _clean_for_speech(text)
    if not cleaned:
        return

    import numpy as np

    # Collect all audio chunks first so playback is completely smooth
    # without any inter-chunk computation pauses or hiccups
    generator = pipeline(cleaned, voice=voice, speed=speed)
    chunks = []
    for _, _, audio in generator:
        if audio is not None and len(audio) > 0:
            chunks.append(audio)

    if chunks:
        full_audio = np.concatenate(chunks)
        sd.play(full_audio, 24000)
        sd.wait()


if __name__ == "__main__":
    import time

    test_lines = [
        "ugh honestly I am so annoyed right now, my brother took my laptop charger and hid it just to be annoying",
        "wait... what? you actually finished the whole assignment before the deadline?",
        "no no no, that is not what I meant! come on, you know me better than that",
        "I don't know, it just felt kind of... wrong? like something was off but I couldn't figure out what",
        "oh my god, you are serious. you are actually serious right now.",
        "hmm. maybe. I will think about it.",
    ]

    for line in test_lines:
        print(f"\n> {line}")
        t0 = time.time()
        speak_kokoro(line)
        print(f"  ({time.time() - t0:.2f}s)")