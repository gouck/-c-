"""
样本: 200 IPv4 报文 → 相同输出合并 → 仅显示不同输出行
"""
import sys, os, random
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))
from dut_wrapper import SwitchDUT
from ref_model import SwitchRefModel
from coverage import FunctionalCoverage

dut = SwitchDUT('./libswitch_dut.so')
ref = SwitchRefModel()
cov = FunctionalCoverage()

records = []
for _ in range(200):
    dut.init(); ref._init_tables()
    aft = random.randint(0,3); dut.set_aft(0, aft); ref.ds_port[0]['aft'] = aft
    tagged = random.choice([True,False])
    d = random.choice(['ucast','bcast','mcast'])
    if d=='bcast':
        dmac = [0xFF]*6
    elif d=='mcast':
        dmac = [0x01]+[random.randint(0,255) for _ in range(5)]
    else:
        dmac = [random.randint(0,255) for _ in range(6)]
    smac = [random.randint(0,255) for _ in range(6)]
    pkt = bytearray(64)
    for i,b in enumerate(dmac): pkt[i]=b
    for i,b in enumerate(smac): pkt[6+i]=b
    off=12
    if tagged: pkt[12]=0x81;pkt[13]=0x00;pkt[14]=0x00;pkt[15]=0x64;off=16
    pkt[off]=0x08;pkt[off+1]=0x00;pkt[off+2]=0x45
    dut.process(bytes(pkt),0); ref.process(bytes(pkt),0)
    s = dut.snapshot()
    r = ref.process(bytes(pkt),0)
    ok = all(s.get(f,-999)==r.get(f,-999) for f in
        ['prIsIpv4','prIsArp','prVlanId','prExistVlan','giTpid',
         'piPortVid','piAft','piDiscard','piBrgHit','piFlooding','enq_cnt'])
    records.append({
        'aft':aft,'tagged':s['giVlanTagged'],'dm':d,
        'discard':s['piDiscard'],'enq':s['enq_cnt'],
        'bcast':s['piBcast'],'brgHit':s['piBrgHit'],
        'flooding':s['piFlooding'],'lrnNew':s['giLrnNew'],'ok':ok
    })
    cov.sample(s)

# ── 合并相同输出 ──
groups = Counter()
for r in records:
    key = (r['aft'], r['tagged'], r['dm'], r['discard'], r['enq'])
    groups[key] += 1

total_ok = sum(1 for r in records if r['ok'])

print("="*100)
print("  [样本] 200 个随机 IPv4 报文 → 合并相同输出 → 仅 12 行")
print("="*100)
print()

# ── 方式1: 波形追踪 (合并版) ──
print("─── 波形追踪 (合并版) ───")
print(f"  {'cnt':>5s} {'aft':>3s} {'tagged':>6s} {'dm':>6s} {'disc':>4s} {'bcast':>5s} {'brgHit':>6s} {'flood':>5s} {'enq':>3s}  {'说明'}")
print(f"  {'─'*5} {'─'*3} {'─'*6} {'─'*6} {'─'*4} {'─'*5} {'─'*6} {'─'*5} {'─'*3}  {'─'*30}")
for (aft,tagged,dm,disc,enq), cnt in sorted(groups.items()):
    rep = next(r for r in records if (r['aft'],r['tagged'],r['dm'],r['discard'],r['enq'])==(aft,tagged,dm,disc,enq))
    desc = ""
    if enq==8 and disc==0 and not rep['bcast']: desc = "泛洪 8 端口(未知单播)"
    elif enq==8 and rep['bcast']: desc = "广播 flooding"
    elif enq==0 and disc==1 and aft in (1,3): desc = f"AFT={aft} 丢弃"
    elif enq==0 and disc==1 and tagged and aft==2: desc = "AFT=2 丢弃 tagged"
    elif enq>0 and enq<8 and rep['brgHit']: desc = "MAC 命中转发"
    print(f"  {cnt:5d} {aft:3d} {tagged:6d} {dm:6s} {disc:4d} {rep['bcast']:5d} {rep['brgHit']:6d} {rep['flooding']:5d} {enq:3d}  {desc}")

print(f"\n  200 条合并为 {len(groups)} 条不同输出 · Scoreboard {total_ok}/200 OK")
print()

# ── 覆盖率报告 ──
print("─── 覆盖率报告 ───")
cov.report()

print()
print(f"  未覆盖分析: 200 个 IPv4 报文无法覆盖 IPv6/ARP/Loop 等 bins")
