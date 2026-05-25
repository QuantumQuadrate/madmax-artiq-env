"""Safe register-path smoke test for the atom_photon_parity_6 helper.

This experiment enables the helper but keeps idle and active output states equal,
so no output bit should change state. It should finish with no single-click
success unless real SPCM edges are already connected.
"""

from artiq.experiment import *


class AtomPhotonParity6Smoke(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument("run_length_us", NumberValue(default=50.0, min=1.0))
        self.setattr_argument("attempt_period_us", NumberValue(default=10.0, min=1.0))
        self.setattr_argument("gate_start_us", NumberValue(default=1.0, min=0.1))
        self.setattr_argument("gate_stop_us", NumberValue(default=5.0, min=0.2))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.clear()
        self.entangler.configure(1)

        run_length_mu = self.core.seconds_to_mu(self.run_length_us * 1e-6)
        attempt_period_mu = self.core.seconds_to_mu(self.attempt_period_us * 1e-6)
        gate_start_mu = self.core.seconds_to_mu(self.gate_start_us * 1e-6)
        gate_stop_mu = self.core.seconds_to_mu(self.gate_stop_us * 1e-6)

        self.entangler.set_run_length_mu(run_length_mu)
        self.entangler.set_num_attempts(1)
        self.entangler.set_attempt_period_mu(attempt_period_mu)
        self.entangler.set_gate_mu(gate_start_mu, gate_stop_mu)
        self.entangler.set_output_states(0, 0)
        self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(5e-6))

        _, status = self.entangler.start()

        self.core.break_realtime()

        print(
            "status",
            status,
            "outcome",
            self.entangler.get_outcome(),
            "click_ts",
            self.entangler.get_click_timestamp_mu(),
            "attempt",
            self.entangler.get_attempt_index(),
        )

