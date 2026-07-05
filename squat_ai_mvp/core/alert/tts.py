from __future__ import annotations

import queue
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
    def __init__(self, rate: int = 185, volume: float = 1.0) -> None:
        import pyttsx3

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate)
        self.engine.setProperty("volume", volume)

    def speak(self, text: str) -> None:
        self.engine.say(text)
        self.engine.runAndWait()

    def close(self) -> None:
        try:
            self.engine.stop()
        except Exception:
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


def create_tts_provider(name: str, rate: int = 185, volume: float = 1.0) -> TTSProvider:
    if name == "print":
        return PrintTTSProvider()
    if name == "pyttsx3":
        try:
            return Pyttsx3Provider(rate=rate, volume=volume)
        except Exception as exc:
            print(f"[alert] pyttsx3 unavailable ({exc}); falling back to print TTS")
            return PrintTTSProvider()
    raise ValueError(f"Unknown tts_provider: {name}")
