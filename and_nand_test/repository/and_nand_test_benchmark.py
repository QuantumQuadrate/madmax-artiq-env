"""Simple gateware transaction benchmark for and_nand_test."""

from artiq.experiment import *


class AndNandTestBenchmark(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("and_nand")
        self.setattr_argument("repetitions", NumberValue(default=10000, min=1, step=1, ndecimals=0))

    @kernel
    def run(self):
        self.core.reset()
        self.and_nand.configure(True, 0b11, 0, 0)
        self.and_nand.set_run_length_mu(1000 * ns)
        self.and_nand.set_timer_div(2)
        t0 = now_mu()
        for _ in range(int(self.repetitions)):
            self.and_nand.clear()
            self.and_nand.start()
        t1 = now_mu()
        print("benchmark_mu_per_run", (t1 - t0) // int(self.repetitions))
