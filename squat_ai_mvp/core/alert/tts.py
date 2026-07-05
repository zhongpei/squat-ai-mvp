from __future__ import annotations

import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class AlertCommand:
    text: str
    priority: str
    cooldown_key: str


class TTSProvider:
    def speak(self, text: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class PrintTTSProvider(TTSProvider):
    def speak(self, text: str) -> None:
        print(f"[TTS] {text}")


class Pyttsx3Provider(TTSProvider):
    """pyttsx3 TTS engine (macOS NSSpeech / Windows SAPI / Linux espeak).

    Supports Chinese voices on macOS via voice_id.
    """

    def __init__(self, rate: int = 185, volume: float = 1.0, voice_id: Optional[str] = None) -> None:
        import pyttsx3

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate)
        self.engine.setProperty("volume", volume)
        if voice_id:
            self.engine.setProperty("voice", voice_id)
        else:
            self._auto_select_chinese_voice()

    def _auto_select_chinese_voice(self) -> None:
        """Prefer a Chinese voice when alert messages are in Chinese."""
        voices = self.engine.getProperty("voices")
        # Prioritise zh_CN (Simplified Chinese), fallback to zh_TW, zh_HK, then default.
        preferred = ["zh_CN", "zh_TW", "zh_HK"]
        for lang in preferred:
            for v in voices:
                if any(lang in str(lang_str) for lang_str in v.languages):
                    self.engine.setProperty("voice", v.id)
                    print(f"[tts] Selected voice: {v.name} ({lang})")
                    return
        print("[tts] No Chinese voice found; using default")

    def speak(self, text: str) -> None:
        self.engine.say(text)
        self.engine.runAndWait()

    def close(self) -> None:
        try:
            self.engine.stop()
        except Exception:
            pass


class SayProvider(TTSProvider):
    """macOS ``say`` command – zero dependencies, fast, built-in.

    Runs ``say -v <voice> <text>`` in a subprocess.
    """

    def __init__(self, voice: str = "Tingting", rate: int = 185) -> None:
        self.voice = voice
        self.rate = rate

    def speak(self, text: str) -> None:
        subprocess.run(
            ["say", "-v", self.voice, "--rate", str(self.rate), text],
            check=False,
        )

    def close(self) -> None:
        pass


class AsyncTTS:
    """Non-blocking TTS queue so real-time inference is not blocked by speech."""

    def __init__(self, provider: TTSProvider) -> None:
        self.provider = provider
        self.q: queue.Queue[Optional[str]] = queue.Queue(maxsize=32)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def speak(self, text: str) -> None:
        try:
            self.q.put_nowait(text)
        except queue.Full:
            print("[alert] TTS queue full; dropping alert")

    def _loop(self) -> None:
        while True:
            item = self.q.get()
            if item is None:
                break
            try:
                self.provider.speak(item)
            except Exception as exc:
                print(f"[alert] TTS failed: {exc}. Text: {item}")

    def close(self) -> None:
        self.q.put(None)
        self.thread.join(timeout=1.0)
        self.provider.close()


def create_tts_provider(name: str, rate: int = 185, volume: float = 1.0, voice: Optional[str] = None) -> TTSProvider:
    """Factory: return a TTS provider by name."""
    if name == "print":
        return PrintTTSProvider()
    if name == "say":
        return SayProvider(voice=voice or "Tingting", rate=rate)
    if name == "pyttsx3":
        try:
            return Pyttsx3Provider(rate=rate, volume=volume, voice_id=voice)
        except Exception as exc:
            print(f"[alert] pyttsx3 unavailable ({exc}); falling back to print TTS")
            return PrintTTSProvider()
    raise ValueError(f"Unknown tts_provider: {name}")
