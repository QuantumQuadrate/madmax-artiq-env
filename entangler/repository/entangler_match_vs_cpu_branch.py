"""
Entangler match vs CPU branch timing
====================================

This diagnostic compares two ways of reacting to a TTL edge:

1. ``cpu_branch``: a normal ARTIQ kernel opens a TTL gate, timestamps the edge,
   checks it with an ``if`` statement, and schedules a response pulse.
2. ``entangler_core``: the entangler core generates the same stimulus pulse,
   matches the configured input pattern in gateware, and reports success when the
   entangler cycle ends.

Important limitation
--------------------
The current entangler gateware does not dynamically schedule a new output at
``click_timestamp + offset`` after a pattern match. Entangler outputs are fixed
within the cycle. The optional entangler response marker in this experiment is
therefore a pre-scheduled marker, not a conditional response.

With only one known-good loopback, connect:

    CPU/entangler stimulus output -> stimulus input

For example, if ``ttl7 -> ttl2`` is the known-good jumper, leave the defaults
``cpu_stimulus_output_name=ttl7`` and ``stimulus_input_name=ttl2`` and set
``entangler_stimulus_output_index`` to the entangler output index that drives
the same physical output.

If you add a second jumper from the response output to a TTL input, set
``response_monitor_input_name`` to that input to physically timestamp the
response marker/pulse.
"""

from artiq.experiment import *
from artiq.coredevice.rtio import rtio_input_timestamped_data
from artiq.coredevice.rtio import rtio_output
import numpy as np

from entangler.config import settings


CPU_BRANCH = 0
ENTANGLER_CORE = 1
NO_TIMESTAMP = np.int64(-1)
ENTANGLER_TIMEOUT = 0x3FFF
NO_DONE_EVENT = -1


class EntanglerMatchVsCpuBranchTiming(EnvExperiment):
    """Compare CPU timestamp/if latency against entangler pattern matching."""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler0")

        self.setattr_argument(
            "variant",
            EnumerationValue(["both", "cpu_branch", "entangler_core"], default="both"),
            group="Benchmark",
        )
        self.setattr_argument(
            "repetitions",
            NumberValue(default=25, min=1, max=10000, step=1, ndecimals=0),
            group="Benchmark",
        )

        self.setattr_argument(
            "stimulus_input_name",
            StringValue(default="ttl2"),
            group="Devices",
        )
        self.setattr_argument(
            "dark_input_name",
            StringValue(default="ttl3"),
            group="Devices",
        )
        self.setattr_argument(
            "cpu_stimulus_output_name",
            StringValue(default="ttl7"),
            group="Devices",
        )
        self.setattr_argument(
            "cpu_response_output_name",
            StringValue(default="ttl4"),
            group="Devices",
        )
        self.setattr_argument(
            "response_monitor_input_name",
            StringValue(default=""),
            group="Devices",
        )

        self.setattr_argument(
            "entangler_input_index",
            NumberValue(default=0, min=0, max=15, step=1, ndecimals=0),
            group="Entangler",
        )
        self.setattr_argument(
            "entangler_channel_override",
            NumberValue(default=-1, min=-1, max=63, step=1, ndecimals=0),
            group="Entangler",
        )
        self.setattr_argument(
            "entangler_stimulus_output_index",
            NumberValue(default=3, min=0, max=15, step=1, ndecimals=0),
            group="Entangler",
        )
        self.setattr_argument(
            "enable_entangler_response_marker",
            BooleanValue(default=True),
            group="Entangler",
        )
        self.setattr_argument(
            "entangler_response_output_index",
            NumberValue(default=0, min=0, max=15, step=1, ndecimals=0),
            group="Entangler",
        )

        self.setattr_argument(
            "stimulus_offset_us",
            NumberValue(default=5.0, min=0.1, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "stimulus_pulse_ns",
            NumberValue(default=200.0, min=50.0, max=1e6, unit="ns", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "cpu_gate_width_us",
            NumberValue(default=15.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "response_delay_us",
            NumberValue(default=25.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "response_pulse_ns",
            NumberValue(default=200.0, min=50.0, max=1e6, unit="ns", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "entangler_cycle_length_us",
            NumberValue(default=40.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "entangler_input_gate_pre_us",
            NumberValue(default=2.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "entangler_input_gate_post_us",
            NumberValue(default=5.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "response_monitor_pre_us",
            NumberValue(default=1.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "response_monitor_width_us",
            NumberValue(default=6.0, min=0.1, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "min_schedule_margin_us",
            NumberValue(default=1.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "max_monitor_events",
            NumberValue(default=8, min=1, max=64, step=1, ndecimals=0),
            group="Timing",
        )
        self.setattr_argument(
            "entangler_rtio_wait_margin_us",
            NumberValue(default=1000.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )

    def prepare(self):
        self.repetitions_i = int(self.repetitions)
        self.variant_code = {
            "both": 0,
            "cpu_branch": 1,
            "entangler_core": 2,
        }[self.variant]

        self.num_outputs_i = int(settings.NUM_OUTPUT_CHANNELS)
        self.num_inputs_i = int(settings.NUM_ENTANGLER_INPUT_SIGNALS)
        self.entangler_input_index_i = int(self.entangler_input_index)
        self.entangler_channel_override_i = int(self.entangler_channel_override)
        self.entangler_stimulus_output_index_i = int(self.entangler_stimulus_output_index)
        self.entangler_response_output_index_i = int(self.entangler_response_output_index)
        self.entangler_channel_i = int(self.entangler0.channel)
        if self.entangler_channel_override_i >= 0:
            self.entangler_channel_i = self.entangler_channel_override_i

        self._validate_entangler_indices()

        self.stimulus_input = self.get_device(self.stimulus_input_name)
        self.cpu_stimulus_output = self.get_device(self.cpu_stimulus_output_name)
        self.cpu_response_output = self.get_device(self.cpu_response_output_name)

        self.have_dark_input = self.dark_input_name.strip() != ""
        if self.have_dark_input:
            self.dark_input = self.get_device(self.dark_input_name)
        else:
            self.dark_input = self.stimulus_input

        self.have_response_monitor = self.response_monitor_input_name.strip() != ""
        self.response_monitor_is_stimulus_input = False
        self.response_monitor_is_dark_input = False
        if self.have_response_monitor:
            self.response_monitor_input = self.get_device(self.response_monitor_input_name)
            self.response_monitor_is_stimulus_input = (
                self.response_monitor_input_name == self.stimulus_input_name
            )
            self.response_monitor_is_dark_input = (
                self.have_dark_input
                and self.response_monitor_input_name == self.dark_input_name
            )
        else:
            self.response_monitor_input = self.stimulus_input

        ref_period = self.core.ref_period
        self.stimulus_offset_mu = self._seconds_to_mu(self.stimulus_offset_us * us, ref_period)
        self.stimulus_pulse_mu = max(
            1, self._seconds_to_mu(self.stimulus_pulse_ns * ns, ref_period)
        )
        self.cpu_gate_width_mu = self._seconds_to_mu(self.cpu_gate_width_us * us, ref_period)
        self.response_delay_mu = self._seconds_to_mu(self.response_delay_us * us, ref_period)
        self.response_pulse_mu = max(
            1, self._seconds_to_mu(self.response_pulse_ns * ns, ref_period)
        )
        self.entangler_cycle_length_mu = self._seconds_to_mu(
            self.entangler_cycle_length_us * us, ref_period
        )
        self.entangler_input_gate_pre_mu = self._seconds_to_mu(
            self.entangler_input_gate_pre_us * us, ref_period
        )
        self.entangler_input_gate_post_mu = self._seconds_to_mu(
            self.entangler_input_gate_post_us * us, ref_period
        )
        self.response_monitor_pre_mu = self._seconds_to_mu(
            self.response_monitor_pre_us * us, ref_period
        )
        self.response_monitor_width_mu = self._seconds_to_mu(
            self.response_monitor_width_us * us, ref_period
        )
        self.min_schedule_margin_mu = self._seconds_to_mu(
            self.min_schedule_margin_us * us, ref_period
        )
        self.max_monitor_events_i = int(self.max_monitor_events)
        self.entangler_rtio_wait_margin_mu = self._seconds_to_mu(
            self.entangler_rtio_wait_margin_us * us, ref_period
        )

        self.entangler_input_gate_start_mu = max(
            8, self.stimulus_offset_mu - self.entangler_input_gate_pre_mu
        )
        self.entangler_input_gate_stop_mu = (
            self.stimulus_offset_mu
            + self.stimulus_pulse_mu
            + self.entangler_input_gate_post_mu
        )
        self.entangler_response_start_mu = self.stimulus_offset_mu + self.response_delay_mu
        self.entangler_response_stop_mu = (
            self.entangler_response_start_mu + self.response_pulse_mu
        )
        self.entangler_timeout_mu = self.entangler_cycle_length_mu + self._seconds_to_mu(
            10.0 * us, ref_period
        )

        self._validate_timing()

        self.cpu_samples = []
        self.entangler_samples = []

    @staticmethod
    def _seconds_to_mu(seconds, ref_period):
        return int(round(seconds / ref_period))

    def _validate_entangler_indices(self):
        if self.entangler_input_index_i >= self.num_inputs_i:
            raise ValueError(
                "entangler_input_index={} but gateware has {} entangler inputs".format(
                    self.entangler_input_index_i, self.num_inputs_i
                )
            )
        if self.entangler_stimulus_output_index_i >= self.num_outputs_i:
            raise ValueError(
                "entangler_stimulus_output_index={} but gateware has {} outputs".format(
                    self.entangler_stimulus_output_index_i, self.num_outputs_i
                )
            )
        if self.entangler_response_output_index_i >= self.num_outputs_i:
            raise ValueError(
                "entangler_response_output_index={} but gateware has {} outputs".format(
                    self.entangler_response_output_index_i, self.num_outputs_i
                )
            )
        if (
            self.enable_entangler_response_marker
            and self.entangler_response_output_index_i
            == self.entangler_stimulus_output_index_i
        ):
            raise ValueError(
                "The current entangler sequencer supports one pulse window per output; "
                "use different stimulus and response output indices."
            )

    def _validate_timing(self):
        if self.stimulus_offset_mu + self.stimulus_pulse_mu >= self.cpu_gate_width_mu:
            raise ValueError("CPU gate must stay open through the stimulus pulse")
        if self.entangler_input_gate_stop_mu >= self.entangler_cycle_length_mu:
            raise ValueError("Entangler input gate must end before the cycle ends")
        if self.enable_entangler_response_marker:
            if self.entangler_response_stop_mu >= self.entangler_cycle_length_mu:
                raise ValueError("Entangler response marker must end before the cycle ends")
            if self.entangler_response_start_mu <= self.stimulus_offset_mu:
                raise ValueError("Entangler response marker should be after the stimulus")

    @rpc
    def _record_cpu_sample(
        self,
        click_mu: TInt64,
        dark_click_mu: TInt64,
        decision_cursor_mu: TInt64,
        decision_wall_mu: TInt64,
        response_target_mu: TInt64,
        schedule_done_cursor_mu: TInt64,
        schedule_done_wall_mu: TInt64,
        monitor_mu: TInt64,
        condition_met: TInt32,
        missed_response: TInt32,
    ):
        self.cpu_samples.append(
            {
                "click_mu": int(click_mu),
                "dark_click_mu": int(dark_click_mu),
                "decision_cursor_mu": int(decision_cursor_mu),
                "decision_wall_mu": int(decision_wall_mu),
                "response_target_mu": int(response_target_mu),
                "schedule_done_cursor_mu": int(schedule_done_cursor_mu),
                "schedule_done_wall_mu": int(schedule_done_wall_mu),
                "monitor_mu": int(monitor_mu),
                "condition_met": int(condition_met),
                "missed_response": int(missed_response),
            }
        )

    @rpc
    def _record_entangler_sample(
        self,
        ttl_click_mu: TInt64,
        dark_click_mu: TInt64,
        entangler_input_ts_mu: TInt32,
        run_end_mu: TInt64,
        reason: TInt32,
        status: TInt32,
        ncycles: TInt32,
        wall_after_run_mu: TInt64,
        response_target_mu: TInt64,
        monitor_mu: TInt64,
    ):
        self.entangler_samples.append(
            {
                "ttl_click_mu": int(ttl_click_mu),
                "dark_click_mu": int(dark_click_mu),
                "entangler_input_ts_mu": int(entangler_input_ts_mu),
                "run_end_mu": int(run_end_mu),
                "reason": int(reason),
                "status": int(status),
                "ncycles": int(ncycles),
                "wall_after_run_mu": int(wall_after_run_mu),
                "response_target_mu": int(response_target_mu),
                "monitor_mu": int(monitor_mu),
            }
        )

    @kernel
    def _setup_cpu_io(self):
        self.stimulus_input.input()
        if self.have_dark_input:
            self.dark_input.input()
        if self.have_response_monitor:
            self.response_monitor_input.input()

        self.cpu_stimulus_output.output()
        self.cpu_response_output.output()
        self.cpu_stimulus_output.off()
        self.cpu_response_output.off()
        self.core.break_realtime()

    @kernel
    def _setup_entangler_io(self):
        self.stimulus_input.input()
        if self.have_dark_input:
            self.dark_input.input()
        if self.have_response_monitor:
            self.response_monitor_input.input()

        self.cpu_stimulus_output.output()
        self.cpu_response_output.output()
        self.cpu_stimulus_output.off()
        self.cpu_response_output.off()
        self.core.break_realtime()

    @kernel
    def _read_first_timestamp_at_or_after(
        self, ttl, deadline_mu: TInt64, threshold_mu: TInt64
    ) -> TInt64:
        found = NO_TIMESTAMP
        for _ in range(self.max_monitor_events_i):
            t_mu = ttl.timestamp_mu(deadline_mu)
            if t_mu < 0:
                break
            if found < 0 and t_mu >= threshold_mu:
                found = t_mu
        return found

    @kernel
    def run_cpu_branch_kernel(self):
        self.core.reset()
        self._setup_cpu_io()

        for _ in range(self.repetitions_i):
            self.core.break_realtime()
            t_start_mu = now_mu()

            if self.have_dark_input:
                with parallel:
                    t_signal_end_mu = self.stimulus_input.gate_rising_mu(
                        np.int64(self.cpu_gate_width_mu)
                    )
                    t_dark_end_mu = self.dark_input.gate_rising_mu(
                        np.int64(self.cpu_gate_width_mu)
                    )
                    at_mu(t_start_mu + self.stimulus_offset_mu)
                    self.cpu_stimulus_output.pulse_mu(np.int64(self.stimulus_pulse_mu))
            else:
                with parallel:
                    t_signal_end_mu = self.stimulus_input.gate_rising_mu(
                        np.int64(self.cpu_gate_width_mu)
                    )
                    at_mu(t_start_mu + self.stimulus_offset_mu)
                    self.cpu_stimulus_output.pulse_mu(np.int64(self.stimulus_pulse_mu))
                t_dark_end_mu = NO_TIMESTAMP

            click_mu = self.stimulus_input.timestamp_mu(t_signal_end_mu)
            dark_click_mu = NO_TIMESTAMP
            if self.have_dark_input:
                dark_click_mu = self.dark_input.timestamp_mu(t_dark_end_mu)

            decision_cursor_mu = now_mu()
            decision_wall_mu = self.core.get_rtio_counter_mu()
            response_target_mu = NO_TIMESTAMP
            schedule_done_cursor_mu = decision_cursor_mu
            schedule_done_wall_mu = decision_wall_mu
            monitor_mu = NO_TIMESTAMP
            condition_met = 0
            missed_response = 0

            if click_mu > 0 and dark_click_mu < 0:
                condition_met = 1
                response_target_mu = click_mu + self.response_delay_mu

                if response_target_mu - decision_wall_mu <= self.min_schedule_margin_mu:
                    missed_response = 1
                else:
                    if self.have_response_monitor:
                        monitor_start_mu = response_target_mu - self.response_monitor_pre_mu
                        if monitor_start_mu < decision_cursor_mu:
                            monitor_start_mu = decision_cursor_mu
                        at_mu(monitor_start_mu)
                        with parallel:
                            t_monitor_end_mu = self.response_monitor_input.gate_rising_mu(
                                np.int64(self.response_monitor_width_mu)
                            )
                            at_mu(response_target_mu)
                            self.cpu_response_output.pulse_mu(
                                np.int64(self.response_pulse_mu)
                            )
                        monitor_mu = self._read_first_timestamp_at_or_after(
                            self.response_monitor_input,
                            t_monitor_end_mu,
                            response_target_mu - self.response_monitor_pre_mu,
                        )
                    else:
                        at_mu(response_target_mu)
                        self.cpu_response_output.pulse_mu(np.int64(self.response_pulse_mu))

                    schedule_done_cursor_mu = now_mu()
                    schedule_done_wall_mu = self.core.get_rtio_counter_mu()

            self._record_cpu_sample(
                click_mu,
                dark_click_mu,
                decision_cursor_mu,
                decision_wall_mu,
                response_target_mu,
                schedule_done_cursor_mu,
                schedule_done_wall_mu,
                monitor_mu,
                condition_met,
                missed_response,
            )

    @kernel
    def _entangler_write(self, addr: TInt32, value: TInt32):
        rtio_output((self.entangler_channel_i << 8) | addr, value)
        delay_mu(self.entangler0.ref_period_mu)

    @kernel
    def _entangler_set_config(self, enable: TBool, standalone: TBool):
        data = 0
        if enable:
            data |= 1
        if self.entangler0.is_master:
            data |= 1 << 1
        if standalone:
            data |= 1 << 2
        self._entangler_write(self.entangler0._ADDRESS_WRITE.CONFIG, data)

    @kernel
    def _entangler_set_timing_mu(
        self, channel: TInt32, t_start_mu: TInt32, t_stop_mu: TInt32
    ):
        if channel < self.num_outputs_i:
            t_start_mu = t_start_mu >> 3
            t_stop_mu = t_stop_mu >> 3

        t_start_mu += 1
        t_stop_mu += 1
        t_start_mu &= self.entangler0._SEQUENCER_TIME_MASK
        t_stop_mu &= self.entangler0._SEQUENCER_TIME_MASK

        self._entangler_write(
            self.entangler0._ADDRESS_WRITE.TIMING + channel,
            np.int32((t_stop_mu << 16) | t_start_mu),
        )

    @kernel
    def _entangler_set_cycle_length_mu(self, t_cycle_mu: TInt32):
        self._entangler_write(
            self.entangler0._ADDRESS_WRITE.TCYCLE,
            np.int32(t_cycle_mu >> 3),
        )

    @kernel
    def _entangler_set_patterns(self):
        pattern = np.int32(1 << self.entangler_input_index_i)
        data = pattern & self.entangler0._PATTERN_LENGTH_MASK
        data |= 1 << (
            self.entangler0._NUM_ALLOWED_PATTERNS * self.entangler0._PATTERN_WIDTH
        )
        self._entangler_write(self.entangler0._ADDRESS_WRITE.PATTERNS, np.int32(data))

    @kernel
    def _configure_entangler_core(self):
        self._entangler_set_config(False, True)

        disabled_start_mu = self.entangler_cycle_length_mu + 8
        disabled_stop_mu = self.entangler_cycle_length_mu + 16

        for channel in range(self.num_outputs_i):
            self._entangler_set_timing_mu(
                channel, np.int32(disabled_start_mu), np.int32(disabled_stop_mu)
            )

        self._entangler_set_timing_mu(
            self.entangler_stimulus_output_index_i,
            np.int32(self.stimulus_offset_mu),
            np.int32(self.stimulus_offset_mu + self.stimulus_pulse_mu),
        )

        if self.enable_entangler_response_marker:
            self._entangler_set_timing_mu(
                self.entangler_response_output_index_i,
                np.int32(self.entangler_response_start_mu),
                np.int32(self.entangler_response_stop_mu),
            )

        for input_index in range(self.num_inputs_i):
            self._entangler_set_timing_mu(
                self.num_outputs_i + input_index, np.int32(0), np.int32(0)
            )

        self._entangler_set_timing_mu(
            self.num_outputs_i + self.entangler_input_index_i,
            np.int32(self.entangler_input_gate_start_mu),
            np.int32(self.entangler_input_gate_stop_mu),
        )

        self._entangler_set_cycle_length_mu(np.int32(self.entangler_cycle_length_mu))
        self._entangler_set_patterns()
        self._entangler_set_config(True, True)
        self.core.break_realtime()

    @kernel
    def _run_entangler_core_bounded(self) -> TTuple([TInt64, TInt32]):
        duration_coarse_mu = self.entangler_timeout_mu >> 3
        self._entangler_write(
            self.entangler0._ADDRESS_WRITE.RUN,
            np.int32(duration_coarse_mu),
        )
        deadline_mu = now_mu() + self.entangler_timeout_mu + self.entangler_rtio_wait_margin_mu
        return rtio_input_timestamped_data(np.int64(deadline_mu), self.entangler_channel_i)

    @kernel
    def run_entangler_core_kernel(self):
        self.core.reset()
        self._setup_entangler_io()
        self._configure_entangler_core()

        for _ in range(self.repetitions_i):
            self.core.break_realtime()

            if self.have_dark_input:
                if self.have_response_monitor and not (
                    self.response_monitor_is_stimulus_input
                    or self.response_monitor_is_dark_input
                ):
                    with parallel:
                        t_signal_end_mu = self.stimulus_input.gate_rising_mu(
                            np.int64(self.entangler_timeout_mu)
                        )
                        t_dark_end_mu = self.dark_input.gate_rising_mu(
                            np.int64(self.entangler_timeout_mu)
                        )
                        t_monitor_end_mu = self.response_monitor_input.gate_rising_mu(
                            np.int64(self.entangler_timeout_mu)
                        )
                        run_end_mu, reason = self._run_entangler_core_bounded()
                else:
                    with parallel:
                        t_signal_end_mu = self.stimulus_input.gate_rising_mu(
                            np.int64(self.entangler_timeout_mu)
                        )
                        t_dark_end_mu = self.dark_input.gate_rising_mu(
                            np.int64(self.entangler_timeout_mu)
                        )
                        run_end_mu, reason = self._run_entangler_core_bounded()
                    t_monitor_end_mu = NO_TIMESTAMP
            else:
                if self.have_response_monitor and not self.response_monitor_is_stimulus_input:
                    with parallel:
                        t_signal_end_mu = self.stimulus_input.gate_rising_mu(
                            np.int64(self.entangler_timeout_mu)
                        )
                        t_monitor_end_mu = self.response_monitor_input.gate_rising_mu(
                            np.int64(self.entangler_timeout_mu)
                        )
                        run_end_mu, reason = self._run_entangler_core_bounded()
                else:
                    with parallel:
                        t_signal_end_mu = self.stimulus_input.gate_rising_mu(
                            np.int64(self.entangler_timeout_mu)
                        )
                        run_end_mu, reason = self._run_entangler_core_bounded()
                    t_monitor_end_mu = NO_TIMESTAMP
                t_dark_end_mu = NO_TIMESTAMP

            wall_after_run_mu = self.core.get_rtio_counter_mu()
            self.core.break_realtime()

            ttl_click_mu = self.stimulus_input.timestamp_mu(t_signal_end_mu)
            dark_click_mu = NO_TIMESTAMP
            if self.have_dark_input:
                dark_click_mu = self.dark_input.timestamp_mu(t_dark_end_mu)

            entangler_input_ts_mu = NO_DONE_EVENT
            status = NO_DONE_EVENT
            ncycles = NO_DONE_EVENT
            if run_end_mu >= 0:
                entangler_input_ts_mu = self.entangler0.get_timestamp_mu(
                    self.entangler_input_index_i
                )
                status = self.entangler0.get_status()
                ncycles = self.entangler0.get_ncycles()

            response_target_mu = NO_TIMESTAMP
            monitor_mu = NO_TIMESTAMP
            if ttl_click_mu > 0 and entangler_input_ts_mu > 0:
                response_target_mu = (
                    ttl_click_mu
                    - entangler_input_ts_mu
                    + self.entangler_response_start_mu
                )

            if run_end_mu >= 0 and self.have_response_monitor and response_target_mu > 0:
                monitor_threshold_mu = response_target_mu - self.response_monitor_pre_mu
                if self.response_monitor_is_stimulus_input:
                    monitor_mu = self._read_first_timestamp_at_or_after(
                        self.stimulus_input, t_signal_end_mu, monitor_threshold_mu
                    )
                elif self.response_monitor_is_dark_input:
                    if dark_click_mu >= monitor_threshold_mu:
                        monitor_mu = dark_click_mu
                    else:
                        monitor_mu = self._read_first_timestamp_at_or_after(
                            self.dark_input, t_dark_end_mu, monitor_threshold_mu
                        )
                else:
                    monitor_mu = self._read_first_timestamp_at_or_after(
                        self.response_monitor_input,
                        t_monitor_end_mu,
                        monitor_threshold_mu,
                    )

            self._record_entangler_sample(
                ttl_click_mu,
                dark_click_mu,
                entangler_input_ts_mu,
                run_end_mu,
                reason,
                status,
                ncycles,
                wall_after_run_mu,
                response_target_mu,
                monitor_mu,
            )

        self.core.break_realtime()
        self._entangler_set_config(False, True)
        self.core.break_realtime()

    def run(self):
        print("=== Entangler Match vs CPU Branch Timing ===")
        print("variant:", self.variant)
        print("stimulus:", self.cpu_stimulus_output_name, "->", self.stimulus_input_name)
        print("dark input:", self.dark_input_name if self.have_dark_input else "(none)")
        print("cpu response output:", self.cpu_response_output_name)
        print(
            "entangler stimulus output index:",
            self.entangler_stimulus_output_index_i,
        )
        print("entangler input index:", self.entangler_input_index_i)
        print("entangler RTIO channel:", self.entangler_channel_i)
        print(
            "entangler response marker:",
            "enabled" if self.enable_entangler_response_marker else "disabled",
        )
        if self.have_response_monitor:
            print("response monitor:", self.response_monitor_input_name)
        else:
            print("response monitor: (none)")

        if self.variant_code in (0, 1):
            self.run_cpu_branch_kernel()
        if self.variant_code in (0, 2):
            self.run_entangler_core_kernel()

        self._publish_results()

    def _publish_results(self):
        self._publish_cpu_results()
        self._publish_entangler_results()

    def _publish_cpu_results(self):
        prefix = "match_vs_cpu/cpu_branch"
        if len(self.cpu_samples) == 0:
            print("cpu_branch: no samples")
            return

        click = self._array("click_mu", self.cpu_samples)
        dark = self._array("dark_click_mu", self.cpu_samples)
        decision_wall = self._array("decision_wall_mu", self.cpu_samples)
        response_target = self._array("response_target_mu", self.cpu_samples)
        schedule_done_wall = self._array("schedule_done_wall_mu", self.cpu_samples)
        monitor = self._array("monitor_mu", self.cpu_samples)
        condition = self._array("condition_met", self.cpu_samples)
        missed = self._array("missed_response", self.cpu_samples)

        click_to_decision = self._delta_or_minus_one(decision_wall, click)
        click_to_response_target = self._delta_or_minus_one(response_target, click)
        decision_to_response_margin = self._delta_or_minus_one(
            response_target, decision_wall
        )
        click_to_schedule_done_wall = self._delta_or_minus_one(schedule_done_wall, click)
        monitor_after_click = self._delta_or_minus_one(monitor, click)

        self.set_dataset(f"{prefix}/click_mu", click, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/dark_click_mu", dark, broadcast=True, archive=True)
        self.set_dataset(
            f"{prefix}/click_to_decision_wall_mu",
            click_to_decision,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/click_to_response_target_mu",
            click_to_response_target,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/decision_to_response_margin_mu",
            decision_to_response_margin,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/click_to_schedule_done_wall_mu",
            click_to_schedule_done_wall,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/monitor_after_click_mu",
            monitor_after_click,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(f"{prefix}/condition_met", condition, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/missed_response", missed, broadcast=True, archive=True)

        print("")
        print("=== CPU branch summary (mu) ===")
        print("samples:", len(self.cpu_samples))
        print("condition met:", int(np.sum(condition)))
        print("missed response deadline:", int(np.sum(missed)))
        print(
            "click -> decision wall mean/min:",
            self._mean_or_minus_one(click_to_decision),
            "/",
            self._min_or_minus_one(click_to_decision),
        )
        print(
            "decision -> response target margin mean/min:",
            self._mean_or_minus_one(decision_to_response_margin),
            "/",
            self._min_or_minus_one(decision_to_response_margin),
        )
        if np.any(monitor_after_click >= 0):
            print(
                "physical monitor click -> response mean/min:",
                self._mean_or_minus_one(monitor_after_click),
                "/",
                self._min_or_minus_one(monitor_after_click),
            )

    def _publish_entangler_results(self):
        prefix = "match_vs_cpu/entangler_core"
        if len(self.entangler_samples) == 0:
            print("entangler_core: no samples")
            return

        ttl_click = self._array("ttl_click_mu", self.entangler_samples)
        dark = self._array("dark_click_mu", self.entangler_samples)
        input_ts = self._array("entangler_input_ts_mu", self.entangler_samples)
        run_end = self._array("run_end_mu", self.entangler_samples)
        reason = self._array("reason", self.entangler_samples)
        status = self._array("status", self.entangler_samples)
        ncycles = self._array("ncycles", self.entangler_samples)
        wall_after_run = self._array("wall_after_run_mu", self.entangler_samples)
        response_target = self._array("response_target_mu", self.entangler_samples)
        monitor = self._array("monitor_mu", self.entangler_samples)

        click_to_cycle_end = np.where(
            (ttl_click >= 0) & (input_ts > 0),
            self.entangler_cycle_length_mu - input_ts,
            -1,
        )
        click_to_run_end_timestamp = self._delta_or_minus_one(run_end, ttl_click)
        click_to_run_return_wall = self._delta_or_minus_one(wall_after_run, ttl_click)
        click_to_response_target = self._delta_or_minus_one(response_target, ttl_click)
        monitor_after_click = self._delta_or_minus_one(monitor, ttl_click)
        no_done = np.where(run_end < 0, 1, 0).astype(np.int64)
        success = np.where(
            (run_end >= 0) & (reason != ENTANGLER_TIMEOUT), 1, 0
        ).astype(np.int64)

        self.set_dataset(f"{prefix}/ttl_click_mu", ttl_click, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/dark_click_mu", dark, broadcast=True, archive=True)
        self.set_dataset(
            f"{prefix}/entangler_input_ts_mu", input_ts, broadcast=True, archive=True
        )
        self.set_dataset(f"{prefix}/run_end_mu", run_end, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/reason", reason, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/status", status, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/ncycles", ncycles, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/success", success, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/no_done_event", no_done, broadcast=True, archive=True)
        self.set_dataset(
            f"{prefix}/click_to_cycle_end_mu",
            click_to_cycle_end,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/click_to_run_end_timestamp_mu",
            click_to_run_end_timestamp,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/click_to_run_return_wall_mu",
            click_to_run_return_wall,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/click_to_response_marker_target_mu",
            click_to_response_target,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/monitor_after_click_mu",
            monitor_after_click,
            broadcast=True,
            archive=True,
        )

        print("")
        print("=== Entangler core summary (mu) ===")
        print("samples:", len(self.entangler_samples))
        print("successes:", int(np.sum(success)))
        print("timeouts:", int(np.sum((run_end >= 0) & (reason == ENTANGLER_TIMEOUT))))
        print("no done events:", int(np.sum(no_done)))
        print(
            "click -> cycle end mean/min:",
            self._mean_or_minus_one(click_to_cycle_end),
            "/",
            self._min_or_minus_one(click_to_cycle_end),
        )
        print(
            "click -> run return wall mean/min:",
            self._mean_or_minus_one(click_to_run_return_wall),
            "/",
            self._min_or_minus_one(click_to_run_return_wall),
        )
        print(
            "click -> pre-scheduled marker target mean/min:",
            self._mean_or_minus_one(click_to_response_target),
            "/",
            self._min_or_minus_one(click_to_response_target),
        )
        if np.any(monitor_after_click >= 0):
            print(
                "physical monitor click -> marker mean/min:",
                self._mean_or_minus_one(monitor_after_click),
                "/",
                self._min_or_minus_one(monitor_after_click),
            )

    @staticmethod
    def _array(key, samples):
        return np.array([sample[key] for sample in samples], dtype=np.int64)

    @staticmethod
    def _delta_or_minus_one(target, origin):
        return np.where((target >= 0) & (origin >= 0), target - origin, -1)

    @staticmethod
    def _valid_values(values):
        return values[values >= 0]

    def _mean_or_minus_one(self, values):
        valid = self._valid_values(values)
        if valid.size == 0:
            return -1
        return int(np.mean(valid))

    def _min_or_minus_one(self, values):
        valid = self._valid_values(values)
        if valid.size == 0:
            return -1
        return int(np.min(valid))
