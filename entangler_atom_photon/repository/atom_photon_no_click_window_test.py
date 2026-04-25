"""Check that a connected ttl5 -> ttl0 loopback can be excluded by the gate.

This keeps the physical loopback connected, but places the photon gate after the
ttl5 excitation pulse. Expected result: neither, no ttl6 branch action.
"""

from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.language.core import delay_mu


class AtomPhotonNoClickWindowTest(EnvExperiment):
    """The loopback edge is outside the photon gate, so no branch should fire."""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler0")
        self.setattr_device("ttl0")
        self.setattr_device("led0")

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        self.ttl0.input()
        self.entangler0.init()
        self.entangler0.clear()
        delay_mu(10000)

        self.configure_no_click_window()
        finished_at_mu, done_word = self.entangler0.run_mu()
        self.core.break_realtime()

        status = self.entangler0.get_status()
        outcome = self.entangler0.get_outcome()
        done_reason = self.entangler0.get_done_reason()
        attempts = self.entangler0.get_attempts_completed()
        spcm0_ts = self.entangler0.get_spcm0_timestamp_mu()
        spcm1_ts = self.entangler0.get_spcm1_timestamp_mu()
        chosen_ts = self.entangler0.get_chosen_timestamp_mu()
        self.entangler0.set_config(0)

        print("no_click_window finished_at_mu", finished_at_mu)
        print("no_click_window done_word", done_word)
        print("no_click_window status", status)
        print("no_click_window outcome", outcome)
        print("no_click_window done_reason", done_reason)
        print("no_click_window attempts", attempts)
        print("no_click_window spcm0_ts_mu", spcm0_ts)
        print("no_click_window spcm1_ts_mu", spcm1_ts)
        print("no_click_window chosen_ts_mu", chosen_ts)
        self.led0.pulse_mu(1000)

    @kernel
    def configure_no_click_window(self):
        self.entangler0.clear()

        self.entangler0.write_register(0x02, 1)    # N_ATTEMPTS
        self.entangler0.write_register(0x03, 512)  # ATTEMPT_PERIOD_MU
        self.entangler0.write_register(0x04, 16)   # FORT_OFF_MU
        self.entangler0.write_register(0x05, 192)  # FORT_ON_MU
        self.entangler0.write_register(0x06, 64)   # EXCITATION_START_MU
        self.entangler0.write_register(0x07, 96)   # EXCITATION_STOP_MU

        # Gate opens after the ttl5 loopback edge, so no SPCM should trigger.
        self.entangler0.write_register(0x08, 120)  # PHOTON_GATE_START_MU
        self.entangler0.write_register(0x09, 180)  # PHOTON_GATE_STOP_MU

        self.entangler0.write_register(0x0A, 0x11)  # BRANCH_POLICIES
        self.entangler0.write_register(0x11, 1)     # BRANCH0_ACTION_COUNT
        self.entangler0.write_register(0x12, 0)     # BRANCH1_ACTION_COUNT
        self.entangler0.write_register(0x30, 160)   # branch0 offset
        self.entangler0.write_register(0x31, 80)    # branch0 duration
        self.entangler0.write_register(0x32, 0x04)  # ttl6 mask
        self.entangler0.write_register(0x33, 0x04)  # ttl6 value

        self.entangler0.set_config(1)
