import logging
import os
import threading
import numpy as np
import torch

logger = logging.getLogger(__name__)
device = "cuda" if torch.cuda.is_available() else "cpu"
_transcriber = None
_model_lock = threading.Lock()
_inference_lock = threading.Lock()


def get_stt_model_id():
    return os.environ.get("MARIN_STT_MODEL", "openai/whisper-small.en")


def get_transcriber():
    global _transcriber
    with _model_lock:
        if _transcriber is None:
            from transformers import pipeline
            _transcriber = pipeline("automatic-speech-recognition", model=get_stt_model_id(), device=device)
            _transcriber.tokenizer.clean_up_tokenization_spaces = False
    return _transcriber


def prepare_audio(audio):
    audio = np.asarray(audio, dtype=np.float32).squeeze()
    if audio.ndim != 1:
        raise ValueError("Speech recognition expects mono audio at 16 kHz")
    if not np.isfinite(audio).all():
        raise ValueError("Audio contains invalid samples")
    if audio.size == 0:
        return audio
    audio = audio - float(np.mean(audio))
    peak = float(np.max(np.abs(audio)))
    if peak < 0.0001:
        return np.array([], dtype=np.float32)
    # Check the original recording before gain can turn background noise into
    # plausible input for Whisper. Require at least 100 ms of audible frames;
    # a brief click must not send an otherwise silent recording to the model.
    frame_size = 320  # 20 ms at 16 kHz
    frame_count = audio.size // frame_size
    if frame_count:
        frames = audio[:frame_count * frame_size].reshape(-1, frame_size)
        frame_rms = np.sqrt(np.mean(frames * frames, axis=1))
        if np.count_nonzero(frame_rms >= 0.003) < 5:
            return np.array([], dtype=np.float32)
    # Lift quiet recordings gently without amplifying them beyond normal range.
    if peak < 0.1:
        audio = audio * min(4.0, 0.1 / peak)
    return np.ascontiguousarray(np.clip(audio, -1, 1), dtype=np.float32)


def stt_conversion(trimmed_audio=None):
    if trimmed_audio is None:
        from speech_recognition.get_speech import trim_audio
        trimmed_audio = trim_audio()
    if trimmed_audio is None:
        return {"text": ""}
    audio = prepare_audio(trimmed_audio)
    if audio.size < 1600:
        return {"text": ""}
    try:
        with _inference_lock:
            transcriber = get_transcriber()
            options = dict(do_sample=False, num_beams=3, condition_on_prev_tokens=False)
            if not get_stt_model_id().endswith(".en"):
                options.update(task="transcribe", language=os.environ.get("MARIN_STT_LANGUAGE", "english"))
            result = transcriber(
                {"sampling_rate": 16000, "array": audio},
                return_timestamps=audio.size > 30 * 16000,
                generate_kwargs=options,
            )
    except Exception as exc:
        logger.exception("Speech recognition failed")
        raise RuntimeError("Speech recognition failed. Check the server log and microphone settings.") from exc
    text = result.get("text", "") if isinstance(result, dict) else str(result or "")
    return {"text": text.strip()}
