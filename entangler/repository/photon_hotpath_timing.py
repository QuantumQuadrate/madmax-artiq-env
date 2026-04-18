"""
Minimal post-photon-detection timing harness.

This experiment is intentionally small and compares two versions of the same
hot path:

1. `baseline`: mirrors the duplicated SPCM0/SPCM1 branch structure and keeps
   surrogate "DDS set" operations inside the hot path.
2. `optimized`: unifies the branches and assumes DDS configuration can be
   preloaded outside the hot path, while preserving the externally visible
   switch timing.

Why no dedicated DDS marker output?
This board only exposes four TTL outputs on the single DIO card, and for a
clean hardware loopback we use two of them as independent simulated SPCM
sources. The DDS timing is still recorded in datasets at the points where
`dds_microwaves.set(...)` and `dds_MW_RF.set(...)` would have been issued, but
there is no separate physical TTL pin reserved for those markers.

Two acquisition modes are provided:

* `synthetic`: the click timestamp is modeled as having occurred some number of
  machine units before the branch executes. This isolates the kernel fast path
  and is the safest default.
* `ttl_loopback`: one output pulses into an SPCM input through an external
  jumper, so `timestamp_mu()` is exercised for real.
"""

from artiq.experiment import *
import numpy as np


class PhotonHotpathTimingHarness(EnvExperiment):
    DEFAULT_MODE = "synthetic"
    DEFAULT_VARIANT = "both"
    DEFAULT_SPCM_CHANNEL = "SPCM0"
    DEFAULT_REPETITIONS = 25

    def build(self):
        self.setattr_device("core")

        self.setattr_argument(
            "mode",
            EnumerationValue(["synthetic", "ttl_loopback"], default=self.DEFAULT_MODE),
            group="Benchmark",
        )
        self.setattr_argument(
            "variant",
            EnumerationValue(["both", "baseline", "optimized"], default=self.DEFAULT_VARIANT),
            group="Benchmark",
        )
        self.setattr_argument(
            "spcm_channel",
            EnumerationValue(["SPCM0", "SPCM1"], default=self.DEFAULT_SPCM_CHANNEL),
            group="Benchmark",
        )
        self.setattr_argument(
            "repetitions",
            NumberValue(default=self.DEFAULT_REPETITIONS, min=1, max=10000, step=1, ndecimals=0),
            group="Benchmark",
        )
        self.setattr_argument(
            "synthetic_detection_lag_us",
            NumberValue(default=8.0, min=0.0, max=1000.0, unit="us", scale=1.0),
            group="Benchmark",
        )
        self.setattr_argument(
            "gate_width_us",
            NumberValue(default=40.0, min=1.0, max=1e6, unit="us", scale=1.0),
            group="Loopback",
        )
        self.setattr_argument(
            "loopback_pulse_offset_us",
            NumberValue(default=5.0, min=0.1, max=1e6, unit="us", scale=1.0),
            group="Loopback",
        )
        self.setattr_argument(
            "marker_pulse_ns",
            NumberValue(default=200.0, min=50.0, max=1e6, unit="ns", scale=1.0),
            group="Loopback",
        )
        self.setattr_argument(
            "t_start_MW_mapping_us",
            NumberValue(default=20.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "t_microwave_11_pulse_us",
            NumberValue(default=2.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "t_MW_RF_pulse_us",
            NumberValue(default=4.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "baseline_dds_mw_set_offset_us",
            NumberValue(default=5.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "baseline_dds_rf_set_offset_us",
            NumberValue(default=10.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )
        self.setattr_argument(
            "pulse_start_offset_us",
            NumberValue(default=15.0, min=0.0, max=1e6, unit="us", scale=1.0),
            group="Timing",
        )

        self._configure_layout()

    def _device_exists(self, name):
        try:
            self.get_device(name)
            return True
        except Exception:
            return False

    def _configure_layout(self):
        # Observed on hardware from the dashboard naming:
        #   dashboard ttl7 -> physical TTL6 output
        #   dashboard ttl8 -> physical TTL7 output
        #   dashboard ttl2 -> physical TTL0 input
        #   dashboard ttl3 -> physical TTL1 input
        observed_inputs = ["ttl2", "ttl3"]
        observed_outputs = ["ttl4", "ttl5", "ttl7", "ttl8"]
        one_dio_inputs = ["ttl0", "ttl1", "ttl2", "ttl3"]
        one_dio_outputs = ["ttl4", "ttl5", "ttl6", "ttl7"]
        legacy_outputs = ["ttl0", "ttl1", "ttl4", "ttl5"]
        legacy_inputs = ["ttl2", "ttl3"]

        if all(self._device_exists(name) for name in observed_outputs + observed_inputs):
            self.layout_name = "observed_dashboard_map"
            output_names = observed_outputs
            input_names = observed_inputs
        elif all(self._device_exists(name) for name in one_dio_outputs + one_dio_inputs):
            self.layout_name = "one_dio_4in_4out"
            output_names = one_dio_outputs
            input_names = one_dio_inputs
        else:
            self.layout_name = "legacy_fallback_4out_2in"
            output_names = legacy_outputs
            input_names = legacy_inputs

        self.output_names = output_names
        self.input_names = input_names

        self.ttl_mw_switch = self.get_device(output_names[0])
        self.ttl_rf_switch = self.get_device(output_names[1])
        self.ttl_spcm0_trigger = self.get_device(output_names[2])
        self.ttl_spcm1_trigger = self.get_device(output_names[3])

        self.spcm_inputs = [self.get_device(name) for name in input_names[:2]]

    def prepare(self):
        ref_period = self.core.ref_period

        self.repetitions_i = int(self.repetitions)
        self.mode_code = 0 if self.mode == "synthetic" else 1
        self.variant_code = {
            "both": 0,
            "baseline": 1,
            "optimized": 2,
        }[self.variant]
        self.branch_index = 0 if self.spcm_channel == "SPCM0" else 1

        self.synthetic_detection_lag_mu = self._seconds_to_mu(
            self.synthetic_detection_lag_us * us, ref_period
        )
        self.gate_width_mu = self._seconds_to_mu(self.gate_width_us * us, ref_period)
        self.loopback_pulse_offset_mu = self._seconds_to_mu(
            self.loopback_pulse_offset_us * us, ref_period
        )
        self.marker_pulse_mu = max(
            1, self._seconds_to_mu(self.marker_pulse_ns * ns, ref_period)
        )
        self.t_start_MW_mapping_mu = self._seconds_to_mu(
            self.t_start_MW_mapping_us * us, ref_period
        )
        self.t_microwave_11_pulse_mu = self._seconds_to_mu(
            self.t_microwave_11_pulse_us * us, ref_period
        )
        self.t_MW_RF_pulse_mu = self._seconds_to_mu(
            self.t_MW_RF_pulse_us * us, ref_period
        )
        self.baseline_dds_mw_set_offset_mu = self._seconds_to_mu(
            self.baseline_dds_mw_set_offset_us * us, ref_period
        )
        self.baseline_dds_rf_set_offset_mu = self._seconds_to_mu(
            self.baseline_dds_rf_set_offset_us * us, ref_period
        )
        self.pulse_start_offset_mu = self._seconds_to_mu(
            self.pulse_start_offset_us * us, ref_period
        )

        self.samples = {"baseline": [], "optimized": []}
        self.timeouts = {"baseline": 0, "optimized": 0}

    @staticmethod
    def _seconds_to_mu(seconds, ref_period):
        return int(round(seconds / ref_period))

    @rpc
    def _record_timeout(self, variant: TInt32):
        key = "baseline" if variant == 0 else "optimized"
        self.timeouts[key] += 1

    @rpc
    def _record_sample(
        self,
        variant: TInt32,
        click_time: TInt64,
        branch_start: TInt64,
        schedule_done: TInt64,
        wall_before: TInt64,
        slack_before: TInt64,
        slack_after: TInt64,
        mw_on_target: TInt64,
        mw_off_target: TInt64,
        dds_mw_target: TInt64,
        dds_rf_target: TInt64,
        pulse_start_target: TInt64,
        pulse_end_target: TInt64,
    ):
        key = "baseline" if variant == 0 else "optimized"
        self.samples[key].append(
            {
                "click_time": int(click_time),
                "branch_start": int(branch_start),
                "schedule_done": int(schedule_done),
                "wall_before": int(wall_before),
                "slack_before": int(slack_before),
                "slack_after": int(slack_after),
                "mw_on_target": int(mw_on_target),
                "mw_off_target": int(mw_off_target),
                "dds_mw_target": int(dds_mw_target),
                "dds_rf_target": int(dds_rf_target),
                "pulse_start_target": int(pulse_start_target),
                "pulse_end_target": int(pulse_end_target),
            }
        )

    @kernel
    def _setup_io(self):
        self.ttl_mw_switch.output()
        self.ttl_rf_switch.output()
        self.ttl_spcm0_trigger.output()
        self.ttl_spcm1_trigger.output()
        self.ttl_mw_switch.on()
        self.ttl_rf_switch.off()
        self.ttl_spcm0_trigger.off()
        self.ttl_spcm1_trigger.off()
        for ttl in self.spcm_inputs:
            ttl.input()
        self.core.break_realtime()

    @kernel
    def _get_click_time(self) -> TInt64:
        if self.mode_code == 0:
            return now_mu() - self.synthetic_detection_lag_mu
        return self._get_loopback_click_time()

    @kernel
    def _get_loopback_click_time(self) -> TInt64:
        t_gate_start = now_mu()
        if self.branch_index == 0:
            with parallel:
                t_end_spcm0 = self.spcm_inputs[0].gate_rising_mu(np.int64(self.gate_width_mu))
                t_end_spcm1 = self.spcm_inputs[1].gate_rising_mu(np.int64(self.gate_width_mu))
                at_mu(t_gate_start + self.loopback_pulse_offset_mu)
                self.ttl_spcm0_trigger.pulse_mu(np.int64(self.marker_pulse_mu))
        else:
            with parallel:
                t_end_spcm0 = self.spcm_inputs[0].gate_rising_mu(np.int64(self.gate_width_mu))
                t_end_spcm1 = self.spcm_inputs[1].gate_rising_mu(np.int64(self.gate_width_mu))
                at_mu(t_gate_start + self.loopback_pulse_offset_mu)
                self.ttl_spcm1_trigger.pulse_mu(np.int64(self.marker_pulse_mu))

        click0 = self.spcm_inputs[0].timestamp_mu(t_end_spcm0)
        click1 = self.spcm_inputs[1].timestamp_mu(t_end_spcm1)

        if self.branch_index == 0:
            return click0
        return click1

    @kernel
    def _baseline_spcm0_path(self, click_time: TInt64):
        self._schedule_baseline_common(click_time)

    @kernel
    def _baseline_spcm1_path(self, click_time: TInt64):
        self._schedule_baseline_common(click_time)

    @kernel
    def _schedule_baseline_common(self, click_time: TInt64):
        branch_start = now_mu()
        wall_before = self.core.get_rtio_counter_mu()
        slack_before = branch_start - wall_before

        mw_on_target = click_time + self.t_start_MW_mapping_mu
        mw_off_target = mw_on_target + self.t_microwave_11_pulse_mu
        dds_mw_target = -1
        dds_rf_target = -1
        pulse_start_target = -1
        pulse_end_target = -1

        at_mu(mw_on_target)
        self.ttl_mw_switch.off()
        at_mu(mw_off_target)
        self.ttl_mw_switch.on()

        if self.t_MW_RF_pulse_mu > 0:
            dds_mw_target = mw_off_target + self.baseline_dds_mw_set_offset_mu
            dds_rf_target = mw_off_target + self.baseline_dds_rf_set_offset_mu
            pulse_start_target = mw_off_target + self.pulse_start_offset_mu
            pulse_end_target = pulse_start_target + self.t_MW_RF_pulse_mu

            at_mu(pulse_start_target)
            with parallel:
                self.ttl_mw_switch.off()
                self.ttl_rf_switch.on()

            at_mu(pulse_end_target)
            with parallel:
                self.ttl_mw_switch.on()
                self.ttl_rf_switch.off()

        schedule_done = now_mu()
        slack_after = schedule_done - self.core.get_rtio_counter_mu()
        self._record_sample(
            0,
            click_time,
            branch_start,
            schedule_done,
            wall_before,
            slack_before,
            slack_after,
            mw_on_target,
            mw_off_target,
            dds_mw_target,
            dds_rf_target,
            pulse_start_target,
            pulse_end_target,
        )

    @kernel
    def _schedule_optimized_common(self, click_time: TInt64):
        branch_start = now_mu()
        wall_before = self.core.get_rtio_counter_mu()
        slack_before = branch_start - wall_before

        mw_on_target = click_time + self.t_start_MW_mapping_mu
        mw_off_target = mw_on_target + self.t_microwave_11_pulse_mu
        pulse_start_target = -1
        pulse_end_target = -1

        at_mu(mw_on_target)
        self.ttl_mw_switch.off()
        at_mu(mw_off_target)
        self.ttl_mw_switch.on()

        if self.t_MW_RF_pulse_mu > 0:
            pulse_start_target = mw_off_target + self.pulse_start_offset_mu
            pulse_end_target = pulse_start_target + self.t_MW_RF_pulse_mu

            at_mu(pulse_start_target)
            with parallel:
                self.ttl_mw_switch.off()
                self.ttl_rf_switch.on()

            at_mu(pulse_end_target)
            with parallel:
                self.ttl_mw_switch.on()
                self.ttl_rf_switch.off()

        schedule_done = now_mu()
        slack_after = schedule_done - self.core.get_rtio_counter_mu()
        self._record_sample(
            1,
            click_time,
            branch_start,
            schedule_done,
            wall_before,
            slack_before,
            slack_after,
            mw_on_target,
            mw_off_target,
            -1,
            -1,
            pulse_start_target,
            pulse_end_target,
        )

    @kernel
    def run_baseline_kernel(self):
        self.core.reset()
        self._setup_io()

        for _ in range(self.repetitions_i):
            click_time = self._get_click_time()
            if click_time < 0:
                self._record_timeout(0)
                self.core.break_realtime()
                continue

            if self.branch_index == 0:
                self._baseline_spcm0_path(click_time)
            else:
                self._baseline_spcm1_path(click_time)

            self.core.break_realtime()

    @kernel
    def run_optimized_kernel(self):
        self.core.reset()
        self._setup_io()

        for _ in range(self.repetitions_i):
            click_time = self._get_click_time()
            if click_time < 0:
                self._record_timeout(1)
                self.core.break_realtime()
                continue

            self._schedule_optimized_common(click_time)
            self.core.break_realtime()

    def run(self):
        print("=== Photon Hot Path Timing Harness ===")
        print("layout:", self.layout_name)
        print("outputs:", ", ".join(self.output_names))
        print("inputs:", ", ".join(self.input_names))
        print("mode:", self.mode)
        print("variant:", self.variant)
        print("branch:", self.spcm_channel)

        if self.variant_code in (0, 1):
            self.run_baseline_kernel()
        if self.variant_code in (0, 2):
            self.run_optimized_kernel()

        self._publish_results()

    def _publish_results(self):
        print("")
        print("=== Timing Summary (mu) ===")

        for key in ("baseline", "optimized"):
            sample_count = len(self.samples[key])
            if sample_count == 0:
                print(f"{key}: no samples (timeouts={self.timeouts[key]})")
                continue

            click = np.array([s["click_time"] for s in self.samples[key]], dtype=np.int64)
            branch_start = np.array(
                [s["branch_start"] for s in self.samples[key]], dtype=np.int64
            )
            schedule_done = np.array(
                [s["schedule_done"] for s in self.samples[key]], dtype=np.int64
            )
            wall_before = np.array(
                [s["wall_before"] for s in self.samples[key]], dtype=np.int64
            )
            slack_before = np.array(
                [s["slack_before"] for s in self.samples[key]], dtype=np.int64
            )
            slack_after = np.array(
                [s["slack_after"] for s in self.samples[key]], dtype=np.int64
            )
            mw_on = np.array(
                [s["mw_on_target"] for s in self.samples[key]], dtype=np.int64
            )
            mw_off = np.array(
                [s["mw_off_target"] for s in self.samples[key]], dtype=np.int64
            )
            dds_mw = np.array(
                [s["dds_mw_target"] for s in self.samples[key]], dtype=np.int64
            )
            dds_rf = np.array(
                [s["dds_rf_target"] for s in self.samples[key]], dtype=np.int64
            )
            pulse_start = np.array(
                [s["pulse_start_target"] for s in self.samples[key]], dtype=np.int64
            )
            pulse_end = np.array(
                [s["pulse_end_target"] for s in self.samples[key]], dtype=np.int64
            )

            branch_entry_after_click = branch_start - click
            click_to_mw_on = mw_on - click
            click_to_mw_off = mw_off - click
            click_to_dds_mw = self._delta_or_minus_one(dds_mw, click)
            click_to_dds_rf = self._delta_or_minus_one(dds_rf, click)
            click_to_rf_mw_start = self._delta_or_minus_one(pulse_start, click)
            click_to_rf_mw_end = self._delta_or_minus_one(pulse_end, click)
            schedule_cost = schedule_done - branch_start
            margin_to_first_event = mw_on - branch_start
            wall_margin_to_first_event = mw_on - wall_before
            wall_margin_to_pulse_start = self._delta_or_minus_one(pulse_start, wall_before)

            prefix = f"hotpath/{key}"
            self.set_dataset(f"{prefix}/branch_entry_after_click_mu", branch_entry_after_click, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/click_to_mw_on_mu", click_to_mw_on, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/click_to_mw_off_mu", click_to_mw_off, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/click_to_dds_mw_set_mu", click_to_dds_mw, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/click_to_dds_rf_set_mu", click_to_dds_rf, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/click_to_rf_mw_start_mu", click_to_rf_mw_start, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/click_to_rf_mw_end_mu", click_to_rf_mw_end, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/schedule_cost_mu", schedule_cost, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/margin_to_first_event_mu", margin_to_first_event, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/wall_margin_to_first_event_mu", wall_margin_to_first_event, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/wall_margin_to_pulse_start_mu", wall_margin_to_pulse_start, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/slack_before_mu", slack_before, broadcast=True, archive=True)
            self.set_dataset(f"{prefix}/slack_after_mu", slack_after, broadcast=True, archive=True)

            print(f"{key}: samples={sample_count}, timeouts={self.timeouts[key]}")
            print(
                "  click->MW on mean/min: {} / {}".format(
                    int(np.mean(click_to_mw_on)), int(np.min(click_to_mw_on))
                )
            )
            print(
                "  click->DDS RF set mean/min: {} / {}".format(
                    self._mean_or_minus_one(click_to_dds_rf),
                    self._min_or_minus_one(click_to_dds_rf),
                )
            )
            print(
                "  click->RF+MW start mean/min: {} / {}".format(
                    self._mean_or_minus_one(click_to_rf_mw_start),
                    self._min_or_minus_one(click_to_rf_mw_start),
                )
            )
            print(
                "  schedule cost mean/max: {} / {}".format(
                    int(np.mean(schedule_cost)), int(np.max(schedule_cost))
                )
            )
            print(
                "  wall margin to first event mean/min: {} / {}".format(
                    int(np.mean(wall_margin_to_first_event)),
                    int(np.min(wall_margin_to_first_event)),
                )
            )
            print(
                "  wall margin to RF+MW start mean/min: {} / {}".format(
                    self._mean_or_minus_one(wall_margin_to_pulse_start),
                    self._min_or_minus_one(wall_margin_to_pulse_start),
                )
            )
            print(
                "  slack before/after min: {} / {}".format(
                    int(np.min(slack_before)), int(np.min(slack_after))
                )
            )

        if self.samples["baseline"] and self.samples["optimized"]:
            base = np.array(
                [
                    s["schedule_done"] - s["branch_start"]
                    for s in self.samples["baseline"]
                ],
                dtype=np.int64,
            )
            opt = np.array(
                [
                    s["schedule_done"] - s["branch_start"]
                    for s in self.samples["optimized"]
                ],
                dtype=np.int64,
            )
            print("")
            print("=== Baseline vs Optimized ===")
            print(
                "schedule cost delta mean/max: {} / {}".format(
                    int(np.mean(base) - np.mean(opt)),
                    int(np.max(base) - np.max(opt)),
                )
            )

    @staticmethod
    def _delta_or_minus_one(target, origin):
        return np.where(target >= 0, target - origin, -1)

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


class PhotonHotpathTimingSynthetic(PhotonHotpathTimingHarness):
    DEFAULT_MODE = "synthetic"


class PhotonHotpathTimingLoopbackSPCM0(PhotonHotpathTimingHarness):
    DEFAULT_MODE = "ttl_loopback"
    DEFAULT_SPCM_CHANNEL = "SPCM0"


class PhotonHotpathTimingLoopbackSPCM1(PhotonHotpathTimingHarness):
    DEFAULT_MODE = "ttl_loopback"
    DEFAULT_SPCM_CHANNEL = "SPCM1"
