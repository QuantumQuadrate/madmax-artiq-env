"""Entangler hardware test that SAVES results as ARTIQ datasets.

Wiring (loopback):
  ttl4 (output) -> ttl0 (input)

After running from artiq_dashboard:
  Check Datasets panel:
    entangler.success_rate
    entangler.status_hist
    entangler.reason_hist
    entangler.ts_hist
"""

import artiq.language.environment as artiq_env
import numpy as np
from artiq.language.core import kernel, delay, parallel
import artiq.language.units as aq_units


class EntanglerDatasetTest(artiq_env.EnvExperiment):
    def build(self):
        self.setattr_device("core")

        # Device names (match your device_db)
        self.ent = self.get_device("entangler0")
        self.ins = [self.get_device(f"ttl{i}") for i in range(0, 4)]   # inputs
        self.out0 = self.get_device("ttl4")                            # output

        # Parameters
        self.nshots = 50
        self.timeout = 10000  # <-- plain int (mu)

        self.cycle_len = 1200
        self.out_start = 100
        self.out_stop = 1000
        self.in_start = 10
        self.in_stop = 1000

        # Pattern for input0 (ttl0) firing
        self.pattern_list = [0b0001]

    def prepare(self):
        # Initialize datasets
        self.set_dataset("entangler.nshots", self.nshots, broadcast=True)
        self.set_dataset("entangler.pattern_list", self.pattern_list, broadcast=True)
        self.set_dataset("entangler.success_rate", 0.0, broadcast=True)
        self.set_dataset("entangler.status_hist", [], broadcast=True)
        self.set_dataset("entangler.reason_hist", [], broadcast=True)
        self.set_dataset("entangler.end_ts_hist", [], broadcast=True)
        self.set_dataset("entangler.ts_hist", [], broadcast=True)

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        # Configure IO
        for t in self.ins:
            t.input()

        # One-time entangler setup
        self.ent.init()
        self.ent.set_cycle_length_mu(self.cycle_len)

        # Configure timing windows
        for ch in range(8):
            self.ent.set_timing_mu(ch, self.out_start, self.out_stop)      # outputs
        for ch in range(8):
            self.ent.set_timing_mu(8 + ch, self.in_start, self.in_stop)    # inputs

        self.ent.set_patterns(self.pattern_list)

        # Storage for results (kernel-side lists)
        reason_hist = [0] * self.nshots
        status_hist = [0] * self.nshots
        end_ts_hist = [0] * self.nshots
        ts_hist0 = [0] * self.nshots
        ts_hist1 = [0] * self.nshots
        ts_hist2 = [0] * self.nshots
        ts_hist3 = [0] * self.nshots
        success_count = 0

        for i in range(self.nshots):
            self.ent.set_config(enable=True, standalone=True)

            with parallel:
                # Arm gates (convert timeout to int64 explicitly)
                self.ins[0].gate_rising_mu(np.int64(self.timeout))
                self.ins[1].gate_rising_mu(np.int64(self.timeout))
                self.ins[2].gate_rising_mu(np.int64(self.timeout))
                self.ins[3].gate_rising_mu(np.int64(self.timeout))

                # Pulse output during the gate window (loopback makes ttl0 rise)
                self.out0.pulse(2 * aq_units.us)

                end_ts, reason = self.ent.run_mu(self.timeout)

            self.core.break_realtime()
            self.ent.set_config(enable=False)

            status = self.ent.get_status()
            ts0 = self.ent.get_timestamp_mu(0)
            ts1 = self.ent.get_timestamp_mu(1)
            ts2 = self.ent.get_timestamp_mu(2)
            ts3 = self.ent.get_timestamp_mu(3)

            reason_hist[i] = reason
            status_hist[i] = status
            end_ts_hist[i] = end_ts
            ts_hist0[i] = ts0
            ts_hist1[i] = ts1
            ts_hist2[i] = ts2
            ts_hist3[i] = ts3

            if status & 0b010:
                success_count += 1

            delay(200 * aq_units.us)

        # Push to datasets (single writes)
        self.set_dataset("entangler._success_count", success_count, broadcast=True)
        self.set_dataset("entangler._reason_hist", reason_hist, broadcast=True)
        self.set_dataset("entangler._status_hist", status_hist, broadcast=True)
        self.set_dataset("entangler._end_ts_hist", end_ts_hist, broadcast=True)
        self.set_dataset("entangler._ts0", ts_hist0, broadcast=True)
        self.set_dataset("entangler._ts1", ts_hist1, broadcast=True)
        self.set_dataset("entangler._ts2", ts_hist2, broadcast=True)
        self.set_dataset("entangler._ts3", ts_hist3, broadcast=True)

    def analyze(self):
        nshots = int(self.nshots)
        success_count = int(self.get_dataset("entangler._success_count"))

        reason_hist = list(self.get_dataset("entangler._reason_hist"))
        status_hist = list(self.get_dataset("entangler._status_hist"))
        end_ts_hist = list(self.get_dataset("entangler._end_ts_hist"))

        ts0 = list(self.get_dataset("entangler._ts0"))
        ts1 = list(self.get_dataset("entangler._ts1"))
        ts2 = list(self.get_dataset("entangler._ts2"))
        ts3 = list(self.get_dataset("entangler._ts3"))

        ts_hist = [[ts0[i], ts1[i], ts2[i], ts3[i]] for i in range(nshots)]
        success_rate = success_count / float(nshots) if nshots else 0.0

        self.set_dataset("entangler.success_rate", success_rate, broadcast=True)
        self.set_dataset("entangler.reason_hist", reason_hist, broadcast=True)
        self.set_dataset("entangler.status_hist", status_hist, broadcast=True)
        self.set_dataset("entangler.end_ts_hist", end_ts_hist, broadcast=True)
        self.set_dataset("entangler.ts_hist", ts_hist, broadcast=True)

        print(f"[EntanglerDatasetTest] success_rate={success_rate:.3f} ({success_count}/{nshots})")
