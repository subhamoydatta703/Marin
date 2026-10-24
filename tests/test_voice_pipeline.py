import asyncio
import sys
import threading
import queue
import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
import numpy as np
import server
from backend import streaming_service as stream
from backend import conversation_service as conversation
from llm import gemini_answer as gemini
from llm.marin_persona import shift_mood, text_is_rude, build_prompt
from speech_to_text import stt_conversion as stt
from speech_recognition import emotion
from text_to_speech.speech_text import clean_speech_text
from text_to_speech import edge_speech
from fastapi.testclient import TestClient


class SpeechTests(unittest.TestCase):
    def test_checkout_modules_are_not_shadowed_by_installed_copies(self):
        self.assertEqual(Path(stt.__file__).resolve().parent, ROOT / "src" / "speech_to_text")
        self.assertEqual(Path(emotion.__file__).resolve().parent, ROOT / "src" / "speech_recognition")

    def test_speech_cleanup_preserves_real_words_and_numbers(self):
        text = clean_speech_text("Okayyyy... Nooo, *laughs* **coffee** and a book cost 100000. Un be lievable.")
        self.assertIn("okay, no, coffee", text)
        self.assertIn("book cost 100000", text)
        self.assertIn("unbelievable", text)
        self.assertNotIn("laughs", text)

    def test_quiet_audio_is_preserved_and_lifted(self):
        audio = np.sin(np.arange(16000) * 0.05).astype(np.float32) * 0.01
        prepared = stt.prepare_audio(audio)
        self.assertEqual(prepared.shape, audio.shape)
        self.assertGreater(np.max(np.abs(prepared)), 0.03)
        self.assertLessEqual(np.max(np.abs(prepared)), 1)

    def test_speech_cleanup_preserves_technical_content(self):
        self.assertEqual(clean_speech_text("Use C#, foo_bar, and 2*3 > 5."), "Use C#, foo_bar, and 2*3 > 5.")

    def test_invalid_audio_is_rejected(self):
        with self.assertRaises(ValueError):
            stt.prepare_audio(np.array([np.nan, 0]))
        with self.assertRaises(ValueError):
            stt.prepare_audio(np.zeros((2, 100)))

    def test_silence_does_not_invoke_whisper(self):
        with patch.object(stt, "get_transcriber") as model:
            self.assertEqual(stt.stt_conversion(np.zeros(16000)), {"text": ""})
            model.assert_not_called()

    def test_quiet_noise_and_isolated_click_do_not_invoke_whisper(self):
        noise = np.random.default_rng(0).normal(0, 0.0008, 16000).astype(np.float32)
        click = noise.copy()
        click[8000:8160] = 0.2
        for audio in (noise, click):
            with self.subTest(click=audio is click), patch.object(stt, "get_transcriber") as model:
                self.assertEqual(stt.stt_conversion(audio), {"text": ""})
                model.assert_not_called()

    def test_short_greeting_is_still_transcribed(self):
        audio = np.zeros(8000, dtype=np.float32)
        audio[1600:4800] = np.sin(np.arange(3200) * 0.05) * 0.01
        model = Mock(return_value={"text": "Hi"})
        with patch.object(stt, "get_transcriber", return_value=model):
            self.assertEqual(stt.stt_conversion(audio), {"text": "Hi"})
        model.assert_called_once()

    def test_long_speech_uses_timestamps_and_deterministic_decoding(self):
        model = Mock(return_value={"text": " recognized "})
        with patch.object(stt, "get_transcriber", return_value=model):
            result = stt.stt_conversion(np.sin(np.arange(31 * 16000) * 0.05))
        self.assertEqual(result["text"], "recognized")
        self.assertTrue(model.call_args.kwargs["return_timestamps"])
        self.assertFalse(model.call_args.kwargs["generate_kwargs"]["do_sample"])

    def test_recognition_failure_is_visible(self):
        model = Mock(side_effect=RuntimeError("model failure"))
        with patch.object(stt, "get_transcriber", return_value=model), self.assertLogs(stt.logger, level="ERROR"):
            with self.assertRaisesRegex(RuntimeError, "Speech recognition failed"):
                stt.stt_conversion(np.sin(np.arange(16000) * 0.05))

    def test_perception_workers_run_concurrently(self):
        barrier = threading.Barrier(2)
        def recognize(_):
            barrier.wait(timeout=2)
            return {"text": "hello"}
        def detect(_):
            barrier.wait(timeout=2)
            return {"top_emotion": "happy", "top_score": 0.9}
        with patch.object(stt, "stt_conversion", side_effect=recognize), patch.object(
            emotion, "detect_emotion", side_effect=detect
        ), patch.object(conversation, "decode_audio_to_16k", return_value=np.ones(16000)):
            self.assertEqual(conversation.perceive_audio(b"audio")[0], "hello")

    def test_mood_requires_repeated_evidence(self):
        state = {}
        self.assertEqual(shift_mood("soft", "happy", 0.9, state=state), "soft")
        self.assertEqual(shift_mood("soft", "happy", 0.9, state=state), "clingy")
        self.assertEqual(shift_mood("clingy", "angry", 0.95, state=state), "clingy")
        self.assertEqual(shift_mood("clingy", "angry", 0.95, state=state), "clingy")

    def test_rudeness_is_not_a_substring_match(self):
        self.assertFalse(text_is_rude("My code has a stupid bug"))
        self.assertFalse(text_is_rude("I feel dumb today"))
        self.assertTrue(text_is_rude("You are stupid"))

    def test_prompt_keeps_factual_and_speech_constraints(self):
        prompt = build_prompt("soft", personality={"warmth": 0.8}, memory="My name is Anil")
        self.assertIn("Never stretch letters", prompt)
        self.assertIn("Do not invent", prompt)
        self.assertIn("My name is Anil", prompt)


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_and_audio_arrive_before_turn_is_complete(self):
        async def tokens(*args):
            yield "It sounds like you had quite a long day. "
            yield "Tell me what happened."
        with patch.object(stream, "perceive_audio", return_value=("Hi", "neutral", 0.5)), patch.object(
            stream, "stream_answer", tokens
        ), patch.object(stream, "synthesize_speech_base64", new=AsyncMock(return_value="audio")) as synth:
            events = [event async for event in stream.stream_audio_turn(b"audio", "soft", [], {})]
        self.assertEqual([e["type"] for e in events], ["user", "text", "audio", "text", "audio", "done"])
        self.assertEqual(synth.call_args.kwargs["voice"], "en-IN-NeerjaNeural")
        self.assertIsNotNone(events[-1]["timings"]["first_audio_ms"])

    async def test_tts_failure_keeps_transcript(self):
        async def tokens(*args):
            yield "Here is a reply."
        with patch.object(stream, "perceive_audio", return_value=("Hi", "neutral", 0.5)), patch.object(
            stream, "stream_answer", tokens
        ), patch.object(stream, "synthesize_speech_base64", new=AsyncMock(side_effect=RuntimeError("offline"))), self.assertLogs(level="ERROR"):
            events = [event async for event in stream.stream_audio_turn(b"audio", "soft", [], {})]
        self.assertIn("warning", [e["type"] for e in events])
        self.assertEqual(events[-1]["reply_text"], "Here is a reply.")

    async def test_cancellation_closes_generation(self):
        closed = asyncio.Event()
        async def tokens(*args):
            try:
                yield "This is a sufficiently long sentence for playback. "
                await asyncio.sleep(30)
            finally:
                closed.set()
        with patch.object(stream, "perceive_audio", return_value=("Hi", "neutral", 0.5)), patch.object(
            stream, "stream_answer", tokens
        ), patch.object(stream, "synthesize_speech_base64", new=AsyncMock(return_value="audio")):
            generator = stream.stream_audio_turn(b"audio", "soft", [], {})
            for _ in range(3):
                await anext(generator)
            await generator.aclose()
        self.assertTrue(closed.is_set())

    def test_sentence_split_does_not_split_abbreviation(self):
        text, _ = stream.split_ready_sentence("Today I was talking at length with Dr. Sharma. Then we left. ")
        self.assertTrue(text.endswith("Sharma."))

    def test_memory_uses_verbatim_snippets_and_is_bounded(self):
        history = conversation.history_messages([{"role": "user", "content": f"Fact {i}"} for i in range(14)], limit=14)
        summary = stream.compact_history("Earlier note", history)
        self.assertIn("user: Fact 0", summary)
        self.assertNotIn("Fact 2", summary)
        self.assertLessEqual(len(stream.compact_history("x" * 4000, history)), 4000)

    async def test_sdk_stream_uses_text_deltas_and_closes(self):
        class Events:
            closed = False
            def __aiter__(self): return self
            async def __anext__(self):
                if getattr(self, "sent", False): raise StopAsyncIteration
                self.sent = True
                return SimpleNamespace(delta=SimpleNamespace(type="text", text="hello"))
            async def close(self): self.closed = True
        events = Events()
        client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=AsyncMock(return_value=events))))
        with patch.object(gemini, "get_client", return_value=client):
            self.assertEqual([t async for t in gemini.stream_answer([], "prompt")], ["hello"])
        self.assertTrue(events.closed)


class DesktopPlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_reply_is_synthesized_once_without_sentence_resets(self):
        with patch.object(edge_speech, "_synthesize", new=AsyncMock(return_value=b"audio")) as synth, patch.object(edge_speech, "_play"):
            await edge_speech._speak_async("Okayyyy. This is a full reply.", "voice", "+0%", "+0Hz", threading.Event())
        synth.assert_awaited_once_with("okay. This is a full reply.", "voice", "+0%", "+0Hz")

    def test_cancelled_speech_cannot_start_ffplay(self):
        out = queue.Queue()
        out.put(b"audio")
        stopped = threading.Event()
        stopped.set()
        with patch.object(edge_speech.subprocess, "Popen") as process:
            edge_speech._play(out, stopped)
        process.assert_not_called()

    def test_playback_does_not_cut_off_long_replies_at_thirty_seconds(self):
        out = queue.Queue()
        out.put(b"audio")
        out.put(None)
        process = Mock(stdin=io.BytesIO())
        with patch.object(edge_speech.subprocess, "Popen", return_value=process):
            edge_speech._play(out, threading.Event())
        process.wait.assert_called_once_with()


class StreamingApiTests(unittest.TestCase):
    def test_bad_context_is_rejected_before_stream(self):
        client = TestClient(server.app)
        for context in ('{"voice":"invalid"}', '{"personality":{"warmth":5}}', 'null'):
            response = client.post("/api/chat/audio", files={"audio": ("a.wav", b"audio")},
                                   data={"stream": "true", "context": context})
            self.assertEqual(response.status_code, 422)

    def test_stream_errors_are_returned_as_events(self):
        with patch.object(stream, "perceive_audio", side_effect=RuntimeError("recognition unavailable")), self.assertLogs("uvicorn.error", level="ERROR"):
            response = TestClient(server.app).post("/api/chat/audio", files={"audio": ("a.wav", b"audio")}, data={"stream": "true"})
        self.assertIn('"type": "error"', response.text)
        self.assertIn("recognition unavailable", response.text)
