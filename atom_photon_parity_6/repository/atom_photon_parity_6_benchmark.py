"""Measure average RTIO machine units per parity-helper transaction."""

from artiq.experiment import *


class AtomPhotonParity6Benchmark(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument("repetitions", NumberValue(default=1000, min=1, step=1, ndecimals=0))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.configure(1)
        self.entangler.set_run_length_mu(self.core.seconds_to_mu(30e-6))
        self.entangler.set_num_attempts(1)
        self.entangler.set_attempt_period_mu(self.core.seconds_to_mu(10e-6))
        self.entangler.set_gate_mu(self.core.seconds_to_mu(1e-6), self.core.seconds_to_mu(4e-6))
        self.entangler.set_output_states(0, 0)
        self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(4e-6))

        t0 = now_mu()
        for _ in range(int(self.repetitions)):
            self.entangler.clear()
            self.entangler.start()
        t1 = now_mu()

        print(
            "repetitions",
            int(self.repetitions),
            "average_mu_per_run",
            (t1 - t0) // int(self.repetitions),
        )

