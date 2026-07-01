"""简单调试脚本"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))
from dut_wrapper import SwitchDUT

dut = SwitchDUT('./libswitch_dut.so')

# 测试1: untagged
dut.init()
pkt1 = bytes([0x00,0x11,0x22,0x33,0x44,0x55, 0x00,0xaa,0xbb,0xcc,0xdd,0x01, 0x08,0x00, 0x45]+[0]*49)
dut.process(pkt1, 0)
s1 = dut.snapshot()
print(f'Test1 (untagged): prVlanId={s1["prVlanId"]} prExistVlan={s1["prExistVlan"]} giTpid={s1["giTpid"]}')

# 测试2: tagged
dut.init()
pkt2 = bytes([0x00,0x11,0x22,0x33,0x44,0x55, 0x00,0xaa,0xbb,0xcc,0xdd,0x01, 0x81,0x00, 0x00,0x64, 0x08,0x00, 0x45]+[0]*47)
dut.process(pkt2, 0)
s2 = dut.snapshot()
print(f'Test2 (tagged):   prVlanId={s2["prVlanId"]} prExistVlan={s2["prExistVlan"]} giTpid={s2["giTpid"]}')

# 测试3: untagged again
dut.init()
pkt3 = bytes([0x00,0x11,0x22,0x33,0x44,0x55, 0x00,0xaa,0xbb,0xcc,0xdd,0x01, 0x08,0x00, 0x45]+[0]*49)
dut.process(pkt3, 0)
s3 = dut.snapshot()
print(f'Test3 (untagged): prVlanId={s3["prVlanId"]} prExistVlan={s3["prExistVlan"]} giTpid={s3["giTpid"]}')
