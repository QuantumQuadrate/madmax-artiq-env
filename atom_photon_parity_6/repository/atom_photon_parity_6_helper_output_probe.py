"""Probe whether the helper drives output0 onto the physical DIO line."""

from artiq.experiment import *


class AtomPhotonParity6HelperOutputProbe(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_device("ttl0")

    @kernel
    def run(self):
        self.core.reset()
        self.ttl0.input()
        self.entangler.clear()
        self.entangler.configure(1)

        self.entangler.set_run_length_mu(self.core.seconds_to_mu(12e-6))
        self.entangler.set_num_attempts(1)
        self.entangler.set_attempt_period_mu(self.core.seconds_to_mu(10e-6))
        self.entangler.set_gate_mu(self.core.seconds_to_mu(1e-6), self.core.seconds_to_mu(8e-6))
        self.entangler.set_output_states(0b0000, 0b1111)
        self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(5e-6))

        for output in range(4):
            self.entangler.set_attempt_window_mu(output, 0, 0)
            self.entangler.set_branch_window_mu(0, output, 0, 0)
            self.entangler.set_branch_window_mu(1, output, 0, 0)

        self.entangler.set_attempt_window_mu(
            0,
            self.core.seconds_to_mu(2e-6),
            self.core.seconds_to_mu(4e-6),
        )

        self.core.break_realtime()
        with parallel:
            gate_end = self.ttl0.gate_rising(20 * us)
            with sequential:
                delay(1 * us)
                _, status = self.entangler.start()

        self.core.break_realtime()
        count = self.ttl0.count(gate_end)
        self.core.break_realtime()

        print("helper_output0_seen_by_ttl0_count", count)
        print("helper_status", status)
