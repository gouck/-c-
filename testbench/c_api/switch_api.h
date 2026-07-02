/**
 * switch_api.h — 8m 交换芯片标准测试接口（测试框架独立版本）
 *
 * 本文件独立于编译器，只需要指定一个 c_project 路径即可使用。
 *
 * 设计原则:
 *   1. tb 只通过此头文件中的函数与交换机模型交互
 *   2. tb 不直接访问任何内部全局变量
 *   3. 每个 L2 功能对应一组 get/set/action 接口
 *
 * 使用:
 *   #include "switch_api.h"
 *   switch_init();
 *   switch_process_packet(pkt, len, port);
 *   result = switch_xxx();
 */

#ifndef _SWITCH_API_H_
#define _SWITCH_API_H_
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================
 * 通用接口
 * ================================================================ */

void     switch_init(void);
void     switch_process_packet(uint8_t *pkt, int len, int src_port);
int      switch_enqueue_count(void);
uint32_t switch_vlan_id(void);
uint8_t* switch_packet_buffer(void);
int      switch_is_discarded(void);

/* ================================================================
 * Phase 1: 内部状态观测 (Monitor)
 * 这些 getter 读取 switchX() 执行后的内部变量快照
 * ================================================================ */

/* -- parser 输出 -- */
int switch_prIsIpv4(void);
int switch_prIsIpv6(void);
int switch_prIsArp(void);
int switch_prIsLoopDetection(void);
int switch_prVlanId(void);
int switch_prExistVlan(void);
int switch_prIpDscp(void);
int switch_giTpid(void);

/* -- VLAN 处理 -- */
int switch_piPortVid(void);      /* 端口 PVID */
int switch_piAft(void);          /* Acceptable Frame Type (0/1/2/3) */
int switch_giVlanHit(void);      /* VLAN CAM 命中? */
int switch_giVlanTagged(void);   /* 报文带 802.1Q tag? */

/* -- 转发决策 -- */
int switch_piDiscard(void);      /* 丢弃标志 */
int switch_piBcast(void);        /* 广播? */
int switch_piMcast(void);        /* 组播? */
int switch_piBrgHit(void);       /* MAC 表命中? */
int switch_piFlooding(void);     /* 泛洪? */
int switch_piFwdBmp(void);       /* 转发端口位图 [7:0] */
int switch_piPrior(void);        /* 最终优先级 [1:0] */

/* -- MAC 学习 -- */
int switch_giLrnHit(void);       /* 学习: SMAC 已存在? */
int switch_giLrnNew(void);       /* 学习: 新条目? */
int switch_giLruLrn(void);       /* 学习: LRU 替换? */

/* -- 其他 -- */
int switch_piLrnDisable(void);   /* 学习禁用? */

/* ================================================================
 * 覆盖率桩函数（C 侧不实现，Python 侧收集）
 * ================================================================ */
void cov_hit_branch(const char *branch_name);

/* ================================================================
 * 初始化 / 复位
 * ================================================================ */
void switch_reset_parser_globals(void);

/* ================================================================
 * 端口配置（直接写 DsPort_mem）
 * ================================================================ */
void switch_set_port_aft(int port, int aft);
void switch_set_port_stp(int port, int state);
void switch_set_port_max_mac(int port, int max);
void switch_set_port_vid(int port, int vid);
/* DsPort 其余字段 setter */
void switch_set_DsPort_dot1qBasedVlan(int port, int v);
void switch_set_DsPort_keepVlanTag(int port, int v);
void switch_set_DsPort_allowBrg2Src(int port, int v);
void switch_set_DsPort_lrnDisable(int port, int v);
void switch_set_DsPort_rmaMode(int port, int v);
void switch_set_DsPort_mirrorEn(int port, int v);
void switch_set_DsPort_updateMacSa(int port, int v);
void switch_set_DsPort_strictPvid(int port, int v);
void switch_set_DsPort_prior(int port, int v);

/* ================================================================
 * ACL / VLAN / 其他寄存器配置
 * ================================================================ */
void switch_set_acl_entry(int idx, int action, int ether_type);
void switch_set_DsAcl_vlanId(int idx, int v);
void switch_set_DsAcl_srcMacHi(int idx, int v);
void switch_set_DsAcl_srcMacLo(int idx, int v);

void switch_set_DsVlan_fid(int idx, int v);
void switch_set_DsVlan_vlanBmp(int idx, int v);
void switch_set_DsVlan_untagFlag(int idx, int v);
void switch_set_DsVlan_leakyUcast(int idx, int v);
void switch_set_DsVlan_leakyMcast(int idx, int v);
void switch_set_DsVlan_leakyBcast(int idx, int v);
void switch_set_DsVlan_leakyArp(int idx, int v);
void switch_set_DsVlan_leakyMirror(int idx, int v);
void switch_set_DsVlan_egressFilter(int idx, int v);
void switch_set_DsVlan_dot1qPriorEn(int idx, int v);
void switch_set_DsVlan_mirrorEn(int idx, int v);
void switch_set_DsVlan_prior(int idx, int v);

void switch_set_VlanIdCamCtl_vlanId(int i, int vid);

void switch_set_L2AgingCtl_agingEn(int v);
void switch_set_L2AgingCtl_fastAgingAll(int v);
void switch_set_L2LearnCtl_lruEn(int v);
void switch_set_LoopDetectCtl_en(int v);
void switch_set_MirrorCtl_srcMirrorPort(int v);
void switch_set_StormCfgCtl_enable(int v);

void switch_set_Ds1qPriorMap_prior(int idx, int v);
void switch_set_DsDscpPriorMap_prior(int idx, int v);

/* ================================================================
 * STP / 端口状态
 * ================================================================ */
#define SW_STP_DISABLED   0
#define SW_STP_BLOCKING   1
#define SW_STP_LISTENING  2
#define SW_STP_LEARNING   3
#define SW_STP_FORWARDING 4

void switch_stp_set_state(int port, int state);
int  switch_port_is_forwarding(int port);

/* ================================================================
 * 端口安全
 * ================================================================ */
void switch_port_set_max_mac(int port, int max);
int  switch_port_mac_count(int port);

/* ================================================================
 * 统计计数器
 * ================================================================ */
uint64_t switch_port_rx_packets(int port);
uint64_t switch_port_tx_packets(int port);
uint64_t switch_port_drop_packets(int port);

/* ================================================================
 * 寄存器字段 getter（全覆盖 — 直接读取硬件寄存器数组）
 * ================================================================ */

/* -- DsPort_mem[port] -- */
int switch_DsPort_portVid(int port);
int switch_DsPort_dot1qBasedVlan(int port);
int switch_DsPort_aft(int port);
int switch_DsPort_keepVlanTag(int port);
int switch_DsPort_portMacHi(int port);
int switch_DsPort_portMacLo(int port);
int switch_DsPort_stpState(int port);
int switch_DsPort_maxMacNum(int port);
int switch_DsPort_allowBrg2Src(int port);
int switch_DsPort_lrnDisable(int port);
int switch_DsPort_prior(int port);
int switch_DsPort_rmaMode(int port);
int switch_DsPort_mirrorEn(int port);
int switch_DsPort_updateMacSa(int port);
int switch_DsPort_strictPvid(int port);

/* -- DsVlan_mem[idx] -- */
int switch_DsVlan_fid(int idx);
int switch_DsVlan_vlanBmp(int idx);
int switch_DsVlan_untagFlag(int idx);
int switch_DsVlan_leakyUcast(int idx);
int switch_DsVlan_leakyMcast(int idx);
int switch_DsVlan_leakyBcast(int idx);
int switch_DsVlan_leakyArp(int idx);
int switch_DsVlan_leakyMirror(int idx);
int switch_DsVlan_egressFilter(int idx);
int switch_DsVlan_dot1qPriorEn(int idx);
int switch_DsVlan_mirrorEn(int idx);
int switch_DsVlan_prior(int idx);

/* -- DsMac_mem[idx] -- */
int switch_DsMac_destMap(int idx);
int switch_DsMac_destDiscard(int idx);
int switch_DsMac_isMcast(int idx);
int switch_DsMac_prior(int idx);

/* -- DsMacAging_mem[idx] -- */
int switch_DsMacAging_aging0(int idx);
int switch_DsMacAging_aging1(int idx);
int switch_DsMacAging_aging2(int idx);
int switch_DsMacAging_aging3(int idx);

/* -- DsMacKey_mem[idx] -- */
int switch_DsMacKey_fid(int idx);
int switch_DsMacKey_macAddrHi(int idx);
int switch_DsMacKey_macAddrLo(int idx);

/* -- DsMacStatic_mem[idx] -- */
int switch_DsMacStatic_static(int idx);

/* -- DsMacValid_mem[idx] -- */
int switch_DsMacValid_valid(int idx);

/* -- DsStormCtrl_mem[idx] -- */
int switch_DsStormCtrl_enable(int idx);
int switch_DsStormCtrl_usePkt(int idx);
int switch_DsStormCtrl_cntThrd(int idx);
int switch_DsStormCtrl_counter(int idx);
int switch_DsStormCtrl_step(int idx);

/* -- DsAcl_mem[idx] -- */
int switch_DsAcl_action(int idx);
int switch_DsAcl_etherType(int idx);
int switch_DsAcl_vlanId(int idx);
int switch_DsAcl_srcMacHi(int idx);
int switch_DsAcl_srcMacLo(int idx);

/* -- L2AgingCtl (单例) -- */
int switch_L2AgingCtl_fastAgingEn(void);
int switch_L2AgingCtl_agingEn(void);
int switch_L2AgingCtl_fastAgingAll(void);
int switch_L2AgingCtl_fastAgingByPort(void);
int switch_L2AgingCtl_portId(void);
int switch_L2AgingCtl_cycleThrd(void);

/* -- L2LearnCtl (单例) -- */
int switch_L2LearnCtl_sysLearnNum(void);
int switch_L2LearnCtl_lruEn(void);

/* -- LoopDetectCtl (单例) -- */
int switch_LoopDetectCtl_en(void);
int switch_LoopDetectCtl_ttl(void);
int switch_LoopDetectCtl_loopMacHi(void);
int switch_LoopDetectCtl_loopMacLo(void);
int switch_LoopDetectCtl_detectInterval(void);

/* -- MirrorCtl (单例) -- */
int switch_MirrorCtl_srcMirrorPort(void);
int switch_MirrorCtl_vlanMirrorPort(void);

/* -- PriorAssignCtl (单例) -- */
int switch_PriorAssignCtl_ipDscpEn(void);
int switch_PriorAssignCtl_ipAddrEn(void);
int switch_PriorAssignCtl_macDaEn(void);
int switch_PriorAssignCtl_rldpEn(void);
int switch_PriorAssignCtl_rldpPrior(void);
int switch_PriorAssignCtl_dscpWeight(void);
int switch_PriorAssignCtl_vlanWeight(void);
int switch_PriorAssignCtl_portWeight(void);
int switch_PriorAssignCtl_ip0AddrPrior(void);
int switch_PriorAssignCtl_ip1AddrPrior(void);
int switch_PriorAssignCtl_ip0AddrBit127To96(void);
int switch_PriorAssignCtl_ip0MaskBit127To96(void);
int switch_PriorAssignCtl_ip1AddrBit127To96(void);
int switch_PriorAssignCtl_ip1MaskBit127To96(void);
int switch_PriorAssignCtl_ip0AddrBit95To64(void);
int switch_PriorAssignCtl_ip0MaskBit95To64(void);
int switch_PriorAssignCtl_ip1AddrBit95To64(void);
int switch_PriorAssignCtl_ip1MaskBit95To64(void);

/* -- StormCfgCtl (单例) -- */
int switch_StormCfgCtl_enable(void);
int switch_StormCfgCtl_delayInterval(void);

/* -- VlanIdCamCtl (单例) -- */
int switch_VlanIdCamCtl_vlanId(int i);

/* -- Ds1qPriorMap_mem[idx] -- */
int switch_Ds1qPriorMap_prior(int idx);

/* -- DsDscpPriorMap_mem[idx] -- */
int switch_DsDscpPriorMap_prior(int idx);

/* -- Trace 索引变量（定位实际命中的表项） -- */
int switch_giHashIdx(void);
int switch_giVlanIdx(void);
int switch_giAclIdx(void);
int switch_giStormCtlIdx(void);
int switch_giStormSubIdx(void);
int switch_giLrnHash(void);
int switch_giLrnSubIdx(void);

/* ================================================================
 * 便利宏（C tb 中使用）
 * ================================================================ */
extern int g_tb_ok, g_tb_ng;
#define TB_TEST(n) printf("  [%2d] %-45s ", g_tb_ok+g_tb_ng+1, n)
#define TB_PASS()  do{puts("PASS");g_tb_ok++;}while(0)
#define TB_FAIL(m) do{printf("FAIL - %s\n",m);g_tb_ng++;}while(0)

#ifdef __cplusplus
}
#endif
#endif /* _SWITCH_API_H_ */
