"""高光事件：交火时只压缩有变化的 HUD，赛后再 OCR 击杀计数。"""


def kill_events(samples):
    """从 (时间, 击杀数或 None) 推出已确认的增长；连续两次相同才采用。"""
    baseline = pending = None
    events = []
    for when, value in samples:
        if value is None or value < 0:
            continue
        if baseline is None:
            baseline = value  # 中途启动 Evo 时，第一次数值不能当作本次击杀
            continue
        if value <= baseline:
            pending = None
            continue
        if pending is not None and pending[0] == value:
            events.append({"occurred_at": f"{pending[1]:%Y-%m-%d %H:%M:%S}", "kind": "kill",
                           "amount": value - baseline, "source": "对局中击杀计数"})
            baseline, pending = value, None
        else:
            pending = (value, when)
    return events


class HighlightSampler:
    """对局中采集击杀行的少量压缩帧，内存上限由 max_samples 控制。"""

    def __init__(self, hud, max_samples=128, change=2.0):
        self.hud, self.max_samples, self.change = hud, max_samples, change
        self.samples = []
        self.last_row = None
        self.changed_at = None
        self.stable_frames = 0
        self.overflow = False

    def observe(self, snip, when, force=False):
        import numpy as np
        from hud import PackedSnip

        row = snip.gray(self.hud.cfg["top_right"]["kp_row"]["area"])
        next_row = row.astype(np.int16)
        changed = self.last_row is None or float(np.mean(np.abs(next_row - self.last_row))) >= self.change
        if changed:
            self.last_row, self.changed_at, self.stable_frames = next_row, when, 0
        else:
            self.stable_frames += 1
        if not (force or self.stable_frames == 2):
            return
        if len(self.samples) >= self.max_samples:
            self.overflow = True
            return
        self.samples.append((self.changed_at or when, PackedSnip(snip)))

    def finish(self, last_snip=None, when=None):
        if last_snip is not None and when is not None:
            self.observe(last_snip, when, force=True)
        readings = []
        for at, packed in self.samples:
            try:
                readings.append((at, self.hud.read_kill_count(packed.unpack())))
            except ValueError:
                readings.append((at, None))
        self.samples.clear()
        self.last_row = None
        self.changed_at = None
        return kill_events(readings)
