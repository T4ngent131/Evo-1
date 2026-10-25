"""不用抓取真实桌面或声音，检验内置录像与片段确实含视频、音轨。"""

import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))


def main():
    try:
        import av
        import numpy as np
    except ImportError:
        print("SKIP 内置录像测试：尚未安装 requirements-highlights.txt")
        return True

    from highlight_video import SessionRecorder, extract_clip
    import storage
    from paths import DATA_DIR

    class Camera:
        def grab(self, **_):
            return np.zeros((360, 640, 3), dtype=np.uint8)

        def release(self):
            pass

    class Audio:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def record(self, numframes):
            time.sleep(numframes / 48000)
            return np.zeros((numframes, 2), dtype=np.float32)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=DATA_DIR) as folder:
        recorder = SessionRecorder(lambda _: None, folder=folder, camera_factory=Camera, audio_factory=Audio)
        recorder.start()
        time.sleep(1.3)
        recorder.stop_event.set()
        for thread in recorder.threads:
            thread.join(5)
        if recorder.errors or any(thread.is_alive() for thread in recorder.threads):
            print(f"FAIL 录制线程：{recorder.errors}")
            return False
        target = Path(folder) / "clip.mp4"
        extract_clip(recorder.path, target, 0.3, 1.0)
        with av.open(str(target)) as result:
            video = sum(1 for _ in result.decode(video=0))
            kinds = {stream.type for stream in result.streams}
        ok = video >= 5 and kinds == {"video", "audio"}
        print(f"{'OK' if ok else 'FAIL'} 合成高光视频：{video} 帧，音视频轨 {sorted(kinds)}")
        database = Path(folder) / "evo.db"
        conn = storage.connect(database)
        match_id = storage.insert_match(conn, {"ended_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}"})
        storage.save_highlights(conn, match_id, [{"occurred_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
                                                  "kind": "champion", "source": "test"}])
        recorder.finish(database)
        event = storage.highlights_of(conn, match_id)[0]
        clip = DATA_DIR / event["clip_path"] if event["clip_path"] else None
        saved = clip is not None and clip.is_file() and not recorder.path.exists()
        print(f"{'OK' if saved else 'FAIL'} 事件关联片段并清除临时录像")
        conn.close()
        return ok and saved


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
