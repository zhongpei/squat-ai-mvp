from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterator, Optional

import cv2
import numpy as np

from squat_ai_mvp.core.biomechanics.schemas import FrameEvent


@dataclass
class VideoFrame:
    event: FrameEvent
    image_bgr: np.ndarray


class OpenCVStreamSource:
    """Unified frame source for RTSP/RTMP/file/webcam inputs.

    Input examples:
      - rtsp://127.0.0.1:8554/live/side
      - /path/to/video.mp4
      - 0  (local webcam, only for debugging)
    """

    def __init__(
        self,
        input_url: str,
        session_id: str,
        camera_id: str,
        camera_role: str,
        expected_fps: float = 30.0,
        reconnect: bool = True,
        reconnect_interval_sec: float = 2.0,
        buffer_size: int = 1,
        rotate: int = 0,
        mirror: bool = False,
        max_width: Optional[int] = 1280,
    ) -> None:
        self.input_url = input_url
        self.session_id = session_id
        self.camera_id = camera_id
        self.camera_role = camera_role
        self.expected_fps = expected_fps
        self.reconnect = reconnect
        self.reconnect_interval_sec = reconnect_interval_sec
        self.buffer_size = buffer_size
        self.rotate = rotate
        self.mirror = mirror
        self.max_width = max_width
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_id = 0
        self._started = time.perf_counter()
        self._last_fps_time = self._started
        self._fps_count = 0
        self._fps_est = 0.0

    def _open(self) -> bool:
        source: str | int = self.input_url
        if str(source).isdigit():
            source = int(source)
        cap = cv2.VideoCapture(source)
        if self.buffer_size is not None:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
        if not cap.isOpened():
            cap.release()
            return False
        self._cap = cap
        return True

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def frames(self) -> Iterator[VideoFrame]:
        while True:
            if self._cap is None and not self._open():
                if not self.reconnect:
                    raise RuntimeError(f"Cannot open video source: {self.input_url}")
                print(f"[stream] Waiting for source: {self.input_url}")
                time.sleep(self.reconnect_interval_sec)
                continue

            assert self._cap is not None
            ok, frame = self._cap.read()
            if not ok or frame is None:
                self.close()
                if not self.reconnect:
                    break
                print("[stream] Frame read failed; reconnecting...")
                time.sleep(self.reconnect_interval_sec)
                continue

            frame = self._normalize_frame(frame)
            self._frame_id += 1
            timestamp_ms = int((time.perf_counter() - self._started) * 1000)
            self._update_fps()
            h, w = frame.shape[:2]
            event = FrameEvent(
                session_id=self.session_id,
                camera_id=self.camera_id,
                camera_role=self.camera_role,
                frame_id=self._frame_id,
                timestamp_ms=timestamp_ms,
                width=w,
                height=h,
                fps_est=self._fps_est,
            )
            yield VideoFrame(event=event, image_bgr=frame)

    def _normalize_frame(self, frame: np.ndarray) -> np.ndarray:
        if self.rotate == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotate == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif self.rotate == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if self.mirror:
            frame = cv2.flip(frame, 1)
        if self.max_width and frame.shape[1] > self.max_width:
            scale = self.max_width / frame.shape[1]
            frame = cv2.resize(frame, (self.max_width, int(frame.shape[0] * scale)))
        return frame

    def _update_fps(self) -> None:
        self._fps_count += 1
        now = time.perf_counter()
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._fps_est = self._fps_count / elapsed
            self._fps_count = 0
            self._last_fps_time = now
