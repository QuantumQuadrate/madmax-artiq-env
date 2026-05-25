"""Repeated SPCM0 loopback stress test.

Wire ``entangler_output0`` to ``entangler_input0``. This repeatedly exercises
the successful single-click path and counts success, timeout, and outcome words.
"""

from artiq.experiment import *


class AtomPhotonParity6Stress(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument("repetitions", NumberValue(default=1000, min=1, step=1, ndecimals=0))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.configure(1)

        successes = 0
        timeouts = 0
        spcm0 = 0
        other = 0

        for _ in range(int(self.repetitions)):
            self.entangler.clear()
            self.entangler.set_run_length_mu(self.core.seconds_to_mu(80e-6))
            self.entangler.set_num_attempts(1)
            self.entangler.set_attempt_period_mu(self.core.seconds_to_mu(20e-6))
            self.entangler.set_gate_mu(self.core.seconds_to_mu(1e-6), self.core.seconds_to_mu(8e-6))
            self.entangler.set_output_states(0b0000, 0b1111)
            self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(8e-6))
            self.entangler.set_attempt_window_mu(0, self.core.seconds_to_mu(2e-6), self.core.seconds_to_mu(3e-6))
            self.entangler.set_branch_window_mu(0, 1, self.core.seconds_to_mu(2e-6), self.core.seconds_to_mu(3e-6))

            _, status = self.entangler.start()

            self.core.break_realtime()
            outcome = self.entangler.get_outcome()

            if status & 0b100:
                successes += 1
            if status & 0b1000:
                timeouts += 1
            if outcome == 1:
                spcm0 += 1
            else:
                other += 1

        print(
            "repetitions",
            int(self.repetitions),
            "successes",
            successes,
            "timeouts",
            timeouts,
            "spcm0",
            spcm0,
            "other",
            other,
        )

