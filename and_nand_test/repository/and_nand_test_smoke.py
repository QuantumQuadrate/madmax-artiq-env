"""Smoke experiment for the and_nand_test gateware mode."""

from artiq.experiment import *


class AndNandTestSmoke(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("and_nand")

    @kernel
    def run(self):
        self.core.reset()
        self.and_nand.init()
        self.and_nand.set_run_length_mu(1000 * ns)
        self.and_nand.set_timer_div(2)
        _, status = self.and_nand.start()
        diff0 = self.and_nand.get_difference_mu(0)
        diff1 = self.and_nand.get_difference_mu(1)
        print("and_nand_test status", status, "diffs", diff0, diff1)
