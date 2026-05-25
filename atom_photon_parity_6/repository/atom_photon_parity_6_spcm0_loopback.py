"""SPCM0 single-click loopback test.

Wire ``entangler_output0`` to ``entangler_input0`` before running. Output 0 is
used as a fake photon pulse inside the SPCM gate. A successful run should report
outcome 1 and a nonzero click timestamp.
"""

from artiq.experiment import *


class AtomPhotonParity6SPCM0Loopback(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument("photon_start_us", NumberValue(default=2.0, min=0.1))
        self.setattr_argument("photon_width_us", NumberValue(default=1.0, min=0.1))
        self.setattr_argument("branch_offset_us", NumberValue(default=2.0, min=0.1))
        self.setattr_argument("branch_width_us", NumberValue(default=1.0, min=0.1))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.clear()
        self.entangler.configure(1)

        photon_start_mu = self.core.seconds_to_mu(self.photon_start_us * 1e-6)
        photon_stop_mu = photon_start_mu + self.core.seconds_to_mu(self.photon_width_us * 1e-6)
        branch_start_mu = self.core.seconds_to_mu(self.branch_offset_us * 1e-6)
        branch_stop_mu = branch_start_mu + self.core.seconds_to_mu(self.branch_width_us * 1e-6)

        self.entangler.set_run_length_mu(self.core.seconds_to_mu(80e-6))
        self.entangler.set_num_attempts(1)
        self.entangler.set_attempt_period_mu(self.core.seconds_to_mu(20e-6))
        self.entangler.set_gate_mu(self.core.seconds_to_mu(1e-6), self.core.seconds_to_mu(8e-6))
        self.entangler.set_output_states(0b0000, 0b1111)
        self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(8e-6))

        self.entangler.set_attempt_window_mu(0, photon_start_mu, photon_stop_mu)
        self.entangler.set_branch_window_mu(0, 1, branch_start_mu, branch_stop_mu)
        self.entangler.set_branch_window_mu(1, 2, branch_start_mu, branch_stop_mu)

        _, status = self.entangler.start()

        print(
            "spcm0_loopback status",
            status,
        )
