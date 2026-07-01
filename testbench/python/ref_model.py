"""
ref_model.py — Python 黄金参考模型

等价于 UVM Scoreboard 中的 Reference Model。
逻辑必须与 source/text4/switchX.c 完全一致。

用法:
    from ref_model import SwitchRefModel
    ref = SwitchRefModel()
    result = ref.process(pkt_bytes, src_port=0)
    assert result["piDiscard"] == dut.snapshot()["piDiscard"]
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class MacEntry:
    fid: int
    mac: int       # 48-bit MAC address
    destMap: int   # 10-bit port bitmap
    port: int      # source port
    destDiscard: int = 0
    prior: int = 0


class SwitchRefModel:
    """Python 实现的完整 parser → switchX → egress 流水线"""

    def __init__(self):
        self._init_tables()

    def _init_tables(self):
        """等价于 _init_all_tables()"""
        self.ds_port = []
        for i in range(8):
            self.ds_port.append({
                "portVid": 100 + i, "aft": 0, "lrnDisable": 0,
                "allowBrg2Src": 1, "rmaMode": 0, "mirrorEn": 0,
                "stpState": 0, "maxMacNum": 0, "prior": 0,
                "strictPvid": 0, "dot1qBasedVlan": 0,
            })
        self.ds_vlan = []
        for i in range(16):
            self.ds_vlan.append({
                "vlanBmp": 0xFF, "fid": 100 + i, "untagFlag": 0xFF,
                "egressFilter": 0, "mirrorEn": 0, "dot1qPriorEn": 0,
                "leakyUcast": 0, "leakyMcast": 0, "leakyBcast": 0,
                "leakyArp": 0, "leakyMirror": 0,
            })
        self.vlan_cam = [100 + i for i in range(16)]
        self.mac_table: List[MacEntry] = []
        self.ds_acl = []  # list of {action, etherType, ...}
        self.sys_learn_num = 0

        # registers
        self.prior_assign = {
            "ipDscpEn": 0, "ipAddrEn": 0, "macDaEn": 0, "rldpEn": 0,
            "portWeight": 0, "vlanWeight": 0, "dscpWeight": 0,
            "rldpPrior": 0,
        }

    def process(self, pkt: bytes, src_port: int) -> dict:
        """完整流水线，返回与 DUT snapshot() 相同结构的 dict"""
        # === Parser ===
        parsed = self._parser(pkt)
        if parsed is None:
            return self._discard_result()

        # === SwitchX ===
        result = self._switchX(parsed, src_port)

        # === Egress ===
        result["enq_cnt"] = self._egress(result)
        return result

    # ================================================================
    # Parser
    # ================================================================

    def _parser(self, pkt: bytes) -> Optional[dict]:
        if len(pkt) < 14:
            return None

        dmac = int.from_bytes(pkt[0:6], 'big')
        smac = int.from_bytes(pkt[6:12], 'big')
        tpid = int.from_bytes(pkt[12:14], 'big')
        offset = 14

        vlan_id = 0
        vlan_prior = 0
        exist_vlan = 0

        if tpid in (0x8100, 0x9100, 0x88a8):
            if offset + 3 >= len(pkt):
                return None
            vlan_prior = (pkt[offset] >> 5) & 0x7
            vlan_id = ((pkt[offset] & 0x0F) << 8) | pkt[offset + 1]
            exist_vlan = 1
            tpid = int.from_bytes(pkt[offset + 2:offset + 4], 'big')
            offset += 4

        is_ipv4 = (tpid == 0x0800)
        is_ipv6 = (tpid == 0x86DD)
        is_arp = (tpid in (0x0806, 0x8035))
        is_loop = (tpid == 0x8899)

        ip_dscp = 0
        ip_sa = 0
        ip_da = 0
        loop_ttl = 0

        if is_ipv4 and offset + 20 <= len(pkt):
            ip_dscp = (pkt[offset + 1] >> 2) & 0x3F
            ip_sa = int.from_bytes(pkt[offset + 12:offset + 16], 'big')
            ip_da = int.from_bytes(pkt[offset + 16:offset + 20], 'big')
        elif is_ipv6 and offset + 40 <= len(pkt):
            ip_dscp = ((pkt[offset] & 0x0F) << 2) | ((pkt[offset + 1] >> 6) & 0x3)
        elif is_loop and offset + 4 <= len(pkt):
            loop_ttl = pkt[offset + 3] & 0x0F

        return {
            "dmac": dmac, "smac": smac, "tpid": tpid,
            "vlanId": vlan_id, "vlanPrior": vlan_prior, "existVlan": exist_vlan,
            "isIpv4": is_ipv4, "isIpv6": is_ipv6, "isArp": is_arp,
            "isLoop": is_loop,
            "ipDscp": ip_dscp, "ipSa": ip_sa, "ipDa": ip_da,
            "loopTtl": loop_ttl,
        }

    # ================================================================
    # SwitchX
    # ================================================================

    def _switchX(self, p: dict, src_port: int) -> dict:
        port = self.ds_port[src_port]

        # 1. Port config
        piPortVid    = port["portVid"]
        piAft        = port["aft"]
        piLrnDisable = port["lrnDisable"]
        piAllowBrg2Src = port["allowBrg2Src"]
        piRmaMode    = port["rmaMode"]
        piPortPrior  = port["prior"] & 0x3

        # 2. VLAN resolution
        giVid = piPortVid
        if port["dot1qBasedVlan"] and p["existVlan"] and p["vlanId"]:
            giVid = p["vlanId"]
            if port["strictPvid"] and p["vlanId"] != piPortVid:
                return self._discard_result()

        giVlanHit = 0
        giVlanIdx = 0
        for i, cam_vid in enumerate(self.vlan_cam):
            if giVid == cam_vid:
                giVlanHit = 1
                giVlanIdx = i
                break

        piDiscard = 0
        piFwdBmp = 0
        piVlanMember = 0
        piFid = 0
        piUntagFlag = 0
        piEgressFilter = 0
        piLeakyUcast = piLeakyMcast = piLeakyBcast = piLeakyArp = piLeakyMirror = 0
        piVlanPrior = 0

        if giVlanHit:
            vlan = self.ds_vlan[giVlanIdx]
            piFwdBmp    = vlan["vlanBmp"] & 0x3FF
            piVlanMember = vlan["vlanBmp"] & 0x3FF
            piFid       = vlan["fid"] & 0xFFF
            piUntagFlag = vlan["untagFlag"] & 0x3FF
            piEgressFilter = vlan["egressFilter"]
            piLeakyUcast = vlan["leakyUcast"]
            piLeakyMcast = vlan["leakyMcast"]
            piLeakyBcast = vlan["leakyBcast"]
            piLeakyArp   = vlan["leakyArp"]
            piLeakyMirror = vlan["leakyMirror"]
        else:
            piDiscard = 1

        # 3. VLAN tagged
        giVlanTagged = 1 if (p["existVlan"] and p["vlanId"]) else 0

        # 4. AFT check
        if not piDiscard:
            if piAft == 1:      # tagged only
                if not giVlanTagged:
                    piDiscard = 1
            elif piAft == 2:    # untagged only
                if giVlanTagged:
                    piDiscard = 1
            elif piAft == 3:    # discard all
                piDiscard = 1

        # 5. ACL check
        if not piDiscard:
            for acl in self.ds_acl:
                if acl["action"] == 0 and acl["etherType"] == p["tpid"]:
                    piDiscard = 1
                    break

        # 6. STP check
        if not piDiscard:
            if port["stpState"] == 1:  # Blocking
                piDiscard = 1

        # 7. MAC classification
        piBcast = 1 if p["dmac"] == 0xFFFFFFFFFFFF else 0
        piMcast = 1 if (not piBcast and ((p["dmac"] >> 40) & 1)) else 0

        piBrgHit = 0
        piFlooding = 0

        if not piDiscard:
            fid = giVid if piMcast else piFid
            for entry in self.mac_table:
                if entry.fid == fid and entry.mac == p["dmac"]:
                    piBrgHit = 1
                    if entry.destDiscard:
                        piDiscard = 1
                    else:
                        piFwdBmp = entry.destMap & 0x3FF
                    break
            if not piBrgHit:
                piFlooding = 1

        # 8. Flooding
        if piFlooding:
            piFwdBmp = piVlanMember & 0x3FF

        # 9. Learning
        giLrnHit = 0
        giLrnNew = 0
        giLruLrn = 0

        if not piLrnDisable and not piDiscard:
            fid = giVid if piMcast else piFid
            # check existing
            for entry in self.mac_table:
                if entry.fid == fid and entry.mac == p["smac"]:
                    giLrnHit = 1
                    break
            if not giLrnHit:
                # check port security
                max_mac = port["maxMacNum"]
                port_cnt = sum(1 for e in self.mac_table if e.port == src_port)
                if max_mac == 0 or port_cnt < max_mac:
                    giLrnNew = 1
                    self.mac_table.append(MacEntry(
                        fid=fid, mac=p["smac"],
                        destMap=(1 << src_port) & 0x3FF,
                        port=src_port
                    ))
                    self.sys_learn_num += 1

        # 10. Priority
        piPrior = 0
        if self.prior_assign["ipDscpEn"] and (p["isIpv4"] or p["isIpv6"]):
            pass  # DSCP priority lookup (simplified)
        # simplified: use port priority
        piPrior = piPortPrior

        # 11. Loop detection
        if p["isLoop"] and p["loopTtl"] <= 1:
            piDiscard = 1

        # 12. Source port exclusion
        if not piAllowBrg2Src:
            piFwdBmp &= ~(1 << src_port)

        # 13. Egress filter
        for i in range(8):
            if piEgressFilter and (piFwdBmp >> i) & 1 and not ((piVlanMember >> i) & 1):
                piFwdBmp &= ~(1 << i)
                # leak flags simplified: skip for now

        if piDiscard:
            piFwdBmp = 0

        return {
            # parser
            "prIsIpv4":     p["isIpv4"],
            "prIsIpv6":     p["isIpv6"],
            "prIsArp":      p["isArp"],
            "prIsLoopDetection": p["isLoop"],
            "prVlanId":     p["vlanId"],
            "prExistVlan":  p["existVlan"],
            "prIpDscp":     p["ipDscp"],
            "giTpid":       p["tpid"],
            # VLAN
            "piPortVid":    piPortVid,
            "piAft":        piAft,
            "giVlanHit":    giVlanHit,
            "giVlanTagged": giVlanTagged,
            # forwarding
            "piDiscard":    piDiscard,
            "piBcast":      piBcast,
            "piMcast":      piMcast,
            "piBrgHit":     piBrgHit,
            "piFlooding":   piFlooding,
            "piFwdBmp":     piFwdBmp,
            "piPrior":      piPrior,
            # learning
            "giLrnHit":     giLrnHit,
            "giLrnNew":     giLrnNew,
            "giLruLrn":     giLruLrn,
            "piLrnDisable": piLrnDisable,
            # enq_cnt filled by egress
            "enq_cnt":      0,
        }

    def _egress(self, r: dict) -> int:
        """计算 enqueue 次数 = piFwdBmp 中置位的 bit 数"""
        if r["piDiscard"]:
            return 0
        return bin(r["piFwdBmp"] & 0xFF).count('1')

    def _discard_result(self) -> dict:
        return {
            "prIsIpv4": 0, "prIsIpv6": 0, "prIsArp": 0, "prIsLoopDetection": 0,
            "prVlanId": 0, "prExistVlan": 0, "prIpDscp": 0, "giTpid": 0,
            "piPortVid": 0, "piAft": 0, "giVlanHit": 0, "giVlanTagged": 0,
            "piDiscard": 1, "piBcast": 0, "piMcast": 0,
            "piBrgHit": 0, "piFlooding": 0, "piFwdBmp": 0, "piPrior": 0,
            "giLrnHit": 0, "giLrnNew": 0, "giLruLrn": 0, "piLrnDisable": 0,
            "enq_cnt": 0,
        }
