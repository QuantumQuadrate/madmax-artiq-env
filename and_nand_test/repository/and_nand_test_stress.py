"""Repeated loopback run for timeout/success counting."""

from artiq.experiment import *


class AndNandTestStress(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("and_nand")
        self.setattr_argument("repetitions", NumberValue(default=1000, min=1, step=1, ndecimals=0))
        self.setattr_argument("run_length_us", NumberValue(default=20.0, unit="us"))

    @kernel
    def run(self):
        self.core.reset()
        self.and_nand.configure(True, 0b11, 0, 0)
        self.and_nand.set_run_length_mu(self.core.seconds_to_mu(self.run_length_us * 1e-6))
        self.and_nand.set_timer_div(2)
        successes = 0
        timeouts = 0
        for _ in range(int(self.repetitions)):
            self.and_nand.clear()
            _, status = self.and_nand.start()
            if status & 0b100:
                successes += 1
            if status & 0b1000:
                timeouts += 1
        print("successes", successes, "timeouts", timeouts)
