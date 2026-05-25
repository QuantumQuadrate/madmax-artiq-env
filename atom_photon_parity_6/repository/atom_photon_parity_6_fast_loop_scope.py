"""Hardware timing test for the parity-6 fast excitation loop.

This exercises only the gateware-owned loop section:

* output 0 can generate a fake SPCM0 click,
* output 1 can generate a fake SPCM1 click,
* output 2 marks the SPCM0-only branch, and
* output 3 marks the SPCM1-only branch.

Suggested four-cable setup:

* helper output 0 / ttl4 / DIO0[4] -> helper input 0 / ttl0 / DIO0[0]
* helper output 1 / ttl5 / DIO0[5] -> helper input 1 / ttl1 / DIO0[1]
Scope output 0/1 and output 2/3 directly. The current generated device DB does
not export ttl2/ttl3, so this experiment uses the scope as the timing monitor.
"""

from artiq.experiment import *


STATUS_SUCCESS = 1 << 2
STATUS_TIMEOUT = 1 << 3
STATUS_INVALID_CONFIG = 1 << 4
OUTCOME_NONE = 0
OUTCOME_SPCM0_ONLY = 1
OUTCOME_SPCM1_ONLY = 2
OUTCOME_BOTH = 3


class AtomPhotonParity6FastLoopScope(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")

        self.setattr_argument(
            "case",
            EnumerationValue(["spcm0", "spcm1", "both", "none"], default="spcm0"),
        )

        self.setattr_argument("repetitions", NumberValue(default=100, min=1, step=1, ndecimals=0))
        self.setattr_argument("num_attempts", NumberValue(default=4, min=1, step=1, ndecimals=0))
        self.setattr_argument("attempt_period_ns", NumberValue(default=128.0, min=32.0, unit="ns"))
        self.setattr_argument("fake_click_delay_ns", NumberValue(default=16.0, min=8.0, unit="ns"))
        self.setattr_argument("fake_click_width_ns", NumberValue(default=8.0, min=8.0, unit="ns"))
        self.setattr_argument("gate_start_ns", NumberValue(default=8.0, min=8.0, unit="ns"))
        self.setattr_argument("gate_width_ns", NumberValue(default=16.0, min=8.0, unit="ns"))
        self.setattr_argument("branch_offset_ns", NumberValue(default=96.0, min=8.0, unit="ns"))
        self.setattr_argument("branch_width_ns", NumberValue(default=32.0, min=8.0, unit="ns"))
        self.setattr_argument("inter_run_delay_us", NumberValue(default=100.0, min=1.0, unit="us"))

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.configure(1)

        attempt_period_mu = self.core.seconds_to_mu(self.attempt_period_ns * 1e-9)
        fake_start_mu = self.core.seconds_to_mu(self.fake_click_delay_ns * 1e-9)
        fake_stop_mu = fake_start_mu + self.core.seconds_to_mu(self.fake_click_width_ns * 1e-9)
        gate_start_mu = self.core.seconds_to_mu(self.gate_start_ns * 1e-9)
        gate_stop_mu = gate_start_mu + self.core.seconds_to_mu(self.gate_width_ns * 1e-9)
        branch_start_mu = self.core.seconds_to_mu(self.branch_offset_ns * 1e-9)
        branch_stop_mu = branch_start_mu + self.core.seconds_to_mu(self.branch_width_ns * 1e-9)
        inter_run_delay_mu = self.core.seconds_to_mu(self.inter_run_delay_us * 1e-6)

        # Keep this under the current 11-bit coarse counter limit:
        # 2047 coarse ticks * 8 ns = 16.376 us.
        branch_done_mu = branch_stop_mu + self.core.seconds_to_mu(64e-9)
        monitor_window_mu = attempt_period_mu * int(self.num_attempts) + branch_done_mu + self.core.seconds_to_mu(1e-6)
        run_length_mu = monitor_window_mu

        self.entangler.clear()
        self.entangler.set_run_length_mu(run_length_mu)
        self.entangler.set_num_attempts(int(self.num_attempts))
        self.entangler.set_attempt_period_mu(attempt_period_mu)
        self.entangler.set_gate_mu(gate_start_mu, gate_stop_mu)
        self.entangler.set_output_states(0b0000, 0b1111)
        self.entangler.set_branch_done_delay_mu(branch_done_mu)

        for output in range(4):
            self.entangler.set_attempt_window_mu(output, 0, 0)
            self.entangler.set_branch_window_mu(0, output, 0, 0)
            self.entangler.set_branch_window_mu(1, output, 0, 0)

        if self.case == "spcm0" or self.case == "both":
            self.entangler.set_attempt_window_mu(0, fake_start_mu, fake_stop_mu)
        if self.case == "spcm1" or self.case == "both":
            self.entangler.set_attempt_window_mu(1, fake_start_mu, fake_stop_mu)

        self.entangler.set_branch_window_mu(0, 2, branch_start_mu, branch_stop_mu)
        self.entangler.set_branch_window_mu(1, 3, branch_start_mu, branch_stop_mu)

        print("case", self.case)
        print("attempt_period_mu", attempt_period_mu)
        print("fake_click_window_mu", fake_start_mu, fake_stop_mu)
        print("gate_window_mu", gate_start_mu, gate_stop_mu)
        print("branch_window_mu", branch_start_mu, branch_stop_mu)
        print("branch_done_mu", branch_done_mu)
        print("monitor_window_mu", monitor_window_mu)
        print("expected no-click loop roughly num_attempts * attempt_period, plus a few coarse ticks")
        print("expected branch output starts at floor(click_ts / 8 ns) * 8 ns + branch_offset")

        total_loop_mu = 0
        min_loop_mu = 0x7FFFFFFF
        max_loop_mu = 0
        success_count = 0
        timeout_count = 0
        invalid_count = 0

        for _ in range(int(self.repetitions)):
            self.core.break_realtime()
            self.entangler.clear()

            t_start = now_mu()
            branch0_ts = -1
            branch1_ts = -1
            t_done, status = self.entangler.start_for_mu(monitor_window_mu + self.core.seconds_to_mu(10e-6))
            self.core.break_realtime()

            click_ts = self.entangler.get_click_timestamp_mu()
            outcome = self.entangler.get_outcome()
            spcm0_ts = self.entangler.get_spcm_timestamp_mu(0)
            spcm1_ts = self.entangler.get_spcm_timestamp_mu(1)
            loop_mu = -1
            if t_done >= 0:
                loop_mu = int(t_done - t_start)

            total_loop_mu += loop_mu
            if loop_mu < min_loop_mu:
                min_loop_mu = loop_mu
            if loop_mu > max_loop_mu:
                max_loop_mu = loop_mu
            if status & STATUS_SUCCESS:
                success_count += 1
            if status & STATUS_TIMEOUT:
                timeout_count += 1
            if status & STATUS_INVALID_CONFIG:
                invalid_count += 1

            print(
                "run",
                "status",
                status,
                "outcome",
                outcome,
                "loop_mu",
                loop_mu,
                "click_ts",
                click_ts,
                "spcm0_ts",
                spcm0_ts,
                "spcm1_ts",
                spcm1_ts,
                "branch0_abs_ts",
                branch0_ts,
                "branch1_abs_ts",
                branch1_ts,
            )

            delay_mu(inter_run_delay_mu)

        print("summary_repetitions", int(self.repetitions))
        print("summary_average_loop_mu", total_loop_mu // int(self.repetitions))
        print("summary_min_loop_mu", min_loop_mu)
        print("summary_max_loop_mu", max_loop_mu)
        print("summary_success_count", success_count)
        print("summary_timeout_count", timeout_count)
        print("summary_invalid_count", invalid_count)
