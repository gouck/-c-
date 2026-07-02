"""
dut_wrapper.py — Python ctypes 封装

将编译好的 C 动态库暴露为 Python 类，供测试用例调用。

使用:
    from dut_wrapper import SwitchDUT
    dut = SwitchDUT("./output/009/c_project/libswitch_dut.so")
    dut.init()
    dut.process(pkt_bytes, src_port=0)
    snap = dut.snapshot()
"""

import ctypes
import os


class SwitchDUT:
    """8m 交换芯片 DUT 的 Python 封装"""

    def __init__(self, lib_path: str = None):
        """
        Args:
            lib_path: libswitch_dut.so 路径。
                      默认自动搜索: ./output/*/c_project/libswitch_dut.so
        """
        if lib_path is None:
            lib_path = self._find_lib()
        self._lib = ctypes.CDLL(lib_path)
        self._setup_signatures()

    @staticmethod
    def _find_lib() -> str:
        """自动查找最新的 c_project 共享库"""
        # 先在当前目录和上级目录找
        candidates = [
            "./libswitch_dut.so",
            "./libswitch_dut.dll",
        ]
        # 搜索 output/*/c_project/
        import glob
        for pattern in ["output/*/c_project/libswitch_dut.*", "../output/*/c_project/libswitch_dut.*"]:
            matches = glob.glob(pattern)
            if matches:
                return matches[-1]  # 取最新的
        for c in candidates:
            if os.path.exists(c):
                return c
        raise FileNotFoundError(
            "找不到 libswitch_dut.so。请先编译: make lib"
        )

    def _setup_signatures(self):
        """设置所有 C 函数的参数类型和返回类型"""
        L = self._lib

        # -- 初始化和控制 --
        L.switch_init.argtypes = []
        L.switch_init.restype = None

        L.switch_process_packet.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_int, ctypes.c_int
        ]
        L.switch_process_packet.restype = None

        # -- 通用 getter --
        L.switch_enqueue_count.argtypes = []
        L.switch_enqueue_count.restype = ctypes.c_int

        L.switch_is_discarded.argtypes = []
        L.switch_is_discarded.restype = ctypes.c_int

        # -- parser 输出 --
        for name in ["prIsIpv4", "prIsIpv6", "prIsArp", "prIsLoopDetection",
                      "prVlanId", "prExistVlan", "prIpDscp", "giTpid"]:
            func = getattr(L, f"switch_{name}")
            func.argtypes = []
            func.restype = ctypes.c_int

        # -- VLAN / 转发 --
        for name in ["piPortVid", "piAft", "piDiscard", "giVlanHit",
                      "giVlanTagged", "piBcast", "piMcast", "piBrgHit",
                      "piFlooding", "piFwdBmp", "piPrior",
                      "giLrnHit", "giLrnNew", "giLruLrn", "piLrnDisable"]:
            func = getattr(L, f"switch_{name}")
            func.argtypes = []
            func.restype = ctypes.c_int

        # -- 统计 --
        for name in ["port_rx_packets", "port_tx_packets", "port_drop_packets"]:
            func = getattr(L, f"switch_{name}")
            func.argtypes = [ctypes.c_int]
            func.restype = ctypes.c_uint64

        # -- 配置 setter --
        for name in ["set_port_aft", "set_port_stp", "set_port_max_mac", "set_port_vid"]:
            func = getattr(L, f"switch_{name}")
            func.argtypes = [ctypes.c_int, ctypes.c_int]
            func.restype = None
        L.switch_set_acl_entry.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        L.switch_set_acl_entry.restype = None

        # -- 新增 setter（全部寄存器字段） --
        _reg_setters_int = {
            "set_DsPort_dot1qBasedVlan", "set_DsPort_keepVlanTag",
            "set_DsPort_allowBrg2Src", "set_DsPort_lrnDisable",
            "set_DsPort_rmaMode", "set_DsPort_mirrorEn",
            "set_DsPort_updateMacSa", "set_DsPort_strictPvid", "set_DsPort_prior",
            "set_DsVlan_fid", "set_DsVlan_vlanBmp", "set_DsVlan_untagFlag",
            "set_DsVlan_leakyUcast", "set_DsVlan_leakyMcast", "set_DsVlan_leakyBcast",
            "set_DsVlan_leakyArp", "set_DsVlan_leakyMirror",
            "set_DsVlan_egressFilter", "set_DsVlan_dot1qPriorEn",
            "set_DsVlan_mirrorEn", "set_DsVlan_prior",
            "set_DsAcl_vlanId", "set_DsAcl_srcMacHi", "set_DsAcl_srcMacLo",
            "set_Ds1qPriorMap_prior", "set_DsDscpPriorMap_prior",
        }
        for name in _reg_setters_int:
            func = getattr(L, f"switch_{name}")
            func.argtypes = [ctypes.c_int, ctypes.c_int]
            func.restype = None
        L.switch_set_VlanIdCamCtl_vlanId.argtypes = [ctypes.c_int, ctypes.c_int]
        L.switch_set_VlanIdCamCtl_vlanId.restype = None

        # -- 单例 setter --
        _reg_setters_void = {
            "set_L2AgingCtl_agingEn", "set_L2AgingCtl_fastAgingAll",
            "set_L2LearnCtl_lruEn", "set_LoopDetectCtl_en",
            "set_MirrorCtl_srcMirrorPort", "set_StormCfgCtl_enable",
        }
        for name in _reg_setters_void:
            func = getattr(L, f"switch_{name}")
            func.argtypes = [ctypes.c_int]
            func.restype = None

        # -- parser reset --
        L.switch_reset_parser_globals.argtypes = []
        L.switch_reset_parser_globals.restype = None

        # -- 寄存器字段 getter（全覆盖，数组型带 index 参数） --
        _reg_getters_int = {
            # DsPort_mem[port]
            "DsPort_portVid", "DsPort_dot1qBasedVlan", "DsPort_aft",
            "DsPort_keepVlanTag", "DsPort_portMacHi", "DsPort_portMacLo",
            "DsPort_stpState", "DsPort_maxMacNum", "DsPort_allowBrg2Src",
            "DsPort_lrnDisable", "DsPort_prior", "DsPort_rmaMode",
            "DsPort_mirrorEn", "DsPort_updateMacSa", "DsPort_strictPvid",
            # DsVlan_mem[idx]
            "DsVlan_fid", "DsVlan_vlanBmp", "DsVlan_untagFlag",
            "DsVlan_leakyUcast", "DsVlan_leakyMcast", "DsVlan_leakyBcast",
            "DsVlan_leakyArp", "DsVlan_leakyMirror", "DsVlan_egressFilter",
            "DsVlan_dot1qPriorEn", "DsVlan_mirrorEn", "DsVlan_prior",
            # DsMac_mem[idx]
            "DsMac_destMap", "DsMac_destDiscard", "DsMac_isMcast", "DsMac_prior",
            # DsMacAging_mem[idx]
            "DsMacAging_aging0", "DsMacAging_aging1", "DsMacAging_aging2", "DsMacAging_aging3",
            # DsMacKey_mem[idx]
            "DsMacKey_fid", "DsMacKey_macAddrHi", "DsMacKey_macAddrLo",
            # DsMacStatic_mem[idx]
            "DsMacStatic_static",
            # DsMacValid_mem[idx]
            "DsMacValid_valid",
            # DsStormCtrl_mem[idx]
            "DsStormCtrl_enable", "DsStormCtrl_usePkt", "DsStormCtrl_cntThrd",
            "DsStormCtrl_counter", "DsStormCtrl_step",
            # DsAcl_mem[idx]
            "DsAcl_action", "DsAcl_etherType", "DsAcl_vlanId",
            "DsAcl_srcMacHi", "DsAcl_srcMacLo",
        }
        for name in _reg_getters_int:
            func = getattr(L, f"switch_{name}")
            func.argtypes = [ctypes.c_int]
            func.restype = ctypes.c_int

        # -- 单例寄存器字段 getter（无参数） --
        _reg_getters_void = {
            "L2AgingCtl_fastAgingEn", "L2AgingCtl_agingEn", "L2AgingCtl_fastAgingAll",
            "L2AgingCtl_fastAgingByPort", "L2AgingCtl_portId", "L2AgingCtl_cycleThrd",
            "L2LearnCtl_sysLearnNum", "L2LearnCtl_lruEn",
            "LoopDetectCtl_en", "LoopDetectCtl_ttl", "LoopDetectCtl_loopMacHi",
            "LoopDetectCtl_loopMacLo", "LoopDetectCtl_detectInterval",
            "MirrorCtl_srcMirrorPort", "MirrorCtl_vlanMirrorPort",
            "PriorAssignCtl_ipDscpEn", "PriorAssignCtl_ipAddrEn", "PriorAssignCtl_macDaEn",
            "PriorAssignCtl_rldpEn", "PriorAssignCtl_rldpPrior",
            "PriorAssignCtl_dscpWeight", "PriorAssignCtl_vlanWeight", "PriorAssignCtl_portWeight",
            "PriorAssignCtl_ip0AddrPrior", "PriorAssignCtl_ip1AddrPrior",
            "PriorAssignCtl_ip0AddrBit127To96", "PriorAssignCtl_ip0MaskBit127To96",
            "PriorAssignCtl_ip1AddrBit127To96", "PriorAssignCtl_ip1MaskBit127To96",
            "PriorAssignCtl_ip0AddrBit95To64", "PriorAssignCtl_ip0MaskBit95To64",
            "PriorAssignCtl_ip1AddrBit95To64", "PriorAssignCtl_ip1MaskBit95To64",
            "StormCfgCtl_enable", "StormCfgCtl_delayInterval",
            "Ds1qPriorMap_prior", "DsDscpPriorMap_prior",
        }
        for name in _reg_getters_void:
            func = getattr(L, f"switch_{name}")
            func.argtypes = []
            func.restype = ctypes.c_int

        # VlanIdCamCtl_vlanId 有参数
        L.switch_VlanIdCamCtl_vlanId.argtypes = [ctypes.c_int]
        L.switch_VlanIdCamCtl_vlanId.restype = ctypes.c_int

        # -- Trace 索引 getter（无参数） --
        for name in ["giHashIdx", "giVlanIdx", "giAclIdx", "giStormCtlIdx",
                      "giStormSubIdx", "giLrnHash", "giLrnSubIdx"]:
            func = getattr(L, f"switch_{name}")
            func.argtypes = []
            func.restype = ctypes.c_int

    # ================================================================
    # 高级 API
    # ================================================================

    def init(self):
        """初始化交换机（复位所有表项）"""
        self._lib.switch_init()

    def process(self, pkt: bytes, src_port: int = 0):
        """送入一个以太网帧，运行完整流水线

        Args:
            pkt: 原始以太网帧字节
            src_port: 源端口号 (0..7)
        """
        pkt_len = len(pkt)
        pkt_arr = (ctypes.c_uint8 * pkt_len)(*pkt)
        self._lib.switch_process_packet(pkt_arr, pkt_len, src_port)

    def snapshot(self) -> dict:
        """抓取一包处理后的全部内部状态 + 全部寄存器字段

        Returns:
            dict 包含所有可观测变量，用于 Scoreboard 比对 + 全覆盖收集
        """
        L = self._lib
        snap = {
            # parser
            "prIsIpv4":          L.switch_prIsIpv4(),
            "prIsIpv6":          L.switch_prIsIpv6(),
            "prIsArp":           L.switch_prIsArp(),
            "prIsLoopDetection": L.switch_prIsLoopDetection(),
            "prVlanId":          L.switch_prVlanId(),
            "prExistVlan":       L.switch_prExistVlan(),
            "prIpDscp":          L.switch_prIpDscp(),
            "giTpid":            L.switch_giTpid(),
            # VLAN
            "piPortVid":         L.switch_piPortVid(),
            "piAft":             L.switch_piAft(),
            "giVlanHit":         L.switch_giVlanHit(),
            "giVlanTagged":      L.switch_giVlanTagged(),
            # forwarding
            "piDiscard":         L.switch_piDiscard(),
            "piBcast":           L.switch_piBcast(),
            "piMcast":           L.switch_piMcast(),
            "piBrgHit":          L.switch_piBrgHit(),
            "piFlooding":        L.switch_piFlooding(),
            "piFwdBmp":          L.switch_piFwdBmp(),
            "piPrior":           L.switch_piPrior(),
            # learning
            "giLrnHit":          L.switch_giLrnHit(),
            "giLrnNew":          L.switch_giLrnNew(),
            "giLruLrn":          L.switch_giLruLrn(),
            "piLrnDisable":      L.switch_piLrnDisable(),
            # outcome
            "enq_cnt":           L.switch_enqueue_count(),
        }

        # ── 寄存器字段全覆盖（使用 trace 索引定位实际条目） ──
        # 获取 trace 索引
        hash_idx   = L.switch_giHashIdx()      # MAC 查找命中条目
        vlan_idx   = L.switch_giVlanIdx()      # VLAN 表命中条目
        acl_idx    = L.switch_giAclIdx()       # ACL 命中条目
        storm_idx  = L.switch_giStormCtlIdx()  # 风暴控制条目
        storm_sub  = L.switch_giStormSubIdx()  # 风暴控制子条目
        lrn_hash   = L.switch_giLrnHash()      # MAC 学习 hash
        lrn_sub    = L.switch_giLrnSubIdx()    # MAC 学习子条目

        # DsPort_mem[0] — port 0 是测试端口，直接用
        for fld in ["portVid","dot1qBasedVlan","aft","keepVlanTag","portMacHi","portMacLo",
                     "stpState","maxMacNum","allowBrg2Src","lrnDisable","prior","rmaMode",
                     "mirrorEn","updateMacSa","strictPvid"]:
            func = getattr(L, f"switch_DsPort_{fld}")
            snap[f"DsPort_mem.{fld}"] = func(0)

        # DsVlan_mem[vlan_idx] — 用实际 VLAN 命中索引
        for fld in ["fid","vlanBmp","untagFlag","leakyUcast","leakyMcast","leakyBcast",
                     "leakyArp","leakyMirror","egressFilter","dot1qPriorEn","mirrorEn","prior"]:
            func = getattr(L, f"switch_DsVlan_{fld}")
            snap[f"DsVlan_mem.{fld}"] = func(vlan_idx)

        # DsMac_mem[hash_idx] — MAC 转发查找命中索引
        for fld in ["destMap","destDiscard","isMcast","prior"]:
            func = getattr(L, f"switch_DsMac_{fld}")
            snap[f"DsMac_mem.{fld}"] = func(hash_idx)

        # DsMacAging_mem[lrn_hash] — 学习条目索引
        for fld in ["aging0","aging1","aging2","aging3"]:
            func = getattr(L, f"switch_DsMacAging_{fld}")
            snap[f"DsMacAging_mem.{fld}"] = func(lrn_hash)

        # DsMacKey_mem[hash_idx] / [lrn_hash]
        snap["DsMacKey_mem.fid"] = L.switch_DsMacKey_fid(hash_idx)
        snap["DsMacKey_mem.macAddrHi"] = L.switch_DsMacKey_macAddrHi(hash_idx)
        snap["DsMacKey_mem.macAddrLo"] = L.switch_DsMacKey_macAddrLo(hash_idx)

        # DsMacStatic_mem[lrn_hash], DsMacValid_mem[lrn_hash]
        snap["DsMacStatic_mem.static"] = L.switch_DsMacStatic_static(lrn_hash)
        snap["DsMacValid_mem.valid"] = L.switch_DsMacValid_valid(lrn_hash)

        # DsStormCtrl_mem[storm_idx]
        for fld in ["enable","usePkt","cntThrd","counter","step"]:
            func = getattr(L, f"switch_DsStormCtrl_{fld}")
            snap[f"DsStormCtrl_mem.{fld}"] = func(storm_idx)

        # DsAcl_mem[acl_idx] — ACL 命中索引
        for fld in ["action","etherType","vlanId","srcMacHi","srcMacLo"]:
            func = getattr(L, f"switch_DsAcl_{fld}")
            snap[f"DsAcl_mem.{fld}"] = func(acl_idx)

        # 单例寄存器
        singletons = {
            "L2AgingCtl":    ["fastAgingEn","agingEn","fastAgingAll","fastAgingByPort","portId","cycleThrd"],
            "L2LearnCtl":    ["sysLearnNum","lruEn"],
            "LoopDetectCtl": ["en","ttl","loopMacHi","loopMacLo","detectInterval"],
            "MirrorCtl":     ["srcMirrorPort","vlanMirrorPort"],
            "PriorAssignCtl":["ipDscpEn","ipAddrEn","macDaEn","rldpEn","rldpPrior",
                              "dscpWeight","vlanWeight","portWeight","ip0AddrPrior","ip1AddrPrior",
                              "ip0AddrBit127To96","ip0MaskBit127To96","ip1AddrBit127To96","ip1MaskBit127To96",
                              "ip0AddrBit95To64","ip0MaskBit95To64","ip1AddrBit95To64","ip1MaskBit95To64"],
            "StormCfgCtl":   ["enable","delayInterval"],
        }
        for reg, fields in singletons.items():
            for fld in fields:
                func = getattr(L, f"switch_{reg}_{fld}")
                snap[f"{reg}.{fld}"] = func()

        # VlanIdCamCtl
        for i in range(16):
            snap[f"VlanIdCamCtl.vlanId{i}"] = L.switch_VlanIdCamCtl_vlanId(i)

        # Ds1qPriorMap_mem[0], DsDscpPriorMap_mem[0]
        snap["Ds1qPriorMap_mem.prior"] = L.switch_Ds1qPriorMap_prior(0)
        snap["DsDscpPriorMap_mem.prior"] = L.switch_DsDscpPriorMap_prior(0)

        return snap

    # ================================================================
    # 表项配置 API（通过 C setter 函数）
    # ================================================================

    def set_aft(self, port: int, aft: int):
        self._lib.switch_set_port_aft(port, aft)

    def set_port_vid(self, port: int, vid: int):
        self._lib.switch_set_port_vid(port, vid)

    def set_stp_state(self, port: int, state: int):
        self._lib.switch_set_port_stp(port, state)

    def set_max_mac(self, port: int, max_mac: int):
        self._lib.switch_set_port_max_mac(port, max_mac)

    def set_acl_entry(self, idx: int, action: int, ether_type: int):
        self._lib.switch_set_acl_entry(idx, action, ether_type)

    def reset_parser(self):
        """复位 parser 全局变量（消除跨包残留）"""
        self._lib.switch_reset_parser_globals()

    # -- 新增 Python setter（对应 C 侧 switch_set_xxx） --
    def set_port_dot1q(self, port, v):   self._lib.switch_set_DsPort_dot1qBasedVlan(port, v)
    def set_port_allowBrg(self, port, v): self._lib.switch_set_DsPort_allowBrg2Src(port, v)
    def set_vlan_fid(self, idx, v):       self._lib.switch_set_DsVlan_fid(idx, v)
    def set_vlan_bmp(self, idx, v):       self._lib.switch_set_DsVlan_vlanBmp(idx, v)
    def set_vlan_untag(self, idx, v):     self._lib.switch_set_DsVlan_untagFlag(idx, v)
    def set_vidcam_vlan(self, i, vid):    self._lib.switch_set_VlanIdCamCtl_vlanId(i, vid)
    def set_aging_en(self, v):            self._lib.switch_set_L2AgingCtl_agingEn(v)
    def set_fast_aging_all(self, v):      self._lib.switch_set_L2AgingCtl_fastAgingAll(v)
