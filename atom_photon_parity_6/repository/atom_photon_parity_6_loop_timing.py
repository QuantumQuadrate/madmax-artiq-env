"""Measure atom_photon_parity no-click attempt-loop timing on hardware.

Run this after flashing parity gateware. For a clean no-click measurement,
disconnect/cover the SPCM inputs or choose a quiet gate.
"""

from artiq.experiment import *


STATUS_SUCCESS = 1 << 2
STATUS_TIMEOUT = 1 << 3
STATUS_INVALID_CONFIG = 1 << 4


class AtomPhotonParity6LoopTiming(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument("repetitions", NumberValue(default=1000, min=1, step=1, ndecimals=0))
        self.setattr_argument("num_attempts", NumberValue(default=4, min=1, step=1, ndecimals=0))
        self.setattr_argument("attempt_period_ns", NumberValue(default=128.0, min=32.0, unit="ns"))
        self.setattr_argument("gate_start_ns", NumberValue(default=8.0, min=8.0, unit="ns"))
        self.setattr_argument("gate_width_ns", NumberValue(default=8.0, min=8.0, unit="ns"))
        self.setattr_argument("inter_run_delay_us", NumberValue(default=1.0, min=0.0, unit="us"))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.configure(1)

        gate_start_mu = self.core.seconds_to_mu(self.gate_start_ns * 1e-9)
        gate_stop_mu = gate_start_mu + self.core.seconds_to_mu(self.gate_width_ns * 1e-9)
        attempt_period_mu = self.core.seconds_to_mu(self.attempt_period_ns * 1e-9)
        inter_run_delay_mu = self.core.seconds_to_mu(self.inter_run_delay_us * 1e-6)

        run_length_mu = attempt_period_mu * int(self.num_attempts) + self.core.seconds_to_mu(1e-6)

        self.entangler.clear()
        self.entangler.set_run_length_mu(run_length_mu)
        self.entangler.set_num_attempts(int(self.num_attempts))
        self.entangler.set_attempt_period_mu(attempt_period_mu)
        self.entangler.set_gate_mu(gate_start_mu, gate_stop_mu)
        self.entangler.set_output_states(0, 0)
        self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(1e-6))

        total_mu = 0
        min_mu = 0x7FFFFFFF
        max_mu = 0
        success_count = 0
        timeout_count = 0
        invalid_count = 0

        for _ in range(int(self.repetitions)):
            self.entangler.clear()
            t_start = now_mu()
            t_done, status = self.entangler.start()
            self.core.break_realtime()
            dt_mu = int(t_done - t_start)

            total_mu += dt_mu
            if dt_mu < min_mu:
                min_mu = dt_mu
            if dt_mu > max_mu:
                max_mu = dt_mu

            if status & STATUS_SUCCESS:
                success_count += 1
            if status & STATUS_TIMEOUT:
                timeout_count += 1
            if status & STATUS_INVALID_CONFIG:
                invalid_count += 1

            delay_mu(inter_run_delay_mu)

        print("repetitions", int(self.repetitions))
        print("num_attempts", int(self.num_attempts))
        print("attempt_period_mu", attempt_period_mu)
        print("gate_start_mu", gate_start_mu)
        print("gate_stop_mu", gate_stop_mu)
        print("average_loop_mu", total_mu // int(self.repetitions))
        print("min_loop_mu", min_mu)
        print("max_loop_mu", max_mu)
        print("success_count", success_count)
        print("timeout_count", timeout_count)
        print("invalid_count", invalid_count)
