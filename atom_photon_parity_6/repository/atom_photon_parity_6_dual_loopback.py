"""Dual-output loopback test for atom_photon_parity_6.

Wire both loopbacks before running:

* DIO channel 4 / entangler_output0 -> DIO channel 0 / entangler_input0
* DIO channel 5 / entangler_output1 -> DIO channel 1 / entangler_input1

The ``case`` argument chooses which fake photon output is pulsed inside the SPCM
gate. This lets one fixed cable setup test SPCM0-only, SPCM1-only, both-click,
and no-click behavior.
"""

from artiq.experiment import *


class AtomPhotonParity6DualLoopback(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_argument(
            "case",
            EnumerationValue(["spcm0", "spcm1", "both", "none"], default="spcm0"),
        )
        self.setattr_argument("photon0_start_us", NumberValue(default=2.0, min=0.1))
        self.setattr_argument("photon1_start_us", NumberValue(default=3.0, min=0.1))
        self.setattr_argument("photon_width_us", NumberValue(default=0.5, min=0.05))
        self.setattr_argument("gate_start_us", NumberValue(default=1.0, min=0.1))
        self.setattr_argument("gate_stop_us", NumberValue(default=8.0, min=0.2))
        self.setattr_argument("branch_offset_us", NumberValue(default=3.0, min=0.1))
        self.setattr_argument("branch_width_us", NumberValue(default=1.0, min=0.1))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.clear()
        self.entangler.configure(1)

        photon0_start_mu = self.core.seconds_to_mu(self.photon0_start_us * 1e-6)
        photon1_start_mu = self.core.seconds_to_mu(self.photon1_start_us * 1e-6)
        photon_width_mu = self.core.seconds_to_mu(self.photon_width_us * 1e-6)
        gate_start_mu = self.core.seconds_to_mu(self.gate_start_us * 1e-6)
        gate_stop_mu = self.core.seconds_to_mu(self.gate_stop_us * 1e-6)
        branch_start_mu = self.core.seconds_to_mu(self.branch_offset_us * 1e-6)
        branch_stop_mu = branch_start_mu + self.core.seconds_to_mu(self.branch_width_us * 1e-6)

        self.entangler.set_run_length_mu(self.core.seconds_to_mu(12e-6))
        self.entangler.set_num_attempts(1)
        self.entangler.set_attempt_period_mu(self.core.seconds_to_mu(10e-6))
        self.entangler.set_gate_mu(gate_start_mu, gate_stop_mu)
        self.entangler.set_output_states(0b0000, 0b1111)
        self.entangler.set_branch_done_delay_mu(self.core.seconds_to_mu(5e-6))

        for output in range(4):
            self.entangler.set_attempt_window_mu(output, 0, 0)
            self.entangler.set_branch_window_mu(0, output, 0, 0)
            self.entangler.set_branch_window_mu(1, output, 0, 0)

        # output0 is looped to SPCM0/input0; output1 is looped to SPCM1/input1.
        if self.case == "spcm0" or self.case == "both":
            self.entangler.set_attempt_window_mu(
                0,
                photon0_start_mu,
                photon0_start_mu + photon_width_mu,
            )
        if self.case == "spcm1" or self.case == "both":
            self.entangler.set_attempt_window_mu(
                1,
                photon1_start_mu,
                photon1_start_mu + photon_width_mu,
            )

        # Use output2 and output3 as scope-friendly branch markers. They are not
        # looped back into the SPCM inputs.
        self.entangler.set_branch_window_mu(0, 2, branch_start_mu, branch_stop_mu)
        self.entangler.set_branch_window_mu(1, 3, branch_start_mu, branch_stop_mu)

        _, status = self.entangler.start()

        self.core.break_realtime()

        print(
            "dual_loopback",
            self.case,
            "status",
            status,
            "outcome",
            self.entangler.get_outcome(),
            "click_ts",
            self.entangler.get_click_timestamp_mu(),
            "spcm0_ts",
            self.entangler.get_spcm_timestamp_mu(0),
            "spcm1_ts",
            self.entangler.get_spcm_timestamp_mu(1),
            "attempt",
            self.entangler.get_attempt_index(),
        )
