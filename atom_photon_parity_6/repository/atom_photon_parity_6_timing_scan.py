"""Scan click-relative branch pulse timing.

Wire ``entangler_output0`` to ``entangler_input0``. Scope output 1 while this
scan runs; output 1 is the branch-0 pulse scheduled after the fake photon click.
"""

from artiq.experiment import *


class AtomPhotonParity6TimingScan(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument("first_offset_us", NumberValue(default=1.0, min=0.1))
        self.setattr_argument("last_offset_us", NumberValue(default=6.0, min=0.1))
        self.setattr_argument("step_us", NumberValue(default=1.0, min=0.1))
        self.setattr_argument("branch_width_us", NumberValue(default=0.5, min=0.1))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.configure(1)

        photon_start_mu = self.core.seconds_to_mu(2e-6)
        photon_stop_mu = self.core.seconds_to_mu(3e-6)
        branch_width_mu = self.core.seconds_to_mu(self.branch_width_us * 1e-6)

        offset_us = self.first_offset_us
        while offset_us <= self.last_offset_us:
            branch_start_mu = self.core.seconds_to_mu(offset_us * 1e-6)
            branch_stop_mu = branch_start_mu + branch_width_mu

            self.entangler.clear()
            self.entangler.set_run_length_mu(self.core.seconds_to_mu(100e-6))
            self.entangler.set_num_attempts(1)
            self.entangler.set_attempt_period_mu(self.core.seconds_to_mu(20e-6))
            self.entangler.set_gate_mu(self.core.seconds_to_mu(1e-6), self.core.seconds_to_mu(8e-6))
            self.entangler.set_output_states(0b0000, 0b1111)
            self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(10e-6))
            self.entangler.set_attempt_window_mu(0, photon_start_mu, photon_stop_mu)
            self.entangler.set_branch_window_mu(0, 1, branch_start_mu, branch_stop_mu)

            _, status = self.entangler.start()

            self.core.break_realtime()
            print(
                "offset_us",
                offset_us,
                "status",
                status,
                "outcome",
                self.entangler.get_outcome(),
                "click_ts",
                self.entangler.get_click_timestamp_mu(),
            )
            delay(100 * us)
            offset_us += self.step_us

