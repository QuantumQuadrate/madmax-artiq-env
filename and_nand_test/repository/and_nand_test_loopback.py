"""Loopback check for timer outputs wired to timestamp inputs."""

from artiq.experiment import *


class AndNandTestLoopback(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("and_nand")
        self.setattr_argument("run_length_us", NumberValue(default=20.0, unit="us"))
        self.setattr_argument("timer_div", NumberValue(default=4, min=1, step=1, ndecimals=0))

    @kernel
    def run(self):
        self.core.reset()
        self.and_nand.clear()
        self.and_nand.configure(True, 0b11, 0, 0)
        self.and_nand.set_run_length_mu(self.core.seconds_to_mu(self.run_length_us * 1e-6))
        self.and_nand.set_timer_div(int(self.timer_div))
        _, status = self.and_nand.start()
        print(
            "status",
            status,
            "timer_ts",
            self.and_nand.get_timer_timestamp_mu(0),
            self.and_nand.get_timer_timestamp_mu(1),
            "input_ts",
            self.and_nand.get_input_timestamp_mu(0),
            self.and_nand.get_input_timestamp_mu(1),
            "diff",
            self.and_nand.get_difference_mu(0),
            self.and_nand.get_difference_mu(1),
        )
