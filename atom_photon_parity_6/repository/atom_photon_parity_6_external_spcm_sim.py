"""Test Kasli parity helper using normal DIO outputs as fake SPCM inputs.

Suggested wiring for a two-DIO-card test Kasli:

* DIO card 0 is owned by the atom_photon_parity helper.
  - helper input 0: physical SPCM0 input
  - helper input 1: physical SPCM1 input
  - helper outputs: branch/debug outputs for scope
* DIO card 1 remains a normal ARTIQ DIO card.
  - ``fake_spcm0_ttl`` drives a cable into helper input 0.
  - ``fake_spcm1_ttl`` drives a cable into helper input 1.

Default node-1-style device DB names use ``ttl12`` and ``ttl13`` as the normal
DIO-card-1 fake SPCM pulse sources. Adjust those names if the generated test
device database assigns different TTL names.
"""

from artiq.experiment import *


class AtomPhotonParity6ExternalSPCMSim(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        self.setattr_device("ttl12")
        self.setattr_device("ttl13")

        self.setattr_argument(
            "case",
            EnumerationValue(["spcm0", "spcm1", "both", "none"], default="spcm0"),
        )
        self.setattr_argument("fake_spcm_delay_us", NumberValue(default=3.0, min=0.1))
        self.setattr_argument("fake_spcm_width_us", NumberValue(default=0.5, min=0.05))
        self.setattr_argument("gate_start_us", NumberValue(default=1.0, min=0.1))
        self.setattr_argument("gate_stop_us", NumberValue(default=8.0, min=0.2))
        self.setattr_argument("attempt_period_us", NumberValue(default=20.0, min=2.0))
        self.setattr_argument("branch_offset_us", NumberValue(default=2.0, min=0.1))
        self.setattr_argument("branch_width_us", NumberValue(default=1.0, min=0.1))
        self.setattr_argument("branch_done_delay_us", NumberValue(default=8.0, min=0.1))

    @kernel
    def run(self):
        self.core.reset()
        self.ttl12.output()
        self.ttl13.output()
        self.ttl12.off()
        self.ttl13.off()

        self.entangler.clear()
        self.entangler.configure(1)

        gate_start_mu = self.core.seconds_to_mu(self.gate_start_us * 1e-6)
        gate_stop_mu = self.core.seconds_to_mu(self.gate_stop_us * 1e-6)
        attempt_period_mu = self.core.seconds_to_mu(self.attempt_period_us * 1e-6)
        fake_delay_mu = self.core.seconds_to_mu(self.fake_spcm_delay_us * 1e-6)
        fake_width_mu = self.core.seconds_to_mu(self.fake_spcm_width_us * 1e-6)
        branch_start_mu = self.core.seconds_to_mu(self.branch_offset_us * 1e-6)
        branch_stop_mu = branch_start_mu + self.core.seconds_to_mu(self.branch_width_us * 1e-6)

        self.entangler.set_run_length_mu(self.core.seconds_to_mu(100e-6))
        self.entangler.set_num_attempts(1)
        self.entangler.set_attempt_period_mu(attempt_period_mu)
        self.entangler.set_gate_mu(gate_start_mu, gate_stop_mu)
        self.entangler.set_output_states(0b0000, 0b1111)
        self.entangler.set_branch_done_delay_mu(
            self.core.seconds_to_mu(self.branch_done_delay_us * 1e-6)
        )

        # Scope-friendly branch markers:
        # output 1 pulses for SPCM0_ONLY, output 2 pulses for SPCM1_ONLY.
        self.entangler.set_branch_window_mu(0, 1, branch_start_mu, branch_stop_mu)
        self.entangler.set_branch_window_mu(1, 2, branch_start_mu, branch_stop_mu)

        # Pre-schedule fake SPCM pulses in the future, then start the helper
        # before the fake photon time. This keeps Python out of the hot path.
        t_start = now_mu() + self.core.seconds_to_mu(20e-6)

        if self.case == "spcm0" or self.case == "both":
            at_mu(t_start + fake_delay_mu)
            self.ttl12.pulse_mu(fake_width_mu)
        if self.case == "spcm1" or self.case == "both":
            at_mu(t_start + fake_delay_mu)
            self.ttl13.pulse_mu(fake_width_mu)

        at_mu(t_start)
        _, status = self.entangler.start()
        self.core.break_realtime()

        print(
            "external_spcm_sim",
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
