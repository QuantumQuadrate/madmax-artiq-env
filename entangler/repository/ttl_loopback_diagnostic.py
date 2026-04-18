from artiq.experiment import *
import numpy as np


class TTLLoopbackDiagnostic(EnvExperiment):
    def build(self):
        self.setattr_device("core")

        # Observed dashboard-to-physical mapping:
        #   ttl7 -> physical TTL6 output, jumpered to physical TTL0 input
        #   ttl8 -> physical TTL7 output, jumpered to physical TTL1 input
        #   so the dashboard names to test are ttl7 -> ttl2 and ttl8 -> ttl3.
        self.input0 = self.get_device("ttl2")
        self.input1 = self.get_device("ttl3")
        self.output0 = self.get_device("ttl7")
        self.output1 = self.get_device("ttl8")

    @kernel
    def _run_pair(self, ttl_in, ttl_out) -> TTuple([TInt32, TInt64]):
        self.core.reset()
        ttl_in.input()
        ttl_out.output()
        ttl_out.off()
        self.core.break_realtime()

        # First check the static level with a long high pulse.
        ttl_out.on()
        delay(100 * us)
        ttl_in.sample_input()
        delay(1 * us)
        level = ttl_in.sample_get()
        ttl_out.off()
        delay(100 * us)

        # Then check rising-edge timestamping with a wide pulse and gate.
        t_start = now_mu()
        with parallel:
            t_end = ttl_in.gate_rising_mu(np.int64(500000))
            at_mu(t_start + 100000)
            ttl_out.pulse_mu(np.int64(100000))

        ts = ttl_in.timestamp_mu(t_end)
        self.core.break_realtime()
        return level, ts

    def run(self):
        level0, ts0 = self._run_pair(self.input0, self.output0)
        level1, ts1 = self._run_pair(self.input1, self.output1)

        self.set_dataset("loopback/input0_level", int(level0), broadcast=True, archive=True)
        self.set_dataset("loopback/input0_timestamp_mu", int(ts0), broadcast=True, archive=True)
        self.set_dataset("loopback/input1_level", int(level1), broadcast=True, archive=True)
        self.set_dataset("loopback/input1_timestamp_mu", int(ts1), broadcast=True, archive=True)

        print("ttl7 -> ttl2:", "level=", int(level0), "timestamp_mu=", int(ts0))
        print("ttl8 -> ttl3:", "level=", int(level1), "timestamp_mu=", int(ts1))
