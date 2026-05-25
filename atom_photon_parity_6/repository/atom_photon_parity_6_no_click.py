"""No-click retry/timeout check for atom_photon_parity_6.

Run this with SPCM inputs disconnected or dark. The helper should retry until
``num_attempts`` is exhausted, then finish with timeout set and outcome 0.
"""

from artiq.experiment import *


class AtomPhotonParity6NoClick(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument("num_attempts", NumberValue(default=4, min=1, step=1, ndecimals=0))
        self.setattr_argument("attempt_period_us", NumberValue(default=10.0, min=2.0))
        self.setattr_argument("gate_start_us", NumberValue(default=2.0, min=0.1))
        self.setattr_argument("gate_stop_us", NumberValue(default=8.0, min=0.2))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.clear()
        self.entangler.configure(1)

        attempts = int(self.num_attempts)
        attempt_period_mu = self.core.seconds_to_mu(self.attempt_period_us * 1e-6)
        gate_start_mu = self.core.seconds_to_mu(self.gate_start_us * 1e-6)
        gate_stop_mu = self.core.seconds_to_mu(self.gate_stop_us * 1e-6)
        run_length_mu = attempt_period_mu * (attempts + 2)

        self.entangler.set_run_length_mu(run_length_mu)
        self.entangler.set_num_attempts(attempts)
        self.entangler.set_attempt_period_mu(attempt_period_mu)
        self.entangler.set_gate_mu(gate_start_mu, gate_stop_mu)
        self.entangler.set_output_states(0, 0)
        self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(5e-6))

        _, status = self.entangler.start()

        self.core.break_realtime()

        print(
            "no_click status",
            status,
            "outcome",
            self.entangler.get_outcome(),
            "attempt",
            self.entangler.get_attempt_index(),
            "spcm0_ts",
            self.entangler.get_spcm_timestamp_mu(0),
            "spcm1_ts",
            self.entangler.get_spcm_timestamp_mu(1),
        )
