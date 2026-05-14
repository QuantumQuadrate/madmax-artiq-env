# Runtime device database fragment for and_nand_test.
# Replace the channel numbers with the generated values from the matching bitstream.

device_db = {
    "core": {
        "type": "local",
        "module": "artiq.coredevice.core",
        "class": "Core",
        "arguments": {"host": "192.168.1.75", "ref_period": 1e-9},
    },
    "and_nand": {
        "type": "local",
        "module": "entangler.and_nand_test_driver",
        "class": "AndNandTestEntangler",
        "arguments": {"channel": 0},
    },
}
