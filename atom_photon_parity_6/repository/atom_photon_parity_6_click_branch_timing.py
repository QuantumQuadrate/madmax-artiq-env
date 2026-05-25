"""Scope click-to-branch timing for the parity helper.

Wire helper output 0 to SPCM0/input 0. Scope output 0 and output 2.
Output 0 creates the fake photon click; output 2 is the microwave branch marker.
"""

from artiq.experiment import *


class AtomPhotonParity6ClickBranchTiming(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument("repetitions", NumberValue(default=100, min=1, step=1, ndecimals=0))
        self.setattr_argument("fake_click_delay_ns", NumberValue(default=900.0, min=64.0, unit="ns"))
        self.setattr_argument("fake_click_width_ns", NumberValue(default=32.0, min=8.0, unit="ns"))
        self.setattr_argument("gate_start_ns", NumberValue(default=820.0, min=8.0, unit="ns"))
        self.setattr_argument("gate_width_ns", NumberValue(default=200.0, min=8.0, unit="ns"))
        self.setattr_argument("branch_offset_ns", NumberValue(default=1000.0, min=8.0, unit="ns"))
        self.setattr_argument("branch_width_ns", NumberValue(default=200.0, min=8.0, unit="ns"))
        self.setattr_argument("inter_run_delay_us", NumberValue(default=100.0, min=1.0, unit="us"))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.configure(1)

        fake_start_mu = self.core.seconds_to_mu(self.fake_click_delay_ns * 1e-9)
        fake_stop_mu = fake_start_mu + self.core.seconds_to_mu(self.fake_click_width_ns * 1e-9)
        gate_start_mu = self.core.seconds_to_mu(self.gate_start_ns * 1e-9)
        gate_stop_mu = gate_start_mu + self.core.seconds_to_mu(self.gate_width_ns * 1e-9)
        branch_start_mu = self.core.seconds_to_mu(self.branch_offset_ns * 1e-9)
        branch_stop_mu = branch_start_mu + self.core.seconds_to_mu(self.branch_width_ns * 1e-9)
        inter_run_delay_mu = self.core.seconds_to_mu(self.inter_run_delay_us * 1e-6)

        self.entangler.clear()
        self.entangler.set_run_length_mu(self.core.seconds_to_mu(16e-6))
        self.entangler.set_num_attempts(1)
        self.entangler.set_attempt_period_mu(self.core.seconds_to_mu(4e-6))
        self.entangler.set_gate_mu(gate_start_mu, gate_stop_mu)
        self.entangler.set_output_states(0b0000, 0b1111)
        self.entangler.set_branch_done_delay_mu(branch_stop_mu + self.core.seconds_to_mu(1e-6))

        self.entangler.set_attempt_window_mu(0, fake_start_mu, fake_stop_mu)
        self.entangler.set_branch_window_mu(0, 2, branch_start_mu, branch_stop_mu)

        print("fake_click_start_mu", fake_start_mu)
        print("gate_start_mu", gate_start_mu)
        print("gate_stop_mu", gate_stop_mu)
        print("branch_offset_mu", branch_start_mu)
        print("branch_width_mu", branch_stop_mu - branch_start_mu)
        print("scope expected output2 rising near click_ts + branch_offset_mu")
        print("note current gateware branch timing is quantized to the 8 ns coarse clock")

        for _ in range(int(self.repetitions)):
            self.entangler.clear()
            _, status = self.entangler.start()
            self.core.break_realtime()
            print(
                "status",
                status,
                "outcome",
                self.entangler.get_outcome(),
                "click_ts",
                self.entangler.get_click_timestamp_mu(),
            )
            delay_mu(inter_run_delay_mu)
