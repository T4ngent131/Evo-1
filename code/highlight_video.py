"""本地高光录像。独立线程被动采集桌面和系统输出声音；比赛结束后切出片段。"""

import queue
import threading
import time
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

import app_settings
import storage
from paths import DATA_DIR

SETTING_KEY = "highlight_video"
FPS = 10
WIDTH, HEIGHT = 960, 540
RATE = 48000
BEFORE, AFTER = 15, 10


def _fit(frame):
    h, w = frame.shape[:2]
    scale = min(WIDTH / w, HEIGHT / h)
    nw, nh = max(2, int(w * scale) // 2 * 2), max(2, int(h * scale) // 2 * 2)
    fitted = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    result = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    result[(HEIGHT - nh) // 2:(HEIGHT + nh) // 2, (WIDTH - nw) // 2:(WIDTH + nw) // 2] = fitted
    return result


class SessionRecorder:
    """每次采集过程录一个临时文件；关闭采集时生成每条高光片段。"""

    def __init__(self, log, folder=None, camera_factory=None, audio_factory=None, after_id=0):
        self.log = log
        self.folder = Path(folder or DATA_DIR / "highlights")
        self.folder.mkdir(parents=True, exist_ok=True)
        self.started = datetime.now()
        self.start_clock = time.monotonic()
        self.path = self.folder / f"session_{self.started:%Y%m%d_%H%M%S}.mp4"
        self.camera_factory = camera_factory
        self.audio_factory = audio_factory
        self.after_id = after_id
        self.items = queue.Queue(maxsize=6)
        self.stop_event = threading.Event()
        self.errors = []
        self.threads = []

    def start(self):
        import av  # 录制开关关闭时，不加载编解码库
        import dxcam
        import soundcard as sc

        self.av = av
        camera_factory = self.camera_factory or (lambda: dxcam.create(output_color="BGR", processor_backend="numpy"))
        audio_factory = self.audio_factory or (lambda: sc.get_microphone(
            id=str(sc.default_speaker().name), include_loopback=True).recorder(
                samplerate=RATE, channels=2, blocksize=2048))
        for name, target in (("video", lambda: self._video(camera_factory)),
                             ("audio", lambda: self._audio(audio_factory)),
                             ("encode", self._encode)):
            thread = threading.Thread(target=target, name=f"evo-highlight-{name}", daemon=True)
            thread.start()
            self.threads.append(thread)
        self.log("高光录像已启动：960×540、10 帧/秒；包含系统输出声音")

    def _put(self, item):
        try:
            self.items.put_nowait(item)
        except queue.Full:
            pass  # 编码跟不上时丢帧，不能拖慢游戏或 OCR

    def _video(self, camera_factory):
        camera = None
        try:
            camera = camera_factory()
            while not self.stop_event.is_set():
                tick = time.monotonic()
                frame = camera.grab(new_frame_only=False)
                if frame is not None:
                    self._put(("video", tick - self.start_clock, _fit(frame)))
                self.stop_event.wait(max(0, 1 / FPS - (time.monotonic() - tick)))
        except Exception as exc:
            self.errors.append(f"屏幕录制失败：{exc}")
        finally:
            if camera is not None:
                camera.release()

    def _audio(self, audio_factory):
        try:
            with audio_factory() as recorder:
                while not self.stop_event.is_set():
                    samples = recorder.record(numframes=2048)
                    self._put(("audio", time.monotonic() - self.start_clock, samples.copy()))
        except Exception as exc:
            self.errors.append(f"声音录制失败：{exc}")

    def _encode(self):
        try:
            with self.av.open(str(self.path), "w") as out:
                video = out.add_stream("libx264", rate=FPS)
                video.width, video.height, video.pix_fmt = WIDTH, HEIGHT, "yuv420p"
                video.options = {"preset": "ultrafast", "crf": "29"}
                audio = out.add_stream("aac", rate=RATE)
                audio.layout = "stereo"
                last_video = -1
                audio_pts = 0
                while not self.stop_event.is_set() or not self.items.empty():
                    try:
                        kind, elapsed, data = self.items.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if kind == "video":
                        pts = round(elapsed * FPS)
                        if pts <= last_video:
                            continue
                        frame = self.av.VideoFrame.from_ndarray(data, format="bgr24")
                        frame.pts, frame.time_base = pts, Fraction(1, FPS)
                        last_video = pts
                        for packet in video.encode(frame):
                            out.mux(packet)
                    else:
                        data = np.asarray(data, dtype=np.float32)
                        if data.ndim != 2 or data.shape[1] != 2:
                            continue
                        frame = self.av.AudioFrame.from_ndarray(data.T.copy(), format="fltp", layout="stereo")
                        frame.sample_rate = RATE
                        frame.pts, frame.time_base = audio_pts, Fraction(1, RATE)
                        audio_pts += data.shape[0]
                        for packet in audio.encode(frame):
                            out.mux(packet)
                for stream in (video, audio):
                    for packet in stream.encode():
                        out.mux(packet)
        except Exception as exc:
            self.errors.append(f"视频编码失败：{exc}")

    def finish(self, db_path):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=8)
        if any(thread.is_alive() for thread in self.threads):
            self.log("⚠ 高光录像线程未能及时退出，临时录像保留以便恢复")
            return
        for error in self.errors:
            self.log(f"⚠ {error}")
        if self.errors:
            self.log(f"⚠ 高光录像不完整，临时文件保留在 {self.path}")
            return
        if not self.path.is_file():
            return
        try:
            self._extract_all(db_path)
        except Exception as exc:
            self.log(f"⚠ 高光片段生成失败，原始录像保留在 {self.path}：{exc}")
            return
        self.path.unlink(missing_ok=True)

    def _extract_all(self, db_path):
        conn = storage.connect(db_path)
        try:
            rows = conn.execute("SELECT highlight_id, occurred_at FROM highlights WHERE clip_path IS NULL "
                                "AND highlight_id > ? "
                                "AND occurred_at BETWEEN ? AND ? ORDER BY occurred_at",
                                (self.after_id, f"{self.started:%Y-%m-%d %H:%M:%S}",
                                 f"{datetime.now():%Y-%m-%d %H:%M:%S}")).fetchall()
            for row in rows:
                at = datetime.strptime(row["occurred_at"], "%Y-%m-%d %H:%M:%S")
                start = max(0, (at - self.started).total_seconds() - BEFORE)
                end = (at - self.started).total_seconds() + AFTER
                target = self.folder / f"{row['highlight_id']}.mp4"
                try:
                    extract_clip(self.path, target, start, end)
                    storage.set_highlight_clip(conn, row["highlight_id"], str(target.relative_to(DATA_DIR)))
                    self.log(f"高光视频：{target.name}（事件前 15 秒、后 10 秒）")
                except Exception as exc:
                    target.unlink(missing_ok=True)
                    self.log(f"⚠ 高光 {row['highlight_id']} 视频生成失败：{exc}")
        finally:
            conn.close()


def extract_clip(source, target, start, end):
    """按实际播放时间截取，重新编码以保证片段可以独立播放。"""
    import av

    with av.open(str(source)) as src, av.open(str(target), "w") as dst:
        video_in = src.streams.video[0]
        audio_in = src.streams.audio[0] if src.streams.audio else None
        video = dst.add_stream("libx264", rate=FPS)
        video.width, video.height, video.pix_fmt = video_in.width, video_in.height, "yuv420p"
        video.options = {"preset": "ultrafast", "crf": "29"}
        audio = dst.add_stream("aac", rate=RATE) if audio_in is not None else None
        if audio is not None:
            audio.layout = "stereo"
        src.seek(max(0, int((start - 2) * 1_000_000)), backward=True)
        last_video = -1
        audio_pts = 0
        for frame in src.decode():
            if frame.time is None:
                continue
            if frame.time < start:
                continue
            if frame.time > end:
                break
            if isinstance(frame, av.VideoFrame):
                pts = round((frame.time - start) * FPS)
                if pts <= last_video:
                    continue
                frame.pts, frame.time_base = pts, Fraction(1, FPS)
                last_video = pts
                for packet in video.encode(frame):
                    dst.mux(packet)
            elif audio is not None and isinstance(frame, av.AudioFrame):
                frame.pts, frame.time_base = audio_pts, Fraction(1, RATE)
                audio_pts += frame.samples
                for packet in audio.encode(frame):
                    dst.mux(packet)
        if last_video < 0:
            raise ValueError("片段范围内没有视频帧")
        for stream in (video, audio):
            if stream is not None:
                for packet in stream.encode():
                    dst.mux(packet)
