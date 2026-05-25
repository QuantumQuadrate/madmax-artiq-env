"""Normal TTL loopback check for the DIO0 overlay card.

Expected wiring:

* ttl4 -> ttl0
* ttl5 -> ttl1
* ttl6 -> ttl2
* ttl7 -> ttl3
"""

from artiq.experiment import *


class AtomPhotonParity6TTLLoopbackCheck(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("entangler")
        for index in range(8):
            self.setattr_device(f"ttl{index}")

    @kernel
    def _check_one(self, input_index: TInt32, output_index: TInt32) -> TInt32:
        if input_index == 0:
            inp = self.ttl0
        elif input_index == 1:
            inp = self.ttl1
        elif input_index == 2:
            inp = self.ttl2
        else:
            inp = self.ttl3

        if output_index == 4:
            out = self.ttl4
        elif output_index == 5:
            out = self.ttl5
        elif output_index == 6:
            out = self.ttl6
        else:
            out = self.ttl7

        inp.input()
        out.output()
        out.off()
        self.core.break_realtime()

        with parallel:
            gate_end = inp.gate_rising(100 * us)
            with sequential:
                delay(10 * us)
                out.pulse(10 * us)

        self.core.break_realtime()
        return inp.count(gate_end)

    @kernel
    def run(self):
        self.core.reset()
        self.entangler.configure(0)

        count0 = self._check_one(0, 4)
        self.core.break_realtime()
        count1 = self._check_one(1, 5)
        self.core.break_realtime()
        count2 = self._check_one(2, 6)
        self.core.break_realtime()
        count3 = self._check_one(3, 7)

        print("ttl4_to_ttl0_count", count0)
        print("ttl5_to_ttl1_count", count1)
        print("ttl6_to_ttl2_count", count2)
        print("ttl7_to_ttl3_count", count3)
