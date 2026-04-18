"""
TTL Pulse Timestamper
=====================
Opens a gate window on selected TTL input channels and records the RTIO
timestamp of every rising edge detected during that window.

Compatible input channels on this board: ttl0-3, ttl8-19.
  (ttl4-7 and ttl20-23 are output-only and will not work here.)

Datasets written per channel:
  ttl_timestamps/ttlN/count         – number of events captured
  ttl_timestamps/ttlN/timestamps_s  – absolute RTIO timestamps [s]
  ttl_timestamps/ttlN/rel_times_s   – timestamps relative to gate open [s]

Note: the RTIO input FIFO holds ~64 events per channel. If your pulse rate
is high enough to overflow it during the gate window, events will be dropped.
Keep (rate * gate_duration) < 64 per channel for lossless capture.
"""

from artiq.experiment import *
import numpy as np


class TTLTimestamper(EnvExperiment):
    """TTL Pulse Timestamper"""

    def build(self):
        self.setattr_device("core")

        self.setattr_argument(
            "channels",
            StringValue(default="0,1,2,3"),
            group="Channels",
        )
        self.setattr_argument(
            "gate_duration_us",
            NumberValue(default=1000.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Acquisition",
        )
        self.setattr_argument(
            "max_events_per_channel",
            NumberValue(default=500, min=1, max=10000, step=1, ndecimals=0),
            group="Acquisition",
        )

    def prepare(self):
        self.channel_list = [int(c.strip()) for c in self.channels.split(",")]
        self.ttl_inputs = [self.get_device("ttl{}".format(n)) for n in self.channel_list]
        self.gate_mu = self.core.seconds_to_mu(self.gate_duration_us * 1e-6)

        # Storage filled by RPC callbacks during the kernel run
        self._raw_ts = [[] for _ in self.channel_list]
        self._gate_start_mu = 0

    # ------------------------------------------------------------------ #
    # RPC callbacks — run on the host, called from the kernel             #
    # ------------------------------------------------------------------ #

    @rpc
    def _record_gate_start(self, t_mu: TInt64):
        self._gate_start_mu = int(t_mu)

    @rpc
    def _record_event(self, ch_idx: TInt32, t_mu: TInt64):
        self._raw_ts[ch_idx].append(int(t_mu))

    # ------------------------------------------------------------------ #
    # Kernel                                                               #
    # ------------------------------------------------------------------ #

    @kernel
    def run(self):
        self.core.reset()

        # Put all selected channels into input mode
        for ttl in self.ttl_inputs:
            ttl.input()

        self.core.break_realtime()

        # Snapshot the gate-open time, then open all gates simultaneously
        self._record_gate_start(now_mu())
        with parallel:
            for ttl in self.ttl_inputs:
                ttl.gate_rising_mu(self.gate_mu)

        # After the parallel block, now_mu() == gate close time
        t_gate_end = now_mu()

        # Drain the RTIO input FIFO for each channel.
        # timestamp_mu(deadline) returns the next event timestamp, or -1
        # if no more events arrived before the deadline.
        for i in range(len(self.ttl_inputs)):
            for _ in range(self.max_events_per_channel):
                t = self.ttl_inputs[i].timestamp_mu(t_gate_end)
                if t < 0:
                    break
                self._record_event(i, t)

    # ------------------------------------------------------------------ #
    # Host-side analysis — called automatically by the master after run() #
    # ------------------------------------------------------------------ #

    def analyze(self):
        ref_mu = self._gate_start_mu
        ref_period = self.core.ref_period  # seconds per machine unit (1e-9 s)

        print("=== TTL Timestamper Results ===")
        print("Gate duration: {:.1f} us".format(self.gate_duration_us))

        for i, ch in enumerate(self.channel_list):
            ts_mu = np.array(self._raw_ts[i], dtype=np.int64)
            n = len(ts_mu)

            if n > 0:
                # Absolute timestamps in seconds (float64 is exact for typical run durations)
                ts_abs_s = ts_mu.astype(np.float64) * ref_period
                # Gate-relative timestamps in seconds
                rel_s = (ts_mu - ref_mu).astype(np.float64) * ref_period
            else:
                ts_abs_s = np.zeros(0, dtype=np.float64)
                rel_s = np.zeros(0, dtype=np.float64)

            self.set_dataset(
                "ttl_timestamps/ttl{}/count".format(ch),
                n,
                broadcast=True,
                archive=True,
            )
            self.set_dataset(
                "ttl_timestamps/ttl{}/timestamps_s".format(ch),
                ts_abs_s,
                broadcast=True,
                archive=True,
            )
            self.set_dataset(
                "ttl_timestamps/ttl{}/rel_times_s".format(ch),
                rel_s,
                broadcast=True,
                archive=True,
            )

            print("ttl{}: {} event(s)".format(ch, n))
            if n > 0:
                print("  first: {:.3f} us  last: {:.3f} us  span: {:.3f} us".format(
                    rel_s[0] * 1e6,
                    rel_s[-1] * 1e6,
                    (rel_s[-1] - rel_s[0]) * 1e6 if n > 1 else 0.0,
                ))
            if n >= self.max_events_per_channel:
                print("  WARNING: hit max_events_per_channel limit — "
                      "some events may have been dropped.")
