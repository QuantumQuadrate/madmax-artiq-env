"""CPU/kernel branch timing comparison using the same ttl5 -> ttl0 loopback.

Connections:
    ttl5 / dio0[5] -> ttl0 / dio0[0]
    scope CH1 on ttl5
    scope CH2 on ttl6 / dio0[6]

This follows the old software pattern: gate SPCM0, fetch timestamp in Python
kernel code, branch, then schedule ttl6 at click + cpu_action_offset_mu.
Lower the offset until the experiment underflows or becomes unreliable.
"""

from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.experiment import kernel
from artiq.language.core import at_mu
from artiq.language.core import delay_mu
from artiq.language.core import now_mu
from artiq.language.core import parallel
from artiq.language.core import sequential
from artiq.language.units import us
import numpy as np


class CpuBranchTimingComparison(EnvExperiment):
    """Software branch path: click timestamp read by kernel, ttl6 scheduled."""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl0")
        self.setattr_device("ttl5")
        self.setattr_device("ttl6")
        self.setattr_device("led0")
        self.setattr_argument(
            "repeats", NumberValue(5, min=1, max=100, step=1, ndecimals=0)
        )
        self.setattr_argument(
            "cpu_action_offset_mu",
            NumberValue(5000, min=100, max=1000000, step=100, ndecimals=0),
        )
        self.setattr_argument(
            "output_width_mu",
            NumberValue(1000, min=16, max=100000, step=8, ndecimals=0),
        )

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        self.ttl0.input()
        delay_mu(10000)

        for index in range(self.repeats):
            self.core.break_realtime()
            gate_start_mu = now_mu() + 20000
            expected_pulse_mu = gate_start_mu + 2000
            cpu_action_offset_mu = np.int64(self.cpu_action_offset_mu)
            output_width_mu = np.int64(self.output_width_mu)

            at_mu(gate_start_mu)
            with parallel:
                gate_end_mu = self.ttl0.gate_rising(50 * us)
                with sequential:
                    delay_mu(2000)
                    self.ttl5.pulse_mu(1000)

            click_mu = self.ttl0.timestamp_mu(gate_end_mu)

            if click_mu > 0:
                at_mu(click_mu + cpu_action_offset_mu)
                self.ttl6.pulse_mu(output_width_mu)

            self.core.break_realtime()
            print("cpu_branch index", index)
            print("cpu_branch expected_ttl5_mu", expected_pulse_mu)
            print("cpu_branch ttl0_timestamp_mu", click_mu)
            print("cpu_branch ttl0_minus_ttl5_mu", click_mu - expected_pulse_mu)
            print("cpu_branch ttl6_offset_from_click_mu", cpu_action_offset_mu)

            self.core.break_realtime()
            self.led0.pulse_mu(1000)
            delay_mu(100000)
