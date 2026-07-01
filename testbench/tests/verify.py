"""
8m 交换芯片自动化覆盖率驱动测试框架 v2.0

输入: 5种报文 × N个随机包
输出: Scoreboard(终端+HTML) + Coverage(终端+HTML+JSON) + 波形追踪合并版(终端+HTML)

用法:
  python tests/verify.py                     # 每种 100 个, 共 500
  python tests/verify.py --count 200         # 每种 200 个, 共 1000
"""

import sys, os, random, json
from collections import Counter
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from dut_wrapper import SwitchDUT
from ref_model import SwitchRefModel
from coverage import FunctionalCoverage

PER_TYPE = 100
FIELDS = [
    'prIsIpv4','prIsIpv6','prIsArp','prIsLoopDetection',
    'prVlanId','prExistVlan','prIpDscp','giTpid',
    'piPortVid','piAft','piDiscard',
    'giVlanHit','giVlanTagged',
    'piBcast','piMcast','piBrgHit','piFlooding','piFwdBmp',
    'giLrnHit','giLrnNew','giLruLrn','piLrnDisable',
    'piPrior','enq_cnt',
]

PKT_TYPES = {
    'IPv4':    0x0800,
    'IPv6':    0x86DD,
    'ARP':     0x0806,
    'Loop':    0x8899,
    'Unknown': 0x1234,
}

TRACE_VARS = ['piAft','giVlanTagged','piDiscard','piBcast','piMcast','piBrgHit','piFlooding','piFwdBmp','enq_cnt']


# ================================================================
# 报文生成
# ================================================================

def _mac_bytes(hex_str=None):
    if hex_str: return list(bytes.fromhex(hex_str.replace(':', '')))
    return [random.randint(0, 255) for _ in range(6)]

def make_pkt(dmac=None, smac=None, tagged=False, vid=100, etype=0x0800):
    pkt = bytearray(64)
    dmac = _mac_bytes(dmac) if isinstance(dmac, str) else (dmac or _mac_bytes())
    smac = _mac_bytes(smac) if isinstance(smac, str) else (smac or _mac_bytes())
    for i, b in enumerate(dmac): pkt[i] = b
    for i, b in enumerate(smac): pkt[6+i] = b
    off = 12
    if tagged:
        pkt[12]=0x81; pkt[13]=0x00; pkt[14]=(vid>>8)&0xFF; pkt[15]=vid&0xFF; off=16
    pkt[off]=(etype>>8)&0xFF; pkt[off+1]=etype&0xFF
    if etype==0x0800: pkt[off+2]=0x45
    elif etype==0x8899: pkt[off+3]=random.randint(1,15)
    return bytes(pkt)

def gen_packets(etype: int, count: int):
    for _ in range(count):
        tagged = random.choice([True, False])
        d = random.choice(['ucast','bcast','mcast','rma'])
        if d=='bcast':   dmac = [0xFF]*6
        elif d=='mcast': dmac = [0x01]+[random.randint(0,255) for _ in range(5)]
        elif d=='rma':   dmac = [0x01,0x80,0xC2,0x00,0x00,random.randint(0,255)]
        else:            dmac = _mac_bytes()
        smac = _mac_bytes()
        vid = random.choice([100, 200])
        yield make_pkt(dmac=dmac, smac=smac, tagged=tagged, vid=vid, etype=etype)


# ================================================================
# 主流程
# ================================================================

def main():
    global PER_TYPE
    if '--count' in sys.argv:
        i = sys.argv.index('--count')
        if i+1 < len(sys.argv): PER_TYPE = int(sys.argv[i+1])

    dut = SwitchDUT('./libswitch_dut.so')
    ref = SwitchRefModel()
    cov = FunctionalCoverage()

    stats = {name: {'ok': 0, 'ng': 0, 'first_ng': None} for name in PKT_TYPES}
    total_ok = total_ng = total_pkts = 0
    all_records = []  # for merged trace

    total = PER_TYPE * len(PKT_TYPES)
    print(f"{'='*70}")
    print(f"  8m Switch - Automated Coverage-Driven Test v2.0")
    print(f"  Packets: {PER_TYPE}/type × {len(PKT_TYPES)} types = {total}")
    print(f"{'='*70}")

    for type_name, etype in PKT_TYPES.items():
        st = stats[type_name]
        print(f"\n  [{type_name}] EtherType=0x{etype:04X}  ({PER_TYPE} packets)")

        for pkt in gen_packets(etype, PER_TYPE):
            total_pkts += 1

            # ============================================================
            # 第1步: 初始化硬件 & 参考模型（复位所有表项）
            # ============================================================
            dut.init(); ref._init_tables()

            # ============================================================
            # 第2步: 造包（gen_packets 已随机化 DMAC/SMAC/VLAN/EtherType）
            # ============================================================
            # pkt 已在上方 gen_packets() 中生成完毕

            # ============================================================
            # 第3步: 配置寄存器（随机化 DsPort 配置）
            # ============================================================
            aft = random.randint(0, 3)           # AFT: 0=学习 1=untagged 2=tagged 3=全部
            stp_state = random.choice([4])       # STP: 4=转发（可扩展 0..7）
            max_mac = random.choice([0, 255])    # 端口安全: 0=不限 255=最大
            dut.set_aft(0, aft);                ref.ds_port[0]['aft'] = aft
            dut.set_stp_state(0, stp_state);    ref.ds_port[0]['stpState'] = stp_state
            dut.set_max_mac(0, max_mac);        ref.ds_port[0]['maxMacNum'] = max_mac

            # ============================================================
            # 第4步: 送包 → DUT 硬件 & 参考模型 各处理一遍
            # ============================================================
            dut.process(pkt, 0)
            r = ref.process(pkt, 0)

            # ============================================================
            # 第5步: 采样（抓取 DUT 全部内部状态 + 全部寄存器值）
            # ============================================================
            s = dut.snapshot()

            # ============================================================
            # 第6步: 比对（DUT vs 参考模型，逐字段检查）
            # ============================================================
            ok = True
            bad_field = None
            for f in FIELDS:
                if s.get(f, -999) != r.get(f, -999):
                    ok = False; bad_field = f; break

            if ok: st['ok'] += 1
            else:
                st['ng'] += 1
                if st['first_ng'] is None:
                    st['first_ng'] = (total_pkts, bad_field, s.get(bad_field, '?'), r.get(bad_field, '?'))

            # ============================================================
            # 第7步: 覆盖率收集（全部寄存器字段自动入库）
            # ============================================================
            cov.sample(s)
            all_records.append({'snap': s, 'pkt_hex': pkt[:20].hex(), 'type': type_name})

        sub = st['ok'] + st['ng']
        pct = 100 * st['ok'] // sub if sub else 0
        bar = 'OK' if st['ng']==0 else 'NG'
        print(f"  {type_name}: {st['ok']}/{sub} {bar} ({pct}%)")

    total_ok = sum(s['ok'] for s in stats.values())
    total_ng = sum(s['ng'] for s in stats.values())

    # ── 输出1: Scoreboard ──
    print(f"\n{'='*70}")
    print(f"  SCOREBOARD SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Type':10s} {'Packets':>8s} {'OK':>8s} {'NG':>8s} {'Rate':>8s}")
    print(f"  {'─'*10} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
    for name in PKT_TYPES:
        st = stats[name]; sub = st['ok']+st['ng']
        rate = f"{100*st['ok']//sub}%" if sub else '-'
        print(f"  {name:10s} {sub:8d} {st['ok']:8d} {st['ng']:8d} {rate:>8s}")
    print(f"  {'─'*10} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
    print(f"  {'TOTAL':10s} {total_pkts:8d} {total_ok:8d} {total_ng:8d} {100*total_ok//total_pkts if total_pkts else 0:7d}%")

    # ── 输出2: 覆盖率 ──
    cov.report()

    # ── 输出3: 波形追踪合并版 ──
    print(f"\n{'='*70}")
    print(f"  WAVEFORM TRACE (merged, with sample packets)")
    print(f"{'='*70}")
    groups = Counter()
    sample_pkts = {}
    for r in all_records:
        s = r['snap']
        key = (s.get('piAft',0), s.get('giVlanTagged',0),
               s.get('piDiscard',0), s.get('piBcast',0),
               s.get('piMcast',0), s.get('piBrgHit',0),
               s.get('piFlooding',0), s.get('enq_cnt',0))
        groups[key] += 1
        if key not in sample_pkts:
            sample_pkts[key] = r

    trace_headers = ['cnt','aft','tag','disc','bcast','mcast','brgHit','flood','enq','type']
    trace_rows = []
    hdr = f"  {'cnt':>5s} {'aft':>3s} {'tag':>3s} {'disc':>4s} {'bcast':>5s} {'mcast':>5s} {'brgHit':>6s} {'flood':>5s} {'enq':>3s}  sample_pkt(hex)"
    print(hdr)
    print(f"  {'─'*5} {'─'*3} {'─'*3} {'─'*4} {'─'*5} {'─'*5} {'─'*6} {'─'*5} {'─'*3}  {'─'*30}")
    for key, cnt in sorted(groups.items(), key=lambda x: -x[1]):
        aft, tag, disc, bcast, mcast, brg, flood, enq = key
        hex_pkt = sample_pkts[key].get('pkt_hex', '?')[:40]
        type_name = sample_pkts[key].get('type', '?')
        print(f"  {cnt:5d} {aft:3d} {tag:3d} {disc:4d} {bcast:5d} {mcast:5d} {brg:6d} {flood:5d} {enq:3d}  {hex_pkt}  ({type_name})")
        trace_rows.append({'vals': [cnt, aft, tag, disc, bcast, mcast, brg, flood, enq, type_name],
                           'hex': hex_pkt})
    print(f"\n  {total_pkts} packets → {len(groups)} unique output patterns")

    # ── 输出4: JSON ──
    json_path = "coverage_report.json"
    cov.to_json(json_path)
    print(f"\n  JSON report: {json_path}")

    # ── 输出5: HTML ──
    sb_data = {
        'total': total_pkts, 'ok': total_ok, 'ng': total_ng,
        'types': [{'name': n, 'pkts': stats[n]['ok']+stats[n]['ng'],
                    'ok': stats[n]['ok'], 'ng': stats[n]['ng'],
                    'rate': 100*stats[n]['ok']//(stats[n]['ok']+stats[n]['ng']) if (stats[n]['ok']+stats[n]['ng']) else 0}
                  for n in PKT_TYPES]
    }
    trace_data = {
        'headers': trace_headers,
        'rows': trace_rows,
        'total': total_pkts,
        'unique': len(groups),
    }
    html_path = cov.to_html("coverage_report.html",
                            title=f"8m Switch Coverage Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                            stats=sb_data,
                            trace_data=trace_data)
    print(f"  HTML report: {html_path}  (open in browser)")

    # ── 未覆盖 ──
    missed = []
    for cp, bins in cov.points.items():
        for bn, cnt in bins.items():
            if cnt == 0: missed.append(f"{cp}.{bn}")
    if missed:
        print(f"\n  UNCOVERED ({len(missed)}):")
        for m in missed: print(f"    - {m}")

    return 0 if total_ng == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
