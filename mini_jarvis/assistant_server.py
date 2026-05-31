import io
import json
import os
import queue
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime
from collections import deque
from typing import Deque, List, Optional

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from scipy.signal import lfilter

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
VOICE = os.getenv("VOICE", "alloy")
STT_PROVIDER = os.getenv("STT_PROVIDER", "local").strip().lower()
TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")
USE_OLLAMA_CHAT = os.getenv("USE_OLLAMA_CHAT", "true").lower() == "true"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "local").strip().lower()
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
ENERGY_THRESHOLD = int(os.getenv("ENERGY_THRESHOLD", "280"))
MIN_SPEECH_MS = int(os.getenv("MIN_SPEECH_MS", "350"))
SILENCE_HOLD_MS = int(os.getenv("SILENCE_HOLD_MS", "900"))
MAX_SPEECH_MS = int(os.getenv("MAX_SPEECH_MS", "10000"))
PRE_ROLL_MS = int(os.getenv("PRE_ROLL_MS", "250"))
ADAPTIVE_VAD = os.getenv("ADAPTIVE_VAD", "true").lower() == "true"
NOISE_FLOOR_ALPHA = float(os.getenv("NOISE_FLOOR_ALPHA", "0.02"))
VAD_MULTIPLIER = float(os.getenv("VAD_MULTIPLIER", "3.2"))
RESPONSE_COOLDOWN_MS = int(os.getenv("RESPONSE_COOLDOWN_MS", "600"))
WAKE_WORD = os.getenv("WAKE_WORD", "jarvis").strip().lower()
REQUIRE_WAKE_WORD = os.getenv("REQUIRE_WAKE_WORD", "false").lower() == "true"
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip()
AUDIO_DEBUG = os.getenv("AUDIO_DEBUG", "true").lower() == "true"
DEBUG_EVERY_MS = int(os.getenv("DEBUG_EVERY_MS", "1500"))
PCM_INT32_GAIN_DIV = max(1, int(os.getenv("PCM_INT32_GAIN_DIV", "4")))
WAKE_ALIASES = [w.strip().lower() for w in os.getenv("WAKE_ALIASES", "").split(",") if w.strip()]
ASYNC_TTS = os.getenv("ASYNC_TTS", "true").lower() == "true"
BARGE_IN = os.getenv("BARGE_IN", "true").lower() == "true"
IGNORE_SHORT_TRANSCRIPTS = os.getenv("IGNORE_SHORT_TRANSCRIPTS", "true").lower() == "true"
MIN_TRANSCRIPT_CHARS = int(os.getenv("MIN_TRANSCRIPT_CHARS", "4"))
ENABLE_DCBLOCK = os.getenv("ENABLE_DCBLOCK", "true").lower() == "true"
DCBLOCK_R = float(os.getenv("DCBLOCK_R", "0.995"))
NOISE_WORDS = {
    "you",
    "u",
    "uh",
    "um",
    "hmm",
    "huh",
    "thanks",
    "thank you",
}

SYSTEM_PROMPT = (
    "You are Mini Jarvis, a concise helpful voice assistant for a college project. "
    "Keep replies short, clear, and practical."
)


def wake_words() -> List[str]:
    words: List[str] = []
    if WAKE_WORD:
        words.append(WAKE_WORD)
    for alias in WAKE_ALIASES:
        if alias and alias not in words:
            words.append(alias)
    return words


def pcm16_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.astype(np.int16).tobytes())
    return bio.getvalue()


def wav_bytes_to_pcm16(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames = wf.getnframes()
        raw = wf.readframes(frames)

    if sampwidth != 2:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth * 8}-bit")

    audio = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)[:, 0]

    if framerate != SAMPLE_RATE:
        print(f"[warn] TTS WAV is {framerate} Hz, output stream expects {SAMPLE_RATE} Hz")

    return audio


def int32_stream_to_int16(chunk: bytes) -> np.ndarray:
    if not chunk:
        return np.array([], dtype=np.int16)

    usable = len(chunk) - (len(chunk) % 4)
    if usable <= 0:
        return np.array([], dtype=np.int16)

    s32 = np.frombuffer(chunk[:usable], dtype=np.int32).astype(np.int64)
    if PCM_INT32_GAIN_DIV > 1:
        s32 = s32 // PCM_INT32_GAIN_DIV
    s16 = np.clip(s32, -32768, 32767).astype(np.int16)
    return s16


def is_noise_transcript_text(
    text: str,
    ignore_short: bool = IGNORE_SHORT_TRANSCRIPTS,
    min_chars: int = MIN_TRANSCRIPT_CHARS,
    noise_words: Optional[set] = None,
) -> bool:
    clean = (text or "").strip().lower()
    if not clean:
        return True
    words = noise_words if noise_words is not None else NOISE_WORDS
    if clean in words:
        return True
    if ignore_short and len(clean) < min_chars:
        return True
    return False


class DCBlocker:
    """First-order DC-blocking IIR filter: H(z) = (1 - z^-1) / (1 - R·z^-1).

    Uses scipy.signal.lfilter for vectorised processing — O(n) in C instead of
    a Python sample loop, which was the main CPU bottleneck on the i3.
    State (zi) is carried across calls so there are no boundary artefacts when
    chunks are fed one at a time.
    """

    def __init__(self, r: float = DCBLOCK_R):
        self.r = float(max(0.0, min(r, 0.9999)))
        # Direct-Form-II transposed initial state for a 1st-order filter.
        # zi[0] = -prev_x + R*prev_y; zero-initialised (silence assumption).
        self._b = np.array([1.0, -1.0], dtype=np.float64)
        self._a = np.array([1.0, -self.r], dtype=np.float64)
        self._zi = np.zeros(1, dtype=np.float64)

    def process(self, x: np.ndarray) -> np.ndarray:
        if x.size == 0:
            return x
        out, self._zi = lfilter(self._b, self._a, x.astype(np.float32), zi=self._zi)
        return np.clip(out, -32768, 32767).astype(np.int16)


class SpeechSegmenter:
    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self.energy_floor = float(max(1, ENERGY_THRESHOLD // 2))
        self.min_speech_samples = int(sample_rate * MIN_SPEECH_MS / 1000)
        self.silence_hold_samples = int(sample_rate * SILENCE_HOLD_MS / 1000)
        self.max_speech_samples = int(sample_rate * MAX_SPEECH_MS / 1000)
        self.pre_roll_max_samples = int(sample_rate * PRE_ROLL_MS / 1000)

        self.in_speech = False
        self.current: List[np.ndarray] = []
        self.current_samples = 0
        self.silence_samples = 0
        self.pre_roll: Deque[np.ndarray] = deque()
        self.pre_roll_samples = 0
        self.last_energy = 0.0
        self.last_threshold = float(ENERGY_THRESHOLD)
        self.last_is_voiced = False

    def _effective_threshold(self) -> float:
        if not ADAPTIVE_VAD:
            return float(ENERGY_THRESHOLD)
        adaptive = self.energy_floor * VAD_MULTIPLIER
        return float(max(ENERGY_THRESHOLD, int(adaptive)))

    def _update_floor(self, energy: float) -> None:
        if not ADAPTIVE_VAD:
            return
        # Update only while not in active speech to avoid drift upward from voice.
        if not self.in_speech:
            self.energy_floor = (1.0 - NOISE_FLOOR_ALPHA) * self.energy_floor + NOISE_FLOOR_ALPHA * energy

    def _push_preroll(self, chunk: np.ndarray) -> None:
        self.pre_roll.append(chunk)
        self.pre_roll_samples += int(chunk.size)
        while self.pre_roll and self.pre_roll_samples > self.pre_roll_max_samples:
            old = self.pre_roll.popleft()
            self.pre_roll_samples -= int(old.size)

    def push(self, chunk: np.ndarray) -> Optional[np.ndarray]:
        if chunk.size == 0:
            return None

        energy = float(np.mean(np.abs(chunk.astype(np.int32))))
        threshold = self._effective_threshold()
        is_voiced = energy >= threshold
        self.last_energy = energy
        self.last_threshold = threshold
        self.last_is_voiced = is_voiced

        self._update_floor(energy)
        self._push_preroll(chunk)

        if not self.in_speech:
            if is_voiced:
                self.in_speech = True
                self.current = list(self.pre_roll)
                self.current_samples = sum(int(c.size) for c in self.current)
                self.silence_samples = 0
            return None

        self.current.append(chunk)
        self.current_samples += int(chunk.size)

        if self.current_samples >= self.max_speech_samples:
            segment = np.concatenate(self.current) if self.current else np.array([], dtype=np.int16)
            self._reset()
            if segment.size >= self.min_speech_samples:
                return segment
            return None

        if is_voiced:
            self.silence_samples = 0
            return None

        self.silence_samples += int(chunk.size)
        if self.silence_samples >= self.silence_hold_samples:
            segment = np.concatenate(self.current) if self.current else np.array([], dtype=np.int16)
            self._reset()
            if segment.size >= self.min_speech_samples:
                return segment

        return None

    def _reset(self) -> None:
        self.in_speech = False
        self.current = []
        self.current_samples = 0
        self.silence_samples = 0

    def debug_snapshot(self) -> str:
        return (
            f"energy={self.last_energy:.1f} threshold={self.last_threshold:.1f} "
            f"voiced={self.last_is_voiced} in_speech={self.in_speech} "
            f"cur_ms={int(self.current_samples * 1000 / self.sample_rate)}"
        )


class MiniJarvis:
    def __init__(self):
        self.client = None
        self.whisper_model = None
        self.tts_engine = None

        if STT_PROVIDER == "local":
            if WhisperModel is None:
                raise RuntimeError("faster-whisper not installed. Run `pip install -r requirements.txt`.")
            self.whisper_model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
            )
        elif STT_PROVIDER == "openai":
            self._init_openai_client()
        else:
            raise RuntimeError("STT_PROVIDER must be 'local' or 'openai'.")

        if TTS_PROVIDER == "local":
            if pyttsx3 is None:
                raise RuntimeError("pyttsx3 not installed. Run `pip install -r requirements.txt`.")
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty("rate", 180)
        elif TTS_PROVIDER == "openai":
            self._init_openai_client()
        else:
            raise RuntimeError("TTS_PROVIDER must be 'local' or 'openai'.")

        self.segmenter = SpeechSegmenter(sample_rate=SAMPLE_RATE)
        self.chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.last_reply_at = 0.0
        self.last_debug_at = 0.0
        self.chunks_seen = 0
        self.wake_words = wake_words()
        self.tts_queue: "queue.Queue[str]" = queue.Queue(maxsize=8)
        self.speaking = False
        self.noise_streak = 0
        self.dcblock = DCBlocker() if ENABLE_DCBLOCK else None
        self._start_tts_worker()

    def _start_tts_worker(self) -> None:
        if TTS_PROVIDER != "local" or not ASYNC_TTS:
            return

        def _worker() -> None:
            while True:
                text = self.tts_queue.get()
                if text is None:  # type: ignore[comparison-overlap]
                    return
                try:
                    self.speaking = True
                    assert self.tts_engine is not None
                    self.tts_engine.say(text)
                    self.tts_engine.runAndWait()
                except Exception as exc:
                    print(f"[warn] Local TTS failed: {exc}")
                finally:
                    self.speaking = False

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def is_noise_transcript(self, user_text: str) -> bool:
        return is_noise_transcript_text(user_text)

    def auto_tune_after_noise(self, seg_ms: int) -> None:
        max_ms = int(MAX_SPEECH_MS)
        if max_ms <= 0:
            return
        if seg_ms < int(max_ms * 0.9):
            return
        self.noise_streak += 1
        if self.noise_streak < 2:
            return
        # Consecutive long noisy captures indicate threshold is too permissive.
        self.segmenter.energy_floor = min(self.segmenter.energy_floor * 1.25, 20000.0)
        print(
            f"[auto-tune] Noise streak={self.noise_streak}, "
            f"raising VAD floor to {self.segmenter.energy_floor:.1f}"
        )

    def reset_noise_streak(self) -> None:
        if self.noise_streak:
            self.noise_streak = 0

    def _enqueue_tts(self, text: str) -> None:
        if not text:
            return
        try:
            self.tts_queue.put_nowait(text)
        except queue.Full:
            try:
                _ = self.tts_queue.get_nowait()
                self.tts_queue.put_nowait(text)
            except queue.Empty:
                pass

    def _barge_in_stop(self) -> None:
        if TTS_PROVIDER != "local" or not BARGE_IN:
            return
        if self.speaking and self.tts_engine is not None:
            try:
                self.tts_engine.stop()
            except Exception:
                pass

    def _init_openai_client(self) -> None:
        if self.client is not None:
            return
        if OpenAI is None:
            raise RuntimeError("openai package not installed. Run `pip install -r requirements.txt`.")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set for OpenAI provider.")
        self.client = OpenAI(api_key=api_key)

    def transcribe(self, pcm16: np.ndarray) -> str:
        if STT_PROVIDER == "local":
            assert self.whisper_model is not None
            audio = pcm16.astype(np.float32) / 32768.0
            segments, _ = self.whisper_model.transcribe(audio, vad_filter=True)
            return " ".join((seg.text or "").strip() for seg in segments).strip()

        wav_data = pcm16_to_wav_bytes(pcm16, SAMPLE_RATE)
        file_tuple = ("speech.wav", wav_data, "audio/wav")

        result = self.client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=file_tuple,
        )

        return (getattr(result, "text", "") or "").strip()

    def should_respond(self, user_text: str) -> bool:
        if not user_text:
            return False

        now = time.time()
        if now - self.last_reply_at < RESPONSE_COOLDOWN_MS / 1000.0:
            return False

        if not REQUIRE_WAKE_WORD:
            return True

        lower = user_text.lower().strip()
        if not self.wake_words:
            return True

        for wake in self.wake_words:
            if lower == wake or lower.startswith(wake + " "):
                return True

        return False

    def normalize_user_text(self, user_text: str) -> str:
        if not REQUIRE_WAKE_WORD or not self.wake_words:
            return user_text
        lower = user_text.lower().strip()
        for wake in self.wake_words:
            if lower.startswith(wake + " "):
                return user_text[len(wake) :].strip(" ,:.-")
            if lower == wake:
                return "hello"
        return user_text

    def is_wake_greeting(self, user_text: str) -> bool:
        lower = user_text.lower().strip(" .,!?:;")
        if not self.wake_words:
            return False
        for wake in self.wake_words:
            wake_phrases = {
                wake,
                f"hello {wake}",
                f"hi {wake}",
                f"hey {wake}",
                f"good morning {wake}",
                f"good afternoon {wake}",
                f"good evening {wake}",
            }
            if lower in wake_phrases:
                return True
        return False

    def wake_greeting_text(self) -> str:
        hour = datetime.now().hour
        if hour < 12:
            time_greet = "Good morning"
        elif hour < 17:
            time_greet = "Good afternoon"
        else:
            time_greet = "Good evening"
        return f"{time_greet}, master."

    def reply_text(self, user_text: str) -> str:
        self.chat_history.append({"role": "user", "content": user_text})
        # Keep system prompt + last 8 non-system turns.  The old slice
        # [-8:] could double-include the system prompt when history is short.
        self.chat_history = [self.chat_history[0]] + self.chat_history[1:][-8:]

        if USE_OLLAMA_CHAT:
            text = self.reply_text_ollama()
            self.chat_history.append({"role": "assistant", "content": text})
            self.last_reply_at = time.time()
            return text

        self._init_openai_client()
        resp = self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=self.chat_history,
            temperature=0.4,
        )
        text = (resp.choices[0].message.content or "").strip()
        self.chat_history.append({"role": "assistant", "content": text})
        self.last_reply_at = time.time()
        return text

    def reply_text_ollama(self) -> str:
        payload = {
            "model": OLLAMA_MODEL,
            "messages": self.chat_history,
            "stream": False,
            "options": {"temperature": 0.4},
        }

        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "Could not reach Ollama. Start it with `ollama serve` and pull the model "
                f"with `ollama pull {OLLAMA_MODEL}`."
            ) from exc

        try:
            data = json.loads(raw)
            text = (data.get("message", {}) or {}).get("content", "")
        except Exception as exc:
            raise RuntimeError(f"Invalid Ollama response: {raw[:200]}") from exc

        return text.strip()

    def speak(self, text: str) -> None:
        if not text:
            return

        if TTS_PROVIDER == "local":
            if ASYNC_TTS:
                self._enqueue_tts(text)
                return
            assert self.tts_engine is not None
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as exc:
                print(f"[warn] Local TTS failed: {exc}")
            return

        speech = self.client.audio.speech.create(
            model=TTS_MODEL,
            voice=VOICE,
            input=text,
            response_format="wav",
        )

        wav_bytes = getattr(speech, "content", None)
        if not wav_bytes:
            wav_bytes = speech.read()

        pcm16 = wav_bytes_to_pcm16(wav_bytes)
        sd.play(pcm16, SAMPLE_RATE, blocking=True)

    def handle_chunk(self, raw_chunk: bytes) -> None:
        self.chunks_seen += 1
        pcm16 = int32_stream_to_int16(raw_chunk)
        if self.dcblock is not None:
            pcm16 = self.dcblock.process(pcm16)
        segment = self.segmenter.push(pcm16)
        if AUDIO_DEBUG:
            now = time.time()
            if (now - self.last_debug_at) * 1000 >= DEBUG_EVERY_MS:
                print(f"[audio] chunks={self.chunks_seen} {self.segmenter.debug_snapshot()}")
                self.last_debug_at = now
        if segment is None:
            return
        self._barge_in_stop()

        try:
            seg_ms = int(segment.size * 1000 / SAMPLE_RATE)
            seg_energy = float(np.mean(np.abs(segment.astype(np.int32))))
            print(f"\n[segment] ms={seg_ms} energy={seg_energy:.1f}")
            print("\n[processing] Transcribing...")
            user_text = self.transcribe(segment)
            if not user_text:
                print("[skip] No transcription text")
                self.auto_tune_after_noise(seg_ms)
                return
            if self.is_noise_transcript(user_text):
                print(f"[skip] Noise transcript: {user_text!r}")
                self.auto_tune_after_noise(seg_ms)
                return

            print(f"[you] {user_text}")
            self.reset_noise_streak()
            if not self.should_respond(user_text):
                if REQUIRE_WAKE_WORD:
                    words = ", ".join(self.wake_words) if self.wake_words else WAKE_WORD
                    print(f"[skip] Wake word not detected (accepted: {words})")
                else:
                    print("[skip] Cooldown active")
                return

            if REQUIRE_WAKE_WORD and self.is_wake_greeting(user_text):
                reply = self.wake_greeting_text()
                print(f"[jarvis] {reply}")
                self.last_reply_at = time.time()
                self.speak(reply)
                return

            user_text = self.normalize_user_text(user_text)
            reply = self.reply_text(user_text)
            print(f"[jarvis] {reply}")
            self.speak(reply)
        except Exception as exc:
            print(f"[error] Turn failed: {exc}")


def recv_auth_line(conn: socket.socket) -> Optional[str]:
    # Optional auth handshake: client can send first line as 'AUTH <token>\n'.
    conn.settimeout(2.0)
    try:
        first = conn.recv(256)
    except socket.timeout:
        conn.settimeout(None)
        return None
    conn.settimeout(None)

    if not first:
        return ""

    if b"\n" not in first:
        return None

    line, _, _ = first.partition(b"\n")
    return line.decode(errors="ignore").strip()


def authorized(conn: socket.socket) -> bool:
    if not AUTH_TOKEN:
        return True

    line = recv_auth_line(conn)
    if not line:
        return False

    return line == f"AUTH {AUTH_TOKEN}"


def _handle_client(conn: socket.socket, addr: tuple, bot: "MiniJarvis") -> None:
    """Run in a daemon thread — one thread per ESP32 connection."""
    print(f"Connected: {addr}")
    if not authorized(conn):
        print("[security] Unauthorized client rejected")
        conn.close()
        return
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                print(f"Client {addr} disconnected")
                break
            bot.handle_chunk(data)
    except ConnectionResetError:
        print(f"Client {addr} connection reset")
    except Exception as exc:
        print(f"[error] Connection loop {addr}: {exc}")
    finally:
        conn.close()
    print("Waiting for next ESP32 connection...")


def run_server() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(3)

    print(f"Mini Jarvis server listening on {HOST}:{PORT}")
    print("Initializing speech/chat stack...")
    bot = MiniJarvis()
    print("Initialization complete.")
    print(f"STT provider: {STT_PROVIDER}")
    print(f"Chat provider: {'ollama' if USE_OLLAMA_CHAT else 'openai'}")
    print(f"TTS provider: {TTS_PROVIDER}")
    print(f"Audio debug: {'ON' if AUDIO_DEBUG else 'OFF'} ({DEBUG_EVERY_MS} ms)")
    print(f"PCM int32 gain divisor: {PCM_INT32_GAIN_DIV}")
    print(f"DC blocker: {'ON' if ENABLE_DCBLOCK else 'OFF'} (R={DCBLOCK_R})")
    print(f"Async TTS: {'ON' if ASYNC_TTS else 'OFF'} | Barge-in: {'ON' if BARGE_IN else 'OFF'}")
    if REQUIRE_WAKE_WORD:
        words = ", ".join(bot.wake_words) if bot.wake_words else WAKE_WORD
        print(f"Wake word mode: ON ({words})")
    else:
        print("Wake word mode: OFF")
    print("Waiting for ESP32 connection...")

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(
                target=_handle_client,
                args=(conn, addr, bot),
                daemon=True,
            )
            t.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.close()


if __name__ == "__main__":
    try:
        run_server()
    except Exception as exc:
        print(f"Fatal error: {exc}")
        sys.exit(1)
