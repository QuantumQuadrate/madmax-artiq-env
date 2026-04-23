"""
Simple TTL loopback timestamp test.

Default wiring to check with the current one-DIO entangler mapping:

    ttl4 output -> ttl3 input
    ttl5 output -> ttl0 input

Run once with output_name=ttl4 and input_names=ttl0,ttl1,ttl2,ttl3, then
again with output_name=ttl5. A working loopback should show static_level=1
for the connected input and a non-negative timestamp_mu.
"""

from artiq.experiment import *
import numpy as np


class SimpleTTLLoopbackTimestamp(EnvExperiment):
    """Pulse one TTL output and timestamp rising edges on one or more inputs."""

    def build(self):
        self.setattr_device("core")

        self.setattr_argument(
            "output_name",
            StringValue(default="ttl4"),
            group="Devices",
        )
        self.setattr_argument(
            "input_names",
            StringValue(default="ttl0,ttl1,ttl2,ttl3"),
            group="Devices",
        )
        self.setattr_argument(
            "repetitions",
            NumberValue(default=10, min=1, max=10000, step=1, ndecimals=0),
            group="Timing",
        )
        self.setattr_argument(
            "pulse_offset_us",
            NumberValue(default=50.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "pulse_width_us",
            NumberValue(default=10.0, min=0.1, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "gate_width_us",
            NumberValue(default=200.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "inter_trial_us",
            NumberValue(default=100.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "pre_gate_low_us",
            NumberValue(default=10.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "static_hold_us",
            NumberValue(default=20.0, min=0.1, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "check_static_level",
            BooleanValue(default=True),
            group="Timing",
        )
        self.setattr_argument(
            "edge",
            EnumerationValue(["rising", "falling", "both"], default="rising"),
            group="Timing",
        )

    def prepare(self):
        self.output = self.get_device(self.output_name)
        self.input_name_list = [
            name.strip() for name in self.input_names.split(",") if name.strip()
        ]
        if len(self.input_name_list) == 0:
            raise ValueError("input_names must contain at least one TTL device name")

        self.inputs = [self.get_device(name) for name in self.input_name_list]

        self.repetitions_i = int(self.repetitions)
        self.num_inputs_i = len(self.input_name_list)
        self.check_static_level_i = bool(self.check_static_level)
        self.edge_code = {
            "rising": 0,
            "falling": 1,
            "both": 2,
        }[self.edge]

        self.pulse_offset_mu = self.core.seconds_to_mu(self.pulse_offset_us * 1e-6)
        self.pulse_width_mu = max(
            1, self.core.seconds_to_mu(self.pulse_width_us * 1e-6)
        )
        self.gate_width_mu = self.core.seconds_to_mu(self.gate_width_us * 1e-6)
        self.inter_trial_mu = self.core.seconds_to_mu(self.inter_trial_us * 1e-6)
        self.pre_gate_low_mu = self.core.seconds_to_mu(self.pre_gate_low_us * 1e-6)
        self.static_hold_mu = max(
            1, self.core.seconds_to_mu(self.static_hold_us * 1e-6)
        )

        if self.pulse_offset_mu + self.pulse_width_mu >= self.gate_width_mu:
            raise ValueError("gate_width_us must cover pulse_offset_us + pulse_width_us")

        self.pulse_mu = [-1 for _ in range(self.repetitions_i)]
        self.timestamps_mu = [
            [-1 for _ in range(self.num_inputs_i)] for _ in range(self.repetitions_i)
        ]
        self.event_counts = [
            [0 for _ in range(self.num_inputs_i)] for _ in range(self.repetitions_i)
        ]
        self.static_high_levels = [
            [-1 for _ in range(self.num_inputs_i)] for _ in range(self.repetitions_i)
        ]
        self.static_low_levels = [
            [-1 for _ in range(self.num_inputs_i)] for _ in range(self.repetitions_i)
        ]

    @rpc
    def _record_pulse_mu(self, trial: TInt32, pulse_mu: TInt64):
        self.pulse_mu[int(trial)] = int(pulse_mu)

    @rpc
    def _record_timestamp_mu(self, trial: TInt32, input_index: TInt32, timestamp_mu: TInt64):
        self.timestamps_mu[int(trial)][int(input_index)] = int(timestamp_mu)

    @rpc
    def _record_event_count(self, trial: TInt32, input_index: TInt32, count: TInt32):
        self.event_counts[int(trial)][int(input_index)] = int(count)

    @rpc
    def _record_static_levels(
        self,
        trial: TInt32,
        input_index: TInt32,
        high_level: TInt32,
        low_level: TInt32,
    ):
        self.static_high_levels[int(trial)][int(input_index)] = int(high_level)
        self.static_low_levels[int(trial)][int(input_index)] = int(low_level)

    @kernel
    def _sample_static_levels(self, trial: TInt32):
        self.output.on()
        delay_mu(self.static_hold_mu)

        for ttl_input in self.inputs:
            ttl_input.sample_input()

        delay_mu(8)
        self.output.off()
        delay_mu(self.static_hold_mu)

        for ttl_input in self.inputs:
            ttl_input.sample_input()

        delay_mu(8)

        for i in range(self.num_inputs_i):
            high_level = self.inputs[i].sample_get()
            low_level = self.inputs[i].sample_get()
            self._record_static_levels(trial, i, high_level, low_level)

    @kernel
    def _gate_input(self, ttl_input, duration_mu: TInt64):
        if self.edge_code == 0:
            ttl_input.gate_rising_mu(duration_mu)
        elif self.edge_code == 1:
            ttl_input.gate_falling_mu(duration_mu)
        else:
            ttl_input.gate_both_mu(duration_mu)

    @kernel
    def run(self):
        self.core.reset()

        self.output.output()
        self.output.off()
        for ttl_input in self.inputs:
            ttl_input.input()

        self.core.break_realtime()

        for trial in range(self.repetitions_i):
            self.core.break_realtime()

            if self.check_static_level_i:
                self._sample_static_levels(trial)
                self.core.break_realtime()

            self.output.off()
            delay_mu(self.pre_gate_low_mu)
            t_start_mu = now_mu()
            t_pulse_mu = t_start_mu + self.pulse_offset_mu

            with parallel:
                for ttl_input in self.inputs:
                    self._gate_input(ttl_input, np.int64(self.gate_width_mu))

                with sequential:
                    at_mu(t_pulse_mu)
                    self.output.pulse_mu(np.int64(self.pulse_width_mu))

            t_gate_end_mu = now_mu()

            for i in range(self.num_inputs_i):
                timestamp_mu = self.inputs[i].timestamp_mu(t_gate_end_mu)
                count = 0
                if timestamp_mu >= 0:
                    count = 1 + self.inputs[i].count(t_gate_end_mu)
                self._record_timestamp_mu(trial, i, timestamp_mu)
                self._record_event_count(trial, i, count)

            self._record_pulse_mu(trial, t_pulse_mu)

            self.core.break_realtime()
            delay_mu(self.inter_trial_mu)

        self.core.break_realtime()
        self.output.off()
        self.core.break_realtime()

    def analyze(self):
        pulse_mu = np.array(self.pulse_mu, dtype=np.int64)
        timestamps_mu = np.array(self.timestamps_mu, dtype=np.int64)
        event_counts = np.array(self.event_counts, dtype=np.int64)
        static_high_levels = np.array(self.static_high_levels, dtype=np.int64)
        static_low_levels = np.array(self.static_low_levels, dtype=np.int64)
        detected = timestamps_mu >= 0
        latency_mu = np.where(detected, timestamps_mu - pulse_mu[:, None], -1)

        prefix = "simple_ttl_loopback"
        self.set_dataset(f"{prefix}/pulse_mu", pulse_mu, broadcast=True, archive=True)
        self.set_dataset(
            f"{prefix}/timestamps_mu", timestamps_mu, broadcast=True, archive=True
        )
        self.set_dataset(
            f"{prefix}/event_counts", event_counts, broadcast=True, archive=True
        )
        self.set_dataset(
            f"{prefix}/static_high_levels",
            static_high_levels,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(
            f"{prefix}/static_low_levels",
            static_low_levels,
            broadcast=True,
            archive=True,
        )
        self.set_dataset(f"{prefix}/detected", detected, broadcast=True, archive=True)
        self.set_dataset(f"{prefix}/latency_mu", latency_mu, broadcast=True, archive=True)

        print("=== Simple TTL Loopback Timestamp ===")
        print("output:", self.output_name)
        print("inputs:", ", ".join(self.input_name_list))
        print("repetitions:", self.repetitions_i)
        print("edge:", self.edge)
        print("pulse width us:", self.pulse_width_us)
        print("gate width us:", self.gate_width_us)
        print("")

        for i, name in enumerate(self.input_name_list):
            count = int(np.sum(detected[:, i]))
            event_count_total = int(np.sum(event_counts[:, i]))
            high_levels = static_high_levels[:, i]
            low_levels = static_low_levels[:, i]
            high_count = int(np.sum(high_levels == 1))
            low_count = int(np.sum(low_levels == 0))
            valid_latency = latency_mu[latency_mu[:, i] >= 0, i]

            print(f"{name} <- {self.output_name}:")
            print("  static high while output on:", high_count, "/", self.repetitions_i)
            print("  static low after output off:", low_count, "/", self.repetitions_i)
            print("  timestamp count:", count, "/", self.repetitions_i)
            print("  total gated edge events:", event_count_total)
            if valid_latency.size > 0:
                print(
                    "  latency_mu mean/min/max:",
                    int(np.mean(valid_latency)),
                    int(np.min(valid_latency)),
                    int(np.max(valid_latency)),
                )
            else:
                print("  latency_mu mean/min/max: -1 -1 -1")


class DirectTTLLoopbackTimestamp(EnvExperiment):
    """Minimal one-output/one-input timestamp test with no helper indirection."""

    def build(self):
        self.setattr_device("core")
        self.setattr_argument("output_name", StringValue(default="ttl4"))
        self.setattr_argument("input_name", StringValue(default="ttl3"))
        self.setattr_argument(
            "edge",
            EnumerationValue(["rising", "falling", "both"], default="rising"),
        )
        self.setattr_argument(
            "repetitions",
            NumberValue(default=10, min=1, max=10000, step=1, ndecimals=0),
        )
        self.setattr_argument(
            "pulse_offset_us",
            NumberValue(default=50.0, min=1.0, max=1e6, unit="us", scale=1.0),
        )
        self.setattr_argument(
            "pulse_width_us",
            NumberValue(default=10.0, min=0.1, max=1e6, unit="us", scale=1.0),
        )
        self.setattr_argument(
            "gate_width_us",
            NumberValue(default=200.0, min=1.0, max=1e6, unit="us", scale=1.0),
        )
        self.setattr_argument(
            "pre_gate_low_us",
            NumberValue(default=100.0, min=0.0, max=1e6, unit="us", scale=1.0),
        )

    def prepare(self):
        self.output = self.get_device(self.output_name)
        self.input = self.get_device(self.input_name)
        self.repetitions_i = int(self.repetitions)
        self.edge_code = {
            "rising": 0,
            "falling": 1,
            "both": 2,
        }[self.edge]
        self.pulse_offset_mu = self.core.seconds_to_mu(self.pulse_offset_us * 1e-6)
        self.pulse_width_mu = max(
            1, self.core.seconds_to_mu(self.pulse_width_us * 1e-6)
        )
        self.gate_width_mu = self.core.seconds_to_mu(self.gate_width_us * 1e-6)
        self.pre_gate_low_mu = self.core.seconds_to_mu(self.pre_gate_low_us * 1e-6)
        self.pulse_mu = [-1 for _ in range(self.repetitions_i)]
        self.timestamp_mu = [-1 for _ in range(self.repetitions_i)]
        self.counts = [0 for _ in range(self.repetitions_i)]

    @rpc
    def _record(self, trial: TInt32, pulse_mu: TInt64, timestamp_mu: TInt64, count: TInt32):
        self.pulse_mu[int(trial)] = int(pulse_mu)
        self.timestamp_mu[int(trial)] = int(timestamp_mu)
        self.counts[int(trial)] = int(count)

    @kernel
    def run(self):
        self.core.reset()
        self.output.output()
        self.output.off()
        self.input.input()
        self.core.break_realtime()

        for trial in range(self.repetitions_i):
            self.core.break_realtime()
            self.output.off()
            delay_mu(self.pre_gate_low_mu)

            t_start_mu = now_mu()
            t_pulse_mu = t_start_mu + self.pulse_offset_mu

            if self.edge_code == 0:
                with parallel:
                    self.input.gate_rising_mu(np.int64(self.gate_width_mu))
                    with sequential:
                        at_mu(t_pulse_mu)
                        self.output.pulse_mu(np.int64(self.pulse_width_mu))
            elif self.edge_code == 1:
                with parallel:
                    self.input.gate_falling_mu(np.int64(self.gate_width_mu))
                    with sequential:
                        at_mu(t_pulse_mu)
                        self.output.pulse_mu(np.int64(self.pulse_width_mu))
            else:
                with parallel:
                    self.input.gate_both_mu(np.int64(self.gate_width_mu))
                    with sequential:
                        at_mu(t_pulse_mu)
                        self.output.pulse_mu(np.int64(self.pulse_width_mu))

            t_gate_end_mu = now_mu()
            timestamp_mu = self.input.timestamp_mu(t_gate_end_mu)
            count = 0
            if timestamp_mu >= 0:
                count = 1 + self.input.count(t_gate_end_mu)
            self._record(trial, t_pulse_mu, timestamp_mu, count)

        self.core.break_realtime()
        self.output.off()
        self.core.break_realtime()

    def analyze(self):
        pulse_mu = np.array(self.pulse_mu, dtype=np.int64)
        timestamp_mu = np.array(self.timestamp_mu, dtype=np.int64)
        counts = np.array(self.counts, dtype=np.int64)
        latency_mu = np.where(timestamp_mu >= 0, timestamp_mu - pulse_mu, -1)
        valid = latency_mu[latency_mu >= 0]

        self.set_dataset("direct_ttl_loopback/pulse_mu", pulse_mu, broadcast=True)
        self.set_dataset("direct_ttl_loopback/timestamp_mu", timestamp_mu, broadcast=True)
        self.set_dataset("direct_ttl_loopback/counts", counts, broadcast=True)
        self.set_dataset("direct_ttl_loopback/latency_mu", latency_mu, broadcast=True)

        print("=== Direct TTL Loopback Timestamp ===")
        print("output:", self.output_name)
        print("input:", self.input_name)
        print("edge:", self.edge)
        print("timestamps:", int(np.sum(timestamp_mu >= 0)), "/", self.repetitions_i)
        print("total gated edge events:", int(np.sum(counts)))
        print("latency_mu:", latency_mu)
        if valid.size > 0:
            print(
                "latency_mu mean/min/max:",
                int(np.mean(valid)),
                int(np.min(valid)),
                int(np.max(valid)),
            )
        else:
            print("latency_mu mean/min/max: -1 -1 -1")
