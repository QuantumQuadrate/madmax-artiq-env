"""Sweep the two-bit timer divider and read loopback timing deltas."""

from artiq.experiment import *


class AndNandTestTimingScan(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("and_nand")
        self.setattr_argument("first_div", NumberValue(default=1, min=1, step=1, ndecimals=0))
        self.setattr_argument("last_div", NumberValue(default=16, min=1, step=1, ndecimals=0))
        self.setattr_argument("run_length_us", NumberValue(default=50.0, unit="us"))

    @kernel
    def run(self):
        self.core.reset()
        self.and_nand.configure(True, 0b11, 0, 0)
        self.and_nand.set_run_length_mu(self.core.seconds_to_mu(self.run_length_us * 1e-6))
        div = int(self.first_div)
        while div <= int(self.last_div):
            self.and_nand.clear()
            self.and_nand.set_timer_div(div)
            _, status = self.and_nand.start()
            print(
                "div",
                div,
                "status",
                status,
                "diff0",
                self.and_nand.get_difference_mu(0),
                "diff1",
                self.and_nand.get_difference_mu(1),
            )
            div += 1
