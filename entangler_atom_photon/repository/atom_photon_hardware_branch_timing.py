"""Measure atom-photon hardware branch timing with ttl5 looped into ttl0.

Connections:
    ttl5 / dio0[5] -> ttl0 / dio0[0]
    scope CH1 on ttl5
    scope CH2 on ttl6 / dio0[6]

The entangler drives ttl5 as the excitation gate. The ttl5 rising edge loops
back as a fake SPCM0 click. Branch 0 then emits the MW/action pulse on ttl6.
"""

from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.experiment import kernel
from artiq.language.core import delay_mu
from artiq.language.core import parallel
from artiq.language.core import sequential
from artiq.language.units import us
import numpy as np


class AtomPhotonHardwareBranchTiming(EnvExperiment):
    """Run a deterministic SPCM0-only branch and emit action bit 2 on ttl6."""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler0")
        self.setattr_device("ttl0")
        self.setattr_device("ttl6")
        self.setattr_device("led0")
        self.setattr_argument(
            "repeats", NumberValue(5, min=1, max=100, step=1, ndecimals=0)
        )
        self.setattr_argument(
            "action_offset_mu",
            NumberValue(160, min=32, max=100000, step=8, ndecimals=0),
        )
        self.setattr_argument(
            "action_width_mu",
            NumberValue(80, min=16, max=100000, step=8, ndecimals=0),
        )

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        self.ttl0.input()
        self.entangler0.init()
        self.entangler0.clear()
        delay_mu(10000)

        for index in range(self.repeats):
            self.core.break_realtime()
            self.configure_spcm0_loopback_branch()
            with parallel:
                gate_end_mu = self.ttl0.gate_rising(2 * us)
                with sequential:
                    finished_at_mu, done_word = self.entangler0.run_mu()
            cpu_monitor_ts = self.ttl0.timestamp_mu(gate_end_mu)
            self.core.break_realtime()

            status = self.entangler0.get_status()
            self.core.break_realtime()
            outcome = self.entangler0.get_outcome()
            self.core.break_realtime()
            done_reason = self.entangler0.get_done_reason()
            self.core.break_realtime()
            attempts = self.entangler0.get_attempts_completed()
            self.core.break_realtime()
            spcm0_ts = self.entangler0.get_spcm0_timestamp_mu()
            self.core.break_realtime()
            spcm1_ts = self.entangler0.get_spcm1_timestamp_mu()
            self.core.break_realtime()
            chosen_ts = self.entangler0.get_chosen_timestamp_mu()
            action_offset_mu = np.int64(self.action_offset_mu)
            expected_action_ts = chosen_ts + action_offset_mu
            self.core.break_realtime()
            self.entangler0.set_config(0)

            print("hardware_branch index", index)
            print("hardware_branch finished_at_mu", finished_at_mu)
            print("hardware_branch done_word", done_word)
            print("hardware_branch cpu_monitor_ttl0_ts_mu", cpu_monitor_ts)
            print("hardware_branch status", status)
            print("hardware_branch outcome", outcome)
            print("hardware_branch done_reason", done_reason)
            print("hardware_branch attempts", attempts)
            print("hardware_branch spcm0_ts_mu", spcm0_ts)
            print("hardware_branch spcm1_ts_mu", spcm1_ts)
            print("hardware_branch chosen_ts_mu", chosen_ts)
            print("hardware_branch ttl6_expected_ts_mu", expected_action_ts)
            print("hardware_branch logical_click_to_ttl6_mu", action_offset_mu)

            self.core.break_realtime()
            self.led0.pulse_mu(1000)
            delay_mu(100000)

    @kernel
    def configure_spcm0_loopback_branch(self):
        self.entangler0.clear()

        # Attempt-level outputs:
        # output bit 0 / ttl4: FORT gate, 16 -> 192 mu
        # output bit 1 / ttl5: excitation fake click, 64 -> 96 mu.
        # The concurrent ttl0.gate_rising() in run() arms the input PHY for the
        # loopback edge; the entangler timestamp is around 132 mu.
        self.entangler0.write_register(0x02, 1)    # N_ATTEMPTS
        self.entangler0.write_register(0x03, 512)  # ATTEMPT_PERIOD_MU
        self.entangler0.write_register(0x04, 16)   # FORT_OFF_MU
        self.entangler0.write_register(0x05, 192)  # FORT_ON_MU
        self.entangler0.write_register(0x06, 64)   # EXCITATION_START_MU
        self.entangler0.write_register(0x07, 96)   # EXCITATION_STOP_MU
        self.entangler0.write_register(0x08, 32)   # PHOTON_GATE_START_MU
        self.entangler0.write_register(0x09, 160)  # PHOTON_GATE_STOP_MU

        # STOP_FAIL for neither and both.
        self.entangler0.write_register(0x0A, 0x11)  # BRANCH_POLICIES

        # Branch 0 action table entry 0:
        # offset = action_offset_mu relative to SPCM0 timestamp
        # duration = action_width_mu
        # mask/value bit 2 = ttl6
        action_offset_mu = np.int32(self.action_offset_mu)
        action_width_mu = np.int32(self.action_width_mu)
        self.entangler0.write_register(0x11, 1)  # BRANCH0_ACTION_COUNT
        self.entangler0.write_register(0x12, 0)  # BRANCH1_ACTION_COUNT
        self.entangler0.write_register(0x30, action_offset_mu)
        self.entangler0.write_register(0x31, action_width_mu)
        self.entangler0.write_register(0x32, 0x04)
        self.entangler0.write_register(0x33, 0x04)

        self.entangler0.set_config(1)
