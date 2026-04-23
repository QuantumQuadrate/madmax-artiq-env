"""
CPU timestamp matching vs entangler-core pattern matching.

Default loopback wiring for the current one-DIO setup:

    ttl5 output -> ttl1 input    entangler output 1 -> input 1
    ttl4 output -> ttl3 input    entangler output 0 -> input 3

The CPU branch pulses the normal TTLOut devices, gates the normal TTLInOut
devices, and treats the shot as a match when every expected input clicked.

The entangler branch configures the gateware sequencer to pulse the same output
indices, gate the same input indices, and match the corresponding input pattern
in hardware. The experiment records both the normal TTL timestamps observed while
the entangler runs and the entangler-core input timestamps read back from the
gateware.
"""

from artiq.experiment import *
import numpy as np


NO_TIMESTAMP = -1
ENTANGLER_TIMEOUT = 0x3FFF


class EntanglerMatchVsCpuBranchTiming(EnvExperiment):
    """Compare CPU-side TTL timestamp matching with entangler-core matching."""

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
            "test_condition",
            EnumerationValue(
                [
                    "baseline",
                    "tight_entangler_cycle",
                    "fast_hardware_done",
                    "custom",
                ],
                default="baseline",
            ),
            group="Benchmark",
        )

        self.setattr_argument(
            "cpu_output_names",
            StringValue(default="ttl5,ttl4"),
            group="Devices",
        )
        self.setattr_argument(
            "input_names",
            StringValue(default="ttl1,ttl3"),
            group="Devices",
        )
        self.setattr_argument(
            "entangler_output_indices",
            StringValue(default="1,0"),
            group="Entangler",
        )
        self.setattr_argument(
            "entangler_input_indices",
            StringValue(default="1,3"),
            group="Entangler",
        )
        self.setattr_argument(
            "pattern_override",
            NumberValue(default=-1, min=-1, max=15, step=1, ndecimals=0),
            group="Entangler",
        )
        self.setattr_argument(
            "pattern_enable_shift",
            NumberValue(default=-1, min=-1, max=31, step=1, ndecimals=0),
            group="Entangler",
        )

        self.setattr_argument(
            "pulse_offset_us",
            NumberValue(default=2.0, min=0.1, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "pulse_width_us",
            NumberValue(default=2.0, min=0.01, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "cpu_gate_width_us",
            NumberValue(default=10.0, min=0.1, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "entangler_cycle_length_us",
            NumberValue(default=7.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "entangler_gate_pre_us",
            NumberValue(default=1.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "entangler_gate_post_us",
            NumberValue(default=2.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "entangler_run_margin_us",
            NumberValue(default=20.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "inter_trial_us",
            NumberValue(default=100.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )

    def prepare(self):
        self.variant_code = {
            "both": 0,
            "cpu_branch": 1,
            "entangler_core": 2,
        }[self.variant]
        self.repetitions_i = int(self.repetitions)

        self.cpu_output_name_list = self._split_names(self.cpu_output_names)
        self.input_name_list = self._split_names(self.input_names)
        self.entangler_output_index_list = self._split_ints(
            self.entangler_output_indices
        )
        self.entangler_input_index_list = self._split_ints(self.entangler_input_indices)

        self.num_pairs_i = len(self.input_name_list)
        if self.num_pairs_i < 1:
            raise ValueError("input_names must contain at least one TTL device name")
        if self.num_pairs_i > 4:
            raise ValueError("this diagnostic supports at most four loopback pairs")
        if len(self.cpu_output_name_list) != self.num_pairs_i:
            raise ValueError("cpu_output_names and input_names must have equal length")
        if len(self.entangler_output_index_list) != self.num_pairs_i:
            raise ValueError(
                "entangler_output_indices and input_names must have equal length"
            )
        if len(self.entangler_input_index_list) != self.num_pairs_i:
            raise ValueError(
                "entangler_input_indices and input_names must have equal length"
            )

        self.cpu_outputs = [self.get_device(name) for name in self.cpu_output_name_list]
        self.inputs = [self.get_device(name) for name in self.input_name_list]

        self.num_entangler_outputs_i = int(self.entangler0.num_outputs)
        self.num_entangler_inputs_i = int(self.entangler0.num_inputs)
        self._validate_entangler_indices()

        self.pattern_override_i = int(self.pattern_override)
        self.pattern_enable_shift_i = int(self.pattern_enable_shift)
        if self.pattern_enable_shift_i < 0:
            self.pattern_enable_shift_i = (
                self.entangler0._NUM_ALLOWED_PATTERNS * self.entangler0._PATTERN_WIDTH
            )
        self.expected_pattern_i = 0
        if self.pattern_override_i >= 0:
            self.expected_pattern_i = self.pattern_override_i
        else:
            for input_index in self.entangler_input_index_list:
                self.expected_pattern_i |= 1 << input_index

        self.effective_pulse_offset_us = float(self.pulse_offset_us)
        self.effective_pulse_width_us = float(self.pulse_width_us)
        self.effective_cpu_gate_width_us = float(self.cpu_gate_width_us)
        self.effective_entangler_cycle_length_us = float(self.entangler_cycle_length_us)
        self.effective_entangler_gate_pre_us = float(self.entangler_gate_pre_us)
        self.effective_entangler_gate_post_us = float(self.entangler_gate_post_us)

        if self.test_condition == "tight_entangler_cycle":
            self.effective_pulse_offset_us = 1.0
            self.effective_pulse_width_us = 0.2
            self.effective_cpu_gate_width_us = 10.0
            self.effective_entangler_cycle_length_us = 1.6
            self.effective_entangler_gate_pre_us = 0.2
            self.effective_entangler_gate_post_us = 0.1
        elif self.test_condition == "fast_hardware_done":
            self.effective_pulse_offset_us = 1.0
            self.effective_pulse_width_us = 0.2
            self.effective_cpu_gate_width_us = 10.0
            self.effective_entangler_cycle_length_us = 1.32
            self.effective_entangler_gate_pre_us = 0.2
            self.effective_entangler_gate_post_us = 0.1

        self.pulse_offset_mu = self.core.seconds_to_mu(
            self.effective_pulse_offset_us * 1e-6
        )
        self.pulse_width_mu = max(
            1, self.core.seconds_to_mu(self.effective_pulse_width_us * 1e-6)
        )
        self.cpu_gate_width_mu = self.core.seconds_to_mu(
            self.effective_cpu_gate_width_us * 1e-6
        )
        self.entangler_cycle_length_mu = self.core.seconds_to_mu(
            self.effective_entangler_cycle_length_us * 1e-6
        )
        self.entangler_gate_pre_mu = self.core.seconds_to_mu(
            self.effective_entangler_gate_pre_us * 1e-6
        )
        self.entangler_gate_post_mu = self.core.seconds_to_mu(
            self.effective_entangler_gate_post_us * 1e-6
        )
        self.entangler_run_margin_mu = self.core.seconds_to_mu(
            self.entangler_run_margin_us * 1e-6
        )
        self.inter_trial_mu = self.core.seconds_to_mu(self.inter_trial_us * 1e-6)

        self.entangler_gate_start_mu = max(
            8, self.pulse_offset_mu - self.entangler_gate_pre_mu
        )
        self.entangler_gate_stop_mu = (
            self.pulse_offset_mu + self.pulse_width_mu + self.entangler_gate_post_mu
        )
        self.entangler_timeout_mu = (
            self.entangler_cycle_length_mu + self.entangler_run_margin_mu
        )

        self._validate_timing()
        self._allocate_results()

    @staticmethod
    def _split_names(value):
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _split_ints(value):
        return [int(item.strip(), 0) for item in value.split(",") if item.strip()]

    def _validate_entangler_indices(self):
        if len(set(self.entangler_output_index_list)) != len(
            self.entangler_output_index_list
        ):
            raise ValueError("entangler_output_indices must be unique")
        if len(set(self.entangler_input_index_list)) != len(
            self.entangler_input_index_list
        ):
            raise ValueError("entangler_input_indices must be unique")

        for output_index in self.entangler_output_index_list:
            if output_index < 0 or output_index >= self.num_entangler_outputs_i:
                raise ValueError(
                    "entangler output index {} outside available outputs 0..{}".format(
                        output_index, self.num_entangler_outputs_i - 1
                    )
                )

        for input_index in self.entangler_input_index_list:
            if input_index < 0 or input_index >= self.num_entangler_inputs_i:
                raise ValueError(
                    "entangler input index {} outside available inputs 0..{}".format(
                        input_index, self.num_entangler_inputs_i - 1
                    )
                )

    def _validate_timing(self):
        if self.pulse_offset_mu + self.pulse_width_mu >= self.cpu_gate_width_mu:
            raise ValueError("cpu_gate_width_us must cover pulse_offset_us + pulse_width_us")
        if (self.entangler_cycle_length_mu >> 3) > 1023:
            raise ValueError(
                "entangler_cycle_length_us is too large for this PHY; use <= ~8.18 us"
            )
        if self.entangler_gate_stop_mu >= self.entangler_cycle_length_mu:
            raise ValueError("entangler input gate must end before the cycle ends")
        if self.entangler_timeout_mu <= self.entangler_cycle_length_mu:
            raise ValueError("entangler timeout must extend beyond one cycle")

    def _allocate_results(self):
        self.cpu_pulse_mu = [NO_TIMESTAMP for _ in range(self.repetitions_i)]
        self.cpu_click_mu = [
            [NO_TIMESTAMP for _ in range(self.num_pairs_i)]
            for _ in range(self.repetitions_i)
        ]
        self.cpu_counts = [
            [0 for _ in range(self.num_pairs_i)] for _ in range(self.repetitions_i)
        ]
        self.cpu_matched = [0 for _ in range(self.repetitions_i)]
        self.cpu_decision_wall_mu = [
            NO_TIMESTAMP for _ in range(self.repetitions_i)
        ]

        self.entangler_ttl_click_mu = [
            [NO_TIMESTAMP for _ in range(self.num_pairs_i)]
            for _ in range(self.repetitions_i)
        ]
        self.entangler_ttl_counts = [
            [0 for _ in range(self.num_pairs_i)] for _ in range(self.repetitions_i)
        ]
        self.entangler_input_ts_mu = [
            [NO_TIMESTAMP for _ in range(self.num_pairs_i)]
            for _ in range(self.repetitions_i)
        ]
        self.entangler_run_end_mu = [
            NO_TIMESTAMP for _ in range(self.repetitions_i)
        ]
        self.entangler_reason = [NO_TIMESTAMP for _ in range(self.repetitions_i)]
        self.entangler_status = [NO_TIMESTAMP for _ in range(self.repetitions_i)]
        self.entangler_ncycles = [NO_TIMESTAMP for _ in range(self.repetitions_i)]
        self.entangler_success = [0 for _ in range(self.repetitions_i)]
        self.entangler_wall_after_run_mu = [
            NO_TIMESTAMP for _ in range(self.repetitions_i)
        ]

    @rpc
    def _record_cpu_trial(
        self,
        trial: TInt32,
        pulse_mu: TInt64,
        matched: TInt32,
        decision_wall_mu: TInt64,
    ):
        trial_i = int(trial)
        self.cpu_pulse_mu[trial_i] = int(pulse_mu)
        self.cpu_matched[trial_i] = int(matched)
        self.cpu_decision_wall_mu[trial_i] = int(decision_wall_mu)

    @rpc
    def _record_cpu_input(
        self,
        trial: TInt32,
        input_i: TInt32,
        click_mu: TInt64,
        count: TInt32,
    ):
        self.cpu_click_mu[int(trial)][int(input_i)] = int(click_mu)
        self.cpu_counts[int(trial)][int(input_i)] = int(count)

    @rpc
    def _record_entangler_trial(
        self,
        trial: TInt32,
        run_end_mu: TInt64,
        reason: TInt32,
        status: TInt32,
        ncycles: TInt32,
        success: TInt32,
        wall_after_run_mu: TInt64,
    ):
        trial_i = int(trial)
        self.entangler_run_end_mu[trial_i] = int(run_end_mu)
        self.entangler_reason[trial_i] = int(reason)
        self.entangler_status[trial_i] = int(status)
        self.entangler_ncycles[trial_i] = int(ncycles)
        self.entangler_success[trial_i] = int(success)
        self.entangler_wall_after_run_mu[trial_i] = int(wall_after_run_mu)

    @rpc
    def _record_entangler_input(
        self,
        trial: TInt32,
        input_i: TInt32,
        ttl_click_mu: TInt64,
        ttl_count: TInt32,
        entangler_ts_mu: TInt32,
    ):
        self.entangler_ttl_click_mu[int(trial)][int(input_i)] = int(ttl_click_mu)
        self.entangler_ttl_counts[int(trial)][int(input_i)] = int(ttl_count)
        self.entangler_input_ts_mu[int(trial)][int(input_i)] = int(entangler_ts_mu)

    @kernel
    def _setup_cpu_io(self):
        self.entangler0.set_config(False, True)
        for ttl_input in self.inputs:
            ttl_input.input()
        for ttl_output in self.cpu_outputs:
            ttl_output.output()
            ttl_output.off()
        self.core.break_realtime()

    @kernel
    def _setup_entangler_monitor_io(self):
        for ttl_input in self.inputs:
            ttl_input.input()
        for ttl_output in self.cpu_outputs:
            ttl_output.output()
            ttl_output.off()
        self.core.break_realtime()

    @kernel
    def run_cpu_branch_kernel(self):
        self.core.reset()
        self._setup_cpu_io()

        for trial in range(self.repetitions_i):
            self.core.break_realtime()
            for ttl_output in self.cpu_outputs:
                ttl_output.off()
            delay_mu(self.inter_trial_mu)

            t_start_mu = now_mu()
            t_pulse_mu = t_start_mu + self.pulse_offset_mu

            if self.num_pairs_i == 1:
                with parallel:
                    self.inputs[0].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    with sequential:
                        at_mu(t_pulse_mu)
                        self.cpu_outputs[0].pulse_mu(np.int64(self.pulse_width_mu))
            elif self.num_pairs_i == 2:
                with parallel:
                    self.inputs[0].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    self.inputs[1].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    with sequential:
                        at_mu(t_pulse_mu)
                        with parallel:
                            self.cpu_outputs[0].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )
                            self.cpu_outputs[1].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )
            elif self.num_pairs_i == 3:
                with parallel:
                    self.inputs[0].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    self.inputs[1].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    self.inputs[2].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    with sequential:
                        at_mu(t_pulse_mu)
                        with parallel:
                            self.cpu_outputs[0].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )
                            self.cpu_outputs[1].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )
                            self.cpu_outputs[2].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )
            else:
                with parallel:
                    self.inputs[0].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    self.inputs[1].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    self.inputs[2].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    self.inputs[3].gate_rising_mu(np.int64(self.cpu_gate_width_mu))
                    with sequential:
                        at_mu(t_pulse_mu)
                        with parallel:
                            self.cpu_outputs[0].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )
                            self.cpu_outputs[1].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )
                            self.cpu_outputs[2].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )
                            self.cpu_outputs[3].pulse_mu(
                                np.int64(self.pulse_width_mu)
                            )

            t_gate_end_mu = now_mu()
            matched = 1
            click0_mu = NO_TIMESTAMP
            click1_mu = NO_TIMESTAMP
            click2_mu = NO_TIMESTAMP
            click3_mu = NO_TIMESTAMP

            click0_mu = self.inputs[0].timestamp_mu(t_gate_end_mu)
            if click0_mu < 0:
                matched = 0
            if self.num_pairs_i >= 2:
                click1_mu = self.inputs[1].timestamp_mu(t_gate_end_mu)
                if click1_mu < 0:
                    matched = 0
            if self.num_pairs_i >= 3:
                click2_mu = self.inputs[2].timestamp_mu(t_gate_end_mu)
                if click2_mu < 0:
                    matched = 0
            if self.num_pairs_i >= 4:
                click3_mu = self.inputs[3].timestamp_mu(t_gate_end_mu)
                if click3_mu < 0:
                    matched = 0

            decision_wall_mu = self.core.get_rtio_counter_mu()

            count0 = 0
            count1 = 0
            count2 = 0
            count3 = 0
            if click0_mu >= 0:
                count0 = 1 + self.inputs[0].count(t_gate_end_mu)
            if self.num_pairs_i >= 2 and click1_mu >= 0:
                count1 = 1 + self.inputs[1].count(t_gate_end_mu)
            if self.num_pairs_i >= 3 and click2_mu >= 0:
                count2 = 1 + self.inputs[2].count(t_gate_end_mu)
            if self.num_pairs_i >= 4 and click3_mu >= 0:
                count3 = 1 + self.inputs[3].count(t_gate_end_mu)

            self._record_cpu_input(trial, 0, click0_mu, count0)
            if self.num_pairs_i >= 2:
                self._record_cpu_input(trial, 1, click1_mu, count1)
            if self.num_pairs_i >= 3:
                self._record_cpu_input(trial, 2, click2_mu, count2)
            if self.num_pairs_i >= 4:
                self._record_cpu_input(trial, 3, click3_mu, count3)
            self._record_cpu_trial(trial, t_pulse_mu, matched, decision_wall_mu)

        self.core.break_realtime()
        for ttl_output in self.cpu_outputs:
            ttl_output.off()
        self.core.break_realtime()

    @kernel
    def _disable_all_entangler_channels(self):
        disabled_start_mu = self.entangler_cycle_length_mu + 8
        disabled_stop_mu = self.entangler_cycle_length_mu + 16

        for output_i in range(self.num_entangler_outputs_i):
            self.entangler0.set_timing_mu(
                output_i, np.int32(disabled_start_mu), np.int32(disabled_stop_mu)
            )

        for input_i in range(self.num_entangler_inputs_i):
            self.entangler0.set_timing_mu(
                self.num_entangler_outputs_i + input_i, np.int32(0), np.int32(0)
            )

    @kernel
    def _set_single_entangler_pattern(self):
        data = np.int32(self.expected_pattern_i | (1 << self.pattern_enable_shift_i))
        self.entangler0._write(self.entangler0._ADDRESS_WRITE.PATTERNS, data)

    @kernel
    def _configure_entangler_core(self):
        self.entangler0.set_config(False, True)
        self._disable_all_entangler_channels()

        for i in range(self.num_pairs_i):
            self.entangler0.set_timing_mu(
                self.entangler_output_index_list[i],
                np.int32(self.pulse_offset_mu),
                np.int32(self.pulse_offset_mu + self.pulse_width_mu),
            )
            self.entangler0.set_timing_mu(
                self.num_entangler_outputs_i + self.entangler_input_index_list[i],
                np.int32(self.entangler_gate_start_mu),
                np.int32(self.entangler_gate_stop_mu),
            )

        self.entangler0.set_cycle_length_mu(np.int32(self.entangler_cycle_length_mu))
        self.entangler0.set_config(True, True)
        self.core.break_realtime()
        self._set_single_entangler_pattern()
        self.core.break_realtime()

    @kernel
    def run_entangler_core_kernel(self):
        self.core.reset()
        self._setup_entangler_monitor_io()
        self._configure_entangler_core()

        for trial in range(self.repetitions_i):
            self.core.break_realtime()
            delay_mu(self.inter_trial_mu)

            if self.num_pairs_i == 1:
                with parallel:
                    self.inputs[0].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    run_end_mu, reason = self.entangler0.run_mu(
                        np.int32(self.entangler_timeout_mu)
                    )
            elif self.num_pairs_i == 2:
                with parallel:
                    self.inputs[0].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    self.inputs[1].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    run_end_mu, reason = self.entangler0.run_mu(
                        np.int32(self.entangler_timeout_mu)
                    )
            elif self.num_pairs_i == 3:
                with parallel:
                    self.inputs[0].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    self.inputs[1].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    self.inputs[2].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    run_end_mu, reason = self.entangler0.run_mu(
                        np.int32(self.entangler_timeout_mu)
                    )
            else:
                with parallel:
                    self.inputs[0].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    self.inputs[1].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    self.inputs[2].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    self.inputs[3].gate_rising_mu(np.int64(self.entangler_timeout_mu))
                    run_end_mu, reason = self.entangler0.run_mu(
                        np.int32(self.entangler_timeout_mu)
                    )

            t_gate_end_mu = now_mu()
            wall_after_run_mu = self.core.get_rtio_counter_mu()
            self.core.break_realtime()

            status = NO_TIMESTAMP
            ncycles = NO_TIMESTAMP
            success = 0
            if run_end_mu >= 0:
                self.core.break_realtime()
                status = self.entangler0.get_status()
                self.core.break_realtime()
                ncycles = self.entangler0.get_ncycles()
                if reason != ENTANGLER_TIMEOUT:
                    success = 1

            for i in range(self.num_pairs_i):
                ttl_click_mu = self.inputs[i].timestamp_mu(t_gate_end_mu)
                ttl_count = 0
                if ttl_click_mu >= 0:
                    ttl_count = 1 + self.inputs[i].count(t_gate_end_mu)

                entangler_ts_mu = NO_TIMESTAMP
                if run_end_mu >= 0:
                    self.core.break_realtime()
                    entangler_ts_mu = self.entangler0.get_timestamp_mu(
                        self.entangler_input_index_list[i]
                    )

                self._record_entangler_input(
                    trial, i, ttl_click_mu, ttl_count, entangler_ts_mu
                )

            self._record_entangler_trial(
                trial,
                run_end_mu,
                reason,
                status,
                ncycles,
                success,
                wall_after_run_mu,
            )

        self.core.break_realtime()
        self.entangler0.set_config(False, True)
        self.core.break_realtime()

    def run(self):
        print("=== CPU vs Entangler Core Match Timestamp ===")
        print("variant:", self.variant)
        print("CPU outputs:", ", ".join(self.cpu_output_name_list))
        print("TTL inputs:", ", ".join(self.input_name_list))
        print("entangler outputs:", self.entangler_output_index_list)
        print("entangler inputs:", self.entangler_input_index_list)
        print("expected pattern:", bin(self.expected_pattern_i))
        print("pattern enable shift:", self.pattern_enable_shift_i)
        print("test condition:", self.test_condition)
        print(
            "pulse offset/width us:",
            self.effective_pulse_offset_us,
            "/",
            self.effective_pulse_width_us,
        )
        print(
            "entangler cycle/gate pre/post us:",
            self.effective_entangler_cycle_length_us,
            "/",
            self.effective_entangler_gate_pre_us,
            "/",
            self.effective_entangler_gate_post_us,
        )
        print("")

        if self.variant_code in (0, 1):
            self.run_cpu_branch_kernel()
        if self.variant_code in (0, 2):
            self.run_entangler_core_kernel()

        self._publish_results()

    def _publish_results(self):
        prefix = "cpu_vs_entangler_match"

        self.set_dataset(
            f"{prefix}/input_names",
            np.array(self.input_name_list),
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/cpu_output_names",
            np.array(self.cpu_output_name_list),
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/entangler_input_indices",
            np.array(self.entangler_input_index_list, dtype=np.int64),
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/entangler_output_indices",
            np.array(self.entangler_output_index_list, dtype=np.int64),
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/expected_pattern",
            np.int64(self.expected_pattern_i),
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/test_condition",
            np.array([self.test_condition]),
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/pattern_enable_shift",
            np.int64(self.pattern_enable_shift_i),
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/effective_timing_us",
            np.array(
                [
                    self.effective_pulse_offset_us,
                    self.effective_pulse_width_us,
                    self.effective_cpu_gate_width_us,
                    self.effective_entangler_cycle_length_us,
                    self.effective_entangler_gate_pre_us,
                    self.effective_entangler_gate_post_us,
                ]
            ),
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/pulse_offset_mu",
            np.int64(self.pulse_offset_mu),
            broadcast=True,
            archive=True,
        )

        self._publish_cpu_results(prefix)
        self._publish_entangler_results(prefix)
        self._publish_comparison_results(prefix)

    def _publish_cpu_results(self, prefix):
        if self.variant_code not in (0, 1):
            print("CPU branch: not run")
            return

        cpu_pulse = np.array(self.cpu_pulse_mu, dtype=np.int64)
        cpu_click = np.array(self.cpu_click_mu, dtype=np.int64)
        cpu_counts = np.array(self.cpu_counts, dtype=np.int64)
        cpu_matched = np.array(self.cpu_matched, dtype=np.int64)
        cpu_decision_wall = np.array(self.cpu_decision_wall_mu, dtype=np.int64)
        cpu_latency = np.where(
            cpu_click >= 0, cpu_click - cpu_pulse[:, None], NO_TIMESTAMP
        )
        cpu_click_to_decision = np.where(
            (cpu_decision_wall >= 0) & np.all(cpu_click >= 0, axis=1),
            cpu_decision_wall - np.max(cpu_click, axis=1),
            NO_TIMESTAMP,
        )

        branch = f"{prefix}/cpu_branch"
        self.set_dataset(f"{branch}/pulse_mu", cpu_pulse, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/click_mu", cpu_click, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/counts", cpu_counts, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/matched", cpu_matched, broadcast=True, archive=True)
        self.set_dataset(
            f"{branch}/click_minus_pulse_mu",
            cpu_latency,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{branch}/click_to_decision_wall_mu",
            cpu_click_to_decision,
            broadcast=True,
            archive=True,
        )

        print("=== CPU branch summary ===")
        print("matches:", int(np.sum(cpu_matched)), "/", self.repetitions_i)
        for i, name in enumerate(self.input_name_list):
            latency = cpu_latency[:, i]
            print(
                "{} <- {} latency_mu mean/min/max:".format(
                    name, self.cpu_output_name_list[i]
                ),
                self._mean_or_minus_one(latency),
                self._min_or_minus_one(latency),
                self._max_or_minus_one(latency),
            )
        print(
            "latest click -> CPU decision wall mean/min/max:",
            self._mean_or_minus_one(cpu_click_to_decision),
            self._min_or_minus_one(cpu_click_to_decision),
            self._max_or_minus_one(cpu_click_to_decision),
        )
        print("")

    def _publish_entangler_results(self, prefix):
        if self.variant_code not in (0, 2):
            print("Entangler core: not run")
            return

        ttl_click = np.array(self.entangler_ttl_click_mu, dtype=np.int64)
        ttl_counts = np.array(self.entangler_ttl_counts, dtype=np.int64)
        input_ts = np.array(self.entangler_input_ts_mu, dtype=np.int64)
        run_end = np.array(self.entangler_run_end_mu, dtype=np.int64)
        reason = np.array(self.entangler_reason, dtype=np.int64)
        status = np.array(self.entangler_status, dtype=np.int64)
        ncycles = np.array(self.entangler_ncycles, dtype=np.int64)
        success = np.array(self.entangler_success, dtype=np.int64)
        wall_after_run = np.array(self.entangler_wall_after_run_mu, dtype=np.int64)

        entangler_latency = np.where(
            input_ts >= 0, input_ts - self.pulse_offset_mu, NO_TIMESTAMP
        )
        ttl_span = np.where(
            np.all(ttl_click >= 0, axis=1),
            np.max(ttl_click, axis=1) - np.min(ttl_click, axis=1),
            NO_TIMESTAMP,
        )
        run_return_after_ttl_click = np.where(
            (wall_after_run >= 0) & np.all(ttl_click >= 0, axis=1),
            wall_after_run - np.max(ttl_click, axis=1),
            NO_TIMESTAMP,
        )
        run_done_after_ttl_click = np.where(
            (run_end >= 0) & np.all(ttl_click >= 0, axis=1),
            run_end - np.max(ttl_click, axis=1),
            NO_TIMESTAMP,
        )
        timeout = np.where(
            (run_end >= 0) & (reason == ENTANGLER_TIMEOUT), 1, 0
        ).astype(np.int64)
        no_done = np.where(run_end < 0, 1, 0).astype(np.int64)

        branch = f"{prefix}/entangler_core"
        self.set_dataset(
            f"{branch}/ttl_click_mu", ttl_click, broadcast=True, archive=True
        )
        self.set_dataset(
            f"{branch}/ttl_counts", ttl_counts, broadcast=True, archive=True
        )
        self.set_dataset(
            f"{branch}/input_timestamp_mu", input_ts, broadcast=True, archive=True
        )
        self.set_dataset(f"{branch}/run_end_mu", run_end, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/reason", reason, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/status", status, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/ncycles", ncycles, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/success", success, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/timeout", timeout, broadcast=True, archive=True)
        self.set_dataset(f"{branch}/no_done_event", no_done, broadcast=True, archive=True)
        self.set_dataset(
            f"{branch}/input_timestamp_minus_pulse_offset_mu",
            entangler_latency,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{branch}/ttl_click_span_mu", ttl_span, broadcast=True, archive=True
        )
        self.set_dataset(
            f"{branch}/ttl_click_to_run_return_wall_mu",
            run_return_after_ttl_click,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{branch}/ttl_click_to_run_done_timestamp_mu",
            run_done_after_ttl_click,
            broadcast=True,
            archive=True,
        )

        print("=== Entangler core summary ===")
        print("successes:", int(np.sum(success)), "/", self.repetitions_i)
        print("timeouts:", int(np.sum(timeout)))
        print("no done events:", int(np.sum(no_done)))
        print("reason values:", sorted(set(reason.tolist())))
        for i, name in enumerate(self.input_name_list):
            print(
                "input {} ({}) timestamp_mu mean/min/max:".format(
                    self.entangler_input_index_list[i], name
                ),
                self._mean_or_minus_one(input_ts[:, i]),
                self._min_or_minus_one(input_ts[:, i]),
                self._max_or_minus_one(input_ts[:, i]),
            )
            print(
                "input {} ({}) timestamp - pulse_offset mean/min/max:".format(
                    self.entangler_input_index_list[i], name
                ),
                self._mean_or_minus_one(entangler_latency[:, i]),
                self._min_or_minus_one(entangler_latency[:, i]),
                self._max_or_minus_one(entangler_latency[:, i]),
            )
        print(
            "TTL monitor click span mean/min/max:",
            self._mean_or_minus_one(ttl_span),
            self._min_or_minus_one(ttl_span),
            self._max_or_minus_one(ttl_span),
        )
        print(
            "latest TTL click -> entangler done timestamp mean/min/max:",
            self._mean_or_minus_one(run_done_after_ttl_click),
            self._min_or_minus_one(run_done_after_ttl_click),
            self._max_or_minus_one(run_done_after_ttl_click),
        )
        print(
            "latest TTL click -> run return wall mean/min/max:",
            self._mean_or_minus_one(run_return_after_ttl_click),
            self._min_or_minus_one(run_return_after_ttl_click),
            self._max_or_minus_one(run_return_after_ttl_click),
        )

    def _publish_comparison_results(self, prefix):
        if self.variant_code != 0:
            return

        cpu_click = np.array(self.cpu_click_mu, dtype=np.int64)
        cpu_decision_wall = np.array(self.cpu_decision_wall_mu, dtype=np.int64)
        ttl_click = np.array(self.entangler_ttl_click_mu, dtype=np.int64)
        run_end = np.array(self.entangler_run_end_mu, dtype=np.int64)
        wall_after_run = np.array(self.entangler_wall_after_run_mu, dtype=np.int64)

        cpu_click_to_decision = np.where(
            (cpu_decision_wall >= 0) & np.all(cpu_click >= 0, axis=1),
            cpu_decision_wall - np.max(cpu_click, axis=1),
            NO_TIMESTAMP,
        )
        entangler_click_to_done = np.where(
            (run_end >= 0) & np.all(ttl_click >= 0, axis=1),
            run_end - np.max(ttl_click, axis=1),
            NO_TIMESTAMP,
        )
        entangler_click_to_return = np.where(
            (wall_after_run >= 0) & np.all(ttl_click >= 0, axis=1),
            wall_after_run - np.max(ttl_click, axis=1),
            NO_TIMESTAMP,
        )
        done_minus_cpu = np.where(
            (cpu_click_to_decision >= 0) & (entangler_click_to_done >= 0),
            entangler_click_to_done - cpu_click_to_decision,
            NO_TIMESTAMP,
        )
        return_minus_cpu = np.where(
            (cpu_click_to_decision >= 0) & (entangler_click_to_return >= 0),
            entangler_click_to_return - cpu_click_to_decision,
            NO_TIMESTAMP,
        )

        branch = f"{prefix}/comparison"
        self.set_dataset(
            f"{branch}/cpu_click_to_decision_wall_mu",
            cpu_click_to_decision,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{branch}/entangler_click_to_done_timestamp_mu",
            entangler_click_to_done,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{branch}/entangler_click_to_run_return_wall_mu",
            entangler_click_to_return,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{branch}/entangler_done_minus_cpu_decision_mu",
            done_minus_cpu,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{branch}/entangler_return_minus_cpu_decision_mu",
            return_minus_cpu,
            broadcast=True,
            archive=True,
        )

        print("")
        print("=== Speed comparison (mu) ===")
        print(
            "CPU latest click -> decision wall mean/min/max:",
            self._mean_or_minus_one(cpu_click_to_decision),
            self._min_or_minus_one(cpu_click_to_decision),
            self._max_or_minus_one(cpu_click_to_decision),
        )
        print(
            "Entangler latest click -> done timestamp mean/min/max:",
            self._mean_or_minus_one(entangler_click_to_done),
            self._min_or_minus_one(entangler_click_to_done),
            self._max_or_minus_one(entangler_click_to_done),
        )
        print(
            "Entangler latest click -> run return wall mean/min/max:",
            self._mean_or_minus_one(entangler_click_to_return),
            self._min_or_minus_one(entangler_click_to_return),
            self._max_or_minus_one(entangler_click_to_return),
        )
        print(
            "Entangler done - CPU decision mean/min/max:",
            self._mean_masked_or_minus_one(
                done_minus_cpu,
                (cpu_click_to_decision >= 0) & (entangler_click_to_done >= 0),
            ),
            self._min_masked_or_minus_one(
                done_minus_cpu,
                (cpu_click_to_decision >= 0) & (entangler_click_to_done >= 0),
            ),
            self._max_masked_or_minus_one(
                done_minus_cpu,
                (cpu_click_to_decision >= 0) & (entangler_click_to_done >= 0),
            ),
        )
        print(
            "Entangler return - CPU decision mean/min/max:",
            self._mean_or_minus_one(return_minus_cpu),
            self._min_or_minus_one(return_minus_cpu),
            self._max_or_minus_one(return_minus_cpu),
        )

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

    def _max_or_minus_one(self, values):
        valid = self._valid_values(values)
        if valid.size == 0:
            return -1
        return int(np.max(valid))

    @staticmethod
    def _masked_values(values, mask):
        return values[mask]

    def _mean_masked_or_minus_one(self, values, mask):
        valid = self._masked_values(values, mask)
        if valid.size == 0:
            return -1
        return int(np.mean(valid))

    def _min_masked_or_minus_one(self, values, mask):
        valid = self._masked_values(values, mask)
        if valid.size == 0:
            return -1
        return int(np.min(valid))

    def _max_masked_or_minus_one(self, values, mask):
        valid = self._masked_values(values, mask)
        if valid.size == 0:
            return -1
        return int(np.max(valid))
