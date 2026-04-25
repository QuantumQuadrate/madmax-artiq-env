"""Check the physical ttl5 -> ttl0 loopback before using the entangler core.

Connections:
    ttl5 / dio0[5] -> ttl0 / dio0[0]

Put a scope on ttl5 if you want to verify the source pulse. This test prints the
ttl0 timestamp and the measured timestamp delta from the scheduled ttl5 pulse.
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


class Ttl5ToTtl0LoopbackCheck(EnvExperiment):
    """Direct TTL loopback check, independent of the atom-photon gateware."""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl0")
        self.setattr_device("ttl5")
        self.setattr_device("led0")
        self.setattr_argument(
            "repeats", NumberValue(5, min=1, max=100, step=1, ndecimals=0)
        )
        self.setattr_argument(
            "pulse_delay_mu",
            NumberValue(2000, min=100, max=100000, step=100, ndecimals=0),
        )
        self.setattr_argument(
            "pulse_width_mu",
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
            pulse_delay_mu = np.int64(self.pulse_delay_mu)
            pulse_width_mu = np.int64(self.pulse_width_mu)
            expected_pulse_mu = gate_start_mu + pulse_delay_mu

            at_mu(gate_start_mu)
            with parallel:
                gate_end_mu = self.ttl0.gate_rising(50 * us)
                with sequential:
                    delay_mu(pulse_delay_mu)
                    self.ttl5.pulse_mu(pulse_width_mu)

            click_mu = self.ttl0.timestamp_mu(gate_end_mu)
            self.core.break_realtime()

            print("loopback index", index)
            print("loopback expected_ttl5_mu", expected_pulse_mu)
            print("loopback ttl0_timestamp_mu", click_mu)
            print("loopback ttl0_minus_ttl5_mu", click_mu - expected_pulse_mu)

            self.core.break_realtime()
            self.led0.pulse_mu(1000)
            delay_mu(100000)
