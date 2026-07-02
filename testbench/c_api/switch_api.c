/**
 * switch_api.c — 测试适配层实现
 *
 * 职责:
 *   1. 定义全局变量（PacketByte[], 寄存器, 计数器）
 *   2. 包装 forward_tick() 调用
 *   3. 实现所有 switch_xxx() getter 函数
 *   4. 提供 enqueue_packet / send_packet 桩函数
 *
 * 编译:
 *   gcc -shared -fPIC switch_api.c <c_project>/src/8m_*.c \
 *       -o libswitch_dut.so -std=c99 -w -fcommon \
 *       -I<c_project>/include -I.
 */

#include "switch_api.h"
#include "reg_drv_common.h"
#include "reg_drv_tinyReg.h"
#include "reg_drv_tinyReg2.h"
#include <string.h>
#include <stdio.h>

/* ================================================================
 * 全局变量（DUT 需要的）
 * ================================================================ */

uint8_t  PacketByte[512];

L2AgingCtl_t      L2AgingCtl;
L2LearnCtl_t      L2LearnCtl;
LoopDetectCtl_t   LoopDetectCtl;
MirrorCtl_t       MirrorCtl;
PriorAssignCtl_t  PriorAssignCtl;
StormCfgCtl_t     StormCfgCtl;
VlanIdCamCtl_t    VlanIdCamCtl;

/* ================================================================
 * 从生成的 8m_globals_extern.h 引用 parser/switching 全局变量
 * ================================================================ */
extern uint32_t piSrcPort, piPktLength;
extern uint32_t piDestPort, piPrior, piVlanId, piPktTagged;
extern uint32_t piOutNoVlan, piIsLoopDetect, piLoopTtl;
extern uint32_t prVlanId, prVlanPrior, prExistVlan;
extern uint32_t prIsIpv4, prIsIpv6, prIsArp, prIsLoopDetection;
extern uint32_t prIpDscp, prIpSa, prIpDa;
extern uint64_t prMacDa, prMacSa;
extern uint32_t giTpid;

/* 表读取缓存（全局，switchX 填充） */
extern DsPort_entry_t        DsPort;
extern DsVlan_entry_t        DsVlan;
extern DsMac_entry_t         DsMacFwd;
extern DsMac_entry_t         DsMacLrn;
extern DsMacValid_entry_t    DsMacValid;

/* trace 变量（编译器 --trace 自动生成，switchX 末尾赋值） */
#include "8m_trace_extern.h"

int g_tb_ok = 0, g_tb_ng = 0;

/* ================================================================
 * 桩函数
 * ================================================================ */

static int g_enq;

void enqueue_packet(void *pkt, int len) {
    g_enq++;
    (void)pkt; (void)len;
}

void send_packet(void *pkt, int len) {
    (void)pkt; (void)len;
}

/* 由生成的 8m_main.c 提供 */
void forward_tick(void);

/* ================================================================
 * 计数器
 * ================================================================ */

static uint64_t g_rx_cnt[8];
static uint64_t g_tx_cnt[8];
static uint64_t g_drop_cnt[8];

/* ================================================================
 * 内部状态
 * ================================================================ */

static int g_stp_state[8];
static int g_port_max_mac[8];
static int g_port_mac_cnt[8];

/* ================================================================
 * 数组越界检查宏（setter/getter 共用）
 * ================================================================ */
#define PORT_OK(p)       ((p)>=0 && (p)<8)
#define VLAN_OK(i)       ((i)>=0 && (i)<16)
#define MAC_OK(i)        ((i)>=0 && (i)<2048)
#define ACL_OK(i)        ((i)>=0 && (i)<32)
#define STORM_OK(i)      ((i)>=0 && (i)<32)
#define PRIOR1Q_OK(i)    ((i)>=0 && (i)<8)
#define PRIORDSCP_OK(i)  ((i)>=0 && (i)<64)

/* ================================================================
 * 初始化（只做硬件复位，默认配置由 Python 侧 init_chip_config() 负责）
 * ================================================================ */

static void _hw_reset(void) {
    int i;
    /* 所有寄存器表清零 */
    memset(DsPort_mem,       0, sizeof(DsPort_mem));
    memset(DsVlan_mem,       0, sizeof(DsVlan_mem));
    memset(Ds1qPriorMap_mem, 0, sizeof(Ds1qPriorMap_mem));
    memset(DsDscpPriorMap_mem,0,sizeof(DsDscpPriorMap_mem));
    memset(DsStormCtrl_mem,  0, sizeof(DsStormCtrl_mem));
    memset(DsMac_mem,        0, sizeof(DsMac_mem));
    memset(DsMacKey_mem,     0, sizeof(DsMacKey_mem));
    memset(DsMacValid_mem,   0, sizeof(DsMacValid_mem));
    memset(DsMacStatic_mem,  0, sizeof(DsMacStatic_mem));
    memset(DsMacAging_mem,   0, sizeof(DsMacAging_mem));
    memset(DsAcl_mem,        0, sizeof(DsAcl_mem));
    memset(&VlanIdCamCtl,    0, sizeof(VlanIdCamCtl));
    memset(&L2AgingCtl,      0, sizeof(L2AgingCtl));
    memset(&L2LearnCtl,      0, sizeof(L2LearnCtl));
    memset(&LoopDetectCtl,   0, sizeof(LoopDetectCtl));
    memset(&MirrorCtl,       0, sizeof(MirrorCtl));
    memset(&PriorAssignCtl,  0, sizeof(PriorAssignCtl));
    memset(&StormCfgCtl,     0, sizeof(StormCfgCtl));
    /* 测试计数器归零 */
    for (i = 0; i < 8; i++) {
        g_rx_cnt[i] = g_tx_cnt[i] = g_drop_cnt[i] = 0;
        g_stp_state[i] = 0;
        g_port_max_mac[i] = 0;
        g_port_mac_cnt[i] = 0;
    }
    g_enq = 0;
}

void switch_init(void) {
    memset(PacketByte, 0, sizeof(PacketByte));
    _hw_reset();
    switch_reset_parser_globals();
}

/* ================================================================
 * Parser 全局变量复位（消除跨包残留）
 * ================================================================ */

void switch_reset_parser_globals(void) {
    prVlanId = 0; prVlanPrior = 0; prExistVlan = 0;
    prIsIpv4 = 0; prIsIpv6 = 0; prIsArp = 0; prIsLoopDetection = 0;
    giTpid = 0; prIpDscp = 0;
}

/* ================================================================
 * 包处理
 * ================================================================ */

void switch_process_packet(uint8_t *pkt, int len, int src_port) {
    g_enq = 0;
    if (src_port >= 0 && src_port < 8) g_rx_cnt[src_port]++;
    memcpy(PacketByte, pkt, len < 512 ? len : 512);
    piSrcPort   = src_port;
    piPktLength = len;
    switch_reset_parser_globals();
    forward_tick();
    if (g_enq == 0 && src_port >= 0 && src_port < 8)
        g_drop_cnt[src_port]++;
}

/* ================================================================
 * 通用 getter
 * ================================================================ */

int  switch_enqueue_count(void)   { return g_enq; }
int  switch_is_discarded(void)    { return g_enq == 0; }
uint32_t switch_vlan_id(void)     { return prVlanId; }
uint8_t* switch_packet_buffer(void) { return PacketByte; }

/* ================================================================
 * Phase 1: 内部状态 getter（可访问的 extern 变量）
 * ================================================================ */

/* -- parser 输出（全局 extern，完全可访问） -- */
int switch_prIsIpv4(void)          { return (int)prIsIpv4; }
int switch_prIsIpv6(void)          { return (int)prIsIpv6; }
int switch_prIsArp(void)           { return (int)prIsArp; }
int switch_prIsLoopDetection(void) { return (int)prIsLoopDetection; }
int switch_prVlanId(void)          { return (int)prVlanId; }
int switch_prExistVlan(void)       { return (int)prExistVlan; }
int switch_prIpDscp(void)          { return (int)prIpDscp; }
int switch_giTpid(void)            { return (int)giTpid; }

/* -- VLAN 处理（从 DsPort 缓存读取） -- */
int switch_piPortVid(void)         { return (int)DsPort.portVid; }
int switch_piAft(void)             { return (int)DsPort.aft; }

/* -- 这些变量是 switchX() 内的局部变量，无法直接读取。
   需要在编译器中加 --trace 选项来导出 extern 声明。
   当前通过 switch_is_discarded() 可间接判断 discard 状态。 -- */
int switch_piDiscard(void)         { return (int)g_trace_piDiscard; }
int switch_giVlanHit(void)         { return (int)g_trace_giVlanHit; }
int switch_giVlanTagged(void)      { return (int)g_trace_giVlanTagged; }
int switch_piBrgHit(void)          { return (int)g_trace_piBrgHit; }
int switch_piFlooding(void)        { return (int)g_trace_piFlooding; }
int switch_piBcast(void)           { return (int)g_trace_piBcast; }
int switch_piMcast(void)           { return (int)g_trace_piMcast; }
int switch_piFwdBmp(void)          { return (int)g_trace_piFwdBmp; }
int switch_piPrior(void)           { return (int)piPrior; }
int switch_giLrnHit(void)          { return (int)g_trace_giLrnHit; }
int switch_giLrnNew(void)          { return (int)g_trace_giLrnNew; }
int switch_giLruLrn(void)          { return (int)g_trace_giLruLrn; }
int switch_piLrnDisable(void)      { return (int)g_trace_piLrnDisable; }

/* ================================================================
 * 覆盖率桩（Python 侧收集，C 侧空实现）
 * ================================================================ */

void cov_hit_branch(const char *branch_name) {
    (void)branch_name;
    /* 由 Python coverage.py 通过 ctypes 回调实现 */
}

/* ================================================================
 * 端口 / ACL 配置（直接写硬件表）
 * ================================================================ */

void switch_set_port_aft(int port, int aft) {
    if (port >= 0 && port < 8) DsPort_mem[port].aft = aft & 0x3;
}
void switch_set_port_stp(int port, int state) {
    if (port >= 0 && port < 8) DsPort_mem[port].stpState = state & 0x7;
}
void switch_set_port_max_mac(int port, int max) {
    if (port >= 0 && port < 8) DsPort_mem[port].maxMacNum = max & 0xFF;
}
void switch_set_port_vid(int port, int vid) {
    if (port >= 0 && port < 8) DsPort_mem[port].portVid = vid & 0xFFF;
}
void switch_set_acl_entry(int idx, int action, int ether_type) {
    if (idx >= 0 && idx < 32) {
        DsAcl_mem[idx].action    = action & 1;
        DsAcl_mem[idx].etherType = ether_type & 0x7FFF;
    }
}

/* -- DsPort 全部字段 setter -- */
void switch_set_DsPort_dot1qBasedVlan(int port, int v) { if (PORT_OK(port)) DsPort_mem[port].dot1qBasedVlan = v & 1; }
void switch_set_DsPort_keepVlanTag(int port, int v)    { if (PORT_OK(port)) DsPort_mem[port].keepVlanTag    = v & 1; }
void switch_set_DsPort_allowBrg2Src(int port, int v)   { if (PORT_OK(port)) DsPort_mem[port].allowBrg2Src   = v & 1; }
void switch_set_DsPort_lrnDisable(int port, int v)     { if (PORT_OK(port)) DsPort_mem[port].lrnDisable     = v & 1; }
void switch_set_DsPort_rmaMode(int port, int v)        { if (PORT_OK(port)) DsPort_mem[port].rmaMode        = v & 1; }
void switch_set_DsPort_mirrorEn(int port, int v)       { if (PORT_OK(port)) DsPort_mem[port].mirrorEn       = v & 1; }
void switch_set_DsPort_updateMacSa(int port, int v)    { if (PORT_OK(port)) DsPort_mem[port].updateMacSa    = v & 1; }
void switch_set_DsPort_strictPvid(int port, int v)     { if (PORT_OK(port)) DsPort_mem[port].strictPvid     = v & 1; }
void switch_set_DsPort_prior(int port, int v)          { if (PORT_OK(port)) DsPort_mem[port].prior          = v & 3; }

/* -- DsVlan 全部字段 setter -- */
void switch_set_DsVlan_fid(int idx, int v)          { if (VLAN_OK(idx)) DsVlan_mem[idx].fid          = v & 0xFFF; }
void switch_set_DsVlan_vlanBmp(int idx, int v)      { if (VLAN_OK(idx)) DsVlan_mem[idx].vlanBmp      = v & 0x3FF; }
void switch_set_DsVlan_untagFlag(int idx, int v)    { if (VLAN_OK(idx)) DsVlan_mem[idx].untagFlag    = v & 0x3FF; }
void switch_set_DsVlan_leakyUcast(int idx, int v)   { if (VLAN_OK(idx)) DsVlan_mem[idx].leakyUcast   = v & 1; }
void switch_set_DsVlan_leakyMcast(int idx, int v)   { if (VLAN_OK(idx)) DsVlan_mem[idx].leakyMcast   = v & 1; }
void switch_set_DsVlan_leakyBcast(int idx, int v)   { if (VLAN_OK(idx)) DsVlan_mem[idx].leakyBcast   = v & 1; }
void switch_set_DsVlan_leakyArp(int idx, int v)     { if (VLAN_OK(idx)) DsVlan_mem[idx].leakyArp     = v & 1; }
void switch_set_DsVlan_leakyMirror(int idx, int v)  { if (VLAN_OK(idx)) DsVlan_mem[idx].leakyMirror  = v & 1; }
void switch_set_DsVlan_egressFilter(int idx, int v) { if (VLAN_OK(idx)) DsVlan_mem[idx].egressFilter = v & 1; }
void switch_set_DsVlan_dot1qPriorEn(int idx, int v) { if (VLAN_OK(idx)) DsVlan_mem[idx].dot1qPriorEn = v & 1; }
void switch_set_DsVlan_mirrorEn(int idx, int v)     { if (VLAN_OK(idx)) DsVlan_mem[idx].mirrorEn     = v & 1; }
void switch_set_DsVlan_prior(int idx, int v)        { if (VLAN_OK(idx)) DsVlan_mem[idx].prior        = v & 3; }

/* -- DsAcl 其余字段 setter -- */
void switch_set_DsAcl_vlanId(int idx, int v)    { if (ACL_OK(idx)) DsAcl_mem[idx].vlanId    = v & 0xFFF; }
void switch_set_DsAcl_srcMacHi(int idx, int v)  { if (ACL_OK(idx)) DsAcl_mem[idx].srcMacHi  = v & 0xFFFF; }
void switch_set_DsAcl_srcMacLo(int idx, int v)  { if (ACL_OK(idx)) DsAcl_mem[idx].srcMacLo  = v; }

/* -- VlanIdCamCtl 单例 setter -- */
void switch_set_VlanIdCamCtl_vlanId(int i, int vid) {
    switch (i) {
        case  0: VlanIdCamCtl.vlanId0  = vid & 0xFFF; break;
        case  1: VlanIdCamCtl.vlanId1  = vid & 0xFFF; break;
        case  2: VlanIdCamCtl.vlanId2  = vid & 0xFFF; break;
        case  3: VlanIdCamCtl.vlanId3  = vid & 0xFFF; break;
        case  4: VlanIdCamCtl.vlanId4  = vid & 0xFFF; break;
        case  5: VlanIdCamCtl.vlanId5  = vid & 0xFFF; break;
        case  6: VlanIdCamCtl.vlanId6  = vid & 0xFFF; break;
        case  7: VlanIdCamCtl.vlanId7  = vid & 0xFFF; break;
        case  8: VlanIdCamCtl.vlanId8  = vid & 0xFFF; break;
        case  9: VlanIdCamCtl.vlanId9  = vid & 0xFFF; break;
        case 10: VlanIdCamCtl.vlanId10 = vid & 0xFFF; break;
        case 11: VlanIdCamCtl.vlanId11 = vid & 0xFFF; break;
        case 12: VlanIdCamCtl.vlanId12 = vid & 0xFFF; break;
        case 13: VlanIdCamCtl.vlanId13 = vid & 0xFFF; break;
        case 14: VlanIdCamCtl.vlanId14 = vid & 0xFFF; break;
        case 15: VlanIdCamCtl.vlanId15 = vid & 0xFFF; break;
    }
}

/* -- 单例寄存器 setter -- */
void switch_set_L2AgingCtl_agingEn(int v)     { L2AgingCtl.agingEn     = v & 1; }
void switch_set_L2AgingCtl_fastAgingAll(int v){ L2AgingCtl.fastAgingAll = v & 1; }
void switch_set_L2LearnCtl_lruEn(int v)       { L2LearnCtl.lruEn       = v & 1; }
void switch_set_LoopDetectCtl_en(int v)        { LoopDetectCtl.en       = v & 1; }
void switch_set_MirrorCtl_srcMirrorPort(int v) { MirrorCtl.srcMirrorPort = v & 0xF; }
void switch_set_StormCfgCtl_enable(int v)      { StormCfgCtl.enable    = v & 1; }

/* -- Ds1qPriorMap / DsDscpPriorMap setter -- */
void switch_set_Ds1qPriorMap_prior(int idx, int v)   { if (PRIOR1Q_OK(idx))  Ds1qPriorMap_mem[idx].prior   = v & 3; }
void switch_set_DsDscpPriorMap_prior(int idx, int v) { if (PRIORDSCP_OK(idx)) DsDscpPriorMap_mem[idx].prior = v & 3; }

/* ================================================================
 * STP
 * ================================================================ */

void switch_stp_set_state(int port, int state) {
    if (port >= 0 && port < 8) g_stp_state[port] = state;
}
int switch_port_is_forwarding(int port) {
    return (port >= 0 && port < 8) ? (g_stp_state[port] >= SW_STP_LEARNING) : 0;
}

/* ================================================================
 * 端口安全
 * ================================================================ */

void switch_port_set_max_mac(int port, int max) {
    if (port >= 0 && port < 8) g_port_max_mac[port] = max;
}
int switch_port_mac_count(int port) {
    return (port >= 0 && port < 8) ? g_port_mac_cnt[port] : 0;
}

/* ================================================================
 * 统计
 * ================================================================ */

uint64_t switch_port_rx_packets(int port)   { return (port>=0&&port<8)?g_rx_cnt[port]:0; }
uint64_t switch_port_tx_packets(int port)   { return (port>=0&&port<8)?g_tx_cnt[port]:0; }
uint64_t switch_port_drop_packets(int port) { return (port>=0&&port<8)?g_drop_cnt[port]:0; }

/* ================================================================
 * 寄存器字段 getter（全覆盖支持 — 直接读取寄存器数组）
 * ================================================================ */

/* -- DsPort_mem[port] -- */
int switch_DsPort_portVid(int port)          { return PORT_OK(port)  ? DsPort_mem[port].portVid        : 0; }
int switch_DsPort_dot1qBasedVlan(int port)   { return PORT_OK(port)  ? DsPort_mem[port].dot1qBasedVlan : 0; }
int switch_DsPort_aft(int port)              { return PORT_OK(port)  ? DsPort_mem[port].aft            : 0; }
int switch_DsPort_keepVlanTag(int port)      { return PORT_OK(port)  ? DsPort_mem[port].keepVlanTag    : 0; }
int switch_DsPort_portMacHi(int port)        { return PORT_OK(port)  ? DsPort_mem[port].portMacHi      : 0; }
int switch_DsPort_portMacLo(int port)        { return PORT_OK(port)  ? DsPort_mem[port].portMacLo      : 0; }
int switch_DsPort_stpState(int port)         { return PORT_OK(port)  ? DsPort_mem[port].stpState       : 0; }
int switch_DsPort_maxMacNum(int port)        { return PORT_OK(port)  ? DsPort_mem[port].maxMacNum      : 0; }
int switch_DsPort_allowBrg2Src(int port)     { return PORT_OK(port)  ? DsPort_mem[port].allowBrg2Src   : 0; }
int switch_DsPort_lrnDisable(int port)       { return PORT_OK(port)  ? DsPort_mem[port].lrnDisable     : 0; }
int switch_DsPort_prior(int port)            { return PORT_OK(port)  ? DsPort_mem[port].prior          : 0; }
int switch_DsPort_rmaMode(int port)          { return PORT_OK(port)  ? DsPort_mem[port].rmaMode        : 0; }
int switch_DsPort_mirrorEn(int port)         { return PORT_OK(port)  ? DsPort_mem[port].mirrorEn       : 0; }
int switch_DsPort_updateMacSa(int port)      { return PORT_OK(port)  ? DsPort_mem[port].updateMacSa    : 0; }
int switch_DsPort_strictPvid(int port)       { return PORT_OK(port)  ? DsPort_mem[port].strictPvid     : 0; }

/* -- DsVlan_mem[idx] -- */
int switch_DsVlan_fid(int idx)          { return VLAN_OK(idx) ? DsVlan_mem[idx].fid          : 0; }
int switch_DsVlan_vlanBmp(int idx)      { return VLAN_OK(idx) ? DsVlan_mem[idx].vlanBmp      : 0; }
int switch_DsVlan_untagFlag(int idx)    { return VLAN_OK(idx) ? DsVlan_mem[idx].untagFlag    : 0; }
int switch_DsVlan_leakyUcast(int idx)   { return VLAN_OK(idx) ? DsVlan_mem[idx].leakyUcast   : 0; }
int switch_DsVlan_leakyMcast(int idx)   { return VLAN_OK(idx) ? DsVlan_mem[idx].leakyMcast   : 0; }
int switch_DsVlan_leakyBcast(int idx)   { return VLAN_OK(idx) ? DsVlan_mem[idx].leakyBcast   : 0; }
int switch_DsVlan_leakyArp(int idx)     { return VLAN_OK(idx) ? DsVlan_mem[idx].leakyArp     : 0; }
int switch_DsVlan_leakyMirror(int idx)  { return VLAN_OK(idx) ? DsVlan_mem[idx].leakyMirror  : 0; }
int switch_DsVlan_egressFilter(int idx) { return VLAN_OK(idx) ? DsVlan_mem[idx].egressFilter : 0; }
int switch_DsVlan_dot1qPriorEn(int idx) { return VLAN_OK(idx) ? DsVlan_mem[idx].dot1qPriorEn : 0; }
int switch_DsVlan_mirrorEn(int idx)     { return VLAN_OK(idx) ? DsVlan_mem[idx].mirrorEn     : 0; }
int switch_DsVlan_prior(int idx)        { return VLAN_OK(idx) ? DsVlan_mem[idx].prior        : 0; }

/* -- DsMac_mem[idx] -- */
int switch_DsMac_destMap(int idx)     { return MAC_OK(idx) ? DsMac_mem[idx].destMap     : 0; }
int switch_DsMac_destDiscard(int idx) { return MAC_OK(idx) ? DsMac_mem[idx].destDiscard : 0; }
int switch_DsMac_isMcast(int idx)     { return MAC_OK(idx) ? DsMac_mem[idx].isMcast     : 0; }
int switch_DsMac_prior(int idx)       { return MAC_OK(idx) ? DsMac_mem[idx].prior       : 0; }

/* -- DsMacAging_mem[idx] -- */
int switch_DsMacAging_aging0(int idx) { return MAC_OK(idx) ? DsMacAging_mem[idx].aging0 : 0; }
int switch_DsMacAging_aging1(int idx) { return MAC_OK(idx) ? DsMacAging_mem[idx].aging1 : 0; }
int switch_DsMacAging_aging2(int idx) { return MAC_OK(idx) ? DsMacAging_mem[idx].aging2 : 0; }
int switch_DsMacAging_aging3(int idx) { return MAC_OK(idx) ? DsMacAging_mem[idx].aging3 : 0; }

/* -- DsMacKey_mem[idx] -- */
int switch_DsMacKey_fid(int idx)    { return MAC_OK(idx) ? (int)DsMacKey_get_fid(&DsMacKey_mem[idx], 0) : 0; }
/* macAddr is 48-bit, we return it as two 32-bit parts */
int switch_DsMacKey_macAddrHi(int idx) { return MAC_OK(idx) ? (int)(DsMacKey_get_macAddr(&DsMacKey_mem[idx], 0) >> 32) : 0; }
int switch_DsMacKey_macAddrLo(int idx) { return MAC_OK(idx) ? (int)(DsMacKey_get_macAddr(&DsMacKey_mem[idx], 0) & 0xFFFFFFFF) : 0; }

/* -- DsMacStatic_mem[idx] -- */
int switch_DsMacStatic_static(int idx) { return MAC_OK(idx) ? DsMacStatic_mem[idx].__static : 0; }

/* -- DsMacValid_mem[idx] -- */
int switch_DsMacValid_valid(int idx) { return MAC_OK(idx) ? DsMacValid_mem[idx].valid : 0; }

/* -- DsStormCtrl_mem[idx] -- */
int switch_DsStormCtrl_enable(int idx)  { return STORM_OK(idx) ? DsStormCtrl_mem[idx].enable  : 0; }
int switch_DsStormCtrl_usePkt(int idx)  { return STORM_OK(idx) ? DsStormCtrl_mem[idx].usePkt  : 0; }
int switch_DsStormCtrl_cntThrd(int idx) { return STORM_OK(idx) ? (int)DsStormCtrl_mem[idx].cntThrd : 0; }
int switch_DsStormCtrl_counter(int idx) { return STORM_OK(idx) ? (int)DsStormCtrl_mem[idx].counter : 0; }
int switch_DsStormCtrl_step(int idx)    { return STORM_OK(idx) ? (int)DsStormCtrl_mem[idx].step    : 0; }

/* -- DsAcl_mem[idx] -- */
int switch_DsAcl_action(int idx)    { return ACL_OK(idx) ? DsAcl_mem[idx].action    : 0; }
int switch_DsAcl_etherType(int idx) { return ACL_OK(idx) ? DsAcl_mem[idx].etherType : 0; }
int switch_DsAcl_vlanId(int idx)    { return ACL_OK(idx) ? DsAcl_mem[idx].vlanId    : 0; }
int switch_DsAcl_srcMacHi(int idx)  { return ACL_OK(idx) ? DsAcl_mem[idx].srcMacHi  : 0; }
int switch_DsAcl_srcMacLo(int idx)  { return ACL_OK(idx) ? (int)DsAcl_mem[idx].srcMacLo : 0; }

/* -- L2AgingCtl (单例) -- */
int switch_L2AgingCtl_fastAgingEn(void)    { return L2AgingCtl.fastAgingEn; }
int switch_L2AgingCtl_agingEn(void)        { return L2AgingCtl.agingEn; }
int switch_L2AgingCtl_fastAgingAll(void)   { return L2AgingCtl.fastAgingAll; }
int switch_L2AgingCtl_fastAgingByPort(void){ return L2AgingCtl.fastAgingByPort; }
int switch_L2AgingCtl_portId(void)         { return L2AgingCtl.portId; }
int switch_L2AgingCtl_cycleThrd(void)      { return (int)L2AgingCtl.cycleThrd; }

/* -- L2LearnCtl (单例) -- */
int switch_L2LearnCtl_sysLearnNum(void) { return (int)L2LearnCtl.sysLearnNum; }
int switch_L2LearnCtl_lruEn(void)       { return L2LearnCtl.lruEn; }

/* -- LoopDetectCtl (单例) -- */
int switch_LoopDetectCtl_en(void)             { return LoopDetectCtl.en; }
int switch_LoopDetectCtl_ttl(void)            { return LoopDetectCtl.ttl; }
int switch_LoopDetectCtl_loopMacHi(void)      { return LoopDetectCtl.loopMacHi; }
int switch_LoopDetectCtl_loopMacLo(void)      { return (int)LoopDetectCtl.loopMacLo; }
int switch_LoopDetectCtl_detectInterval(void) { return (int)LoopDetectCtl.detectInterval; }

/* -- MirrorCtl (单例) -- */
int switch_MirrorCtl_srcMirrorPort(void)  { return MirrorCtl.srcMirrorPort; }
int switch_MirrorCtl_vlanMirrorPort(void) { return MirrorCtl.vlanMirrorPort; }

/* -- PriorAssignCtl (单例) -- */
int switch_PriorAssignCtl_ipDscpEn(void)           { return PriorAssignCtl.ipDscpEn; }
int switch_PriorAssignCtl_ipAddrEn(void)           { return PriorAssignCtl.ipAddrEn; }
int switch_PriorAssignCtl_macDaEn(void)            { return PriorAssignCtl.macDaEn; }
int switch_PriorAssignCtl_rldpEn(void)             { return PriorAssignCtl.rldpEn; }
int switch_PriorAssignCtl_rldpPrior(void)          { return PriorAssignCtl.rldpPrior; }
int switch_PriorAssignCtl_dscpWeight(void)         { return PriorAssignCtl.dscpWeight; }
int switch_PriorAssignCtl_vlanWeight(void)         { return PriorAssignCtl.vlanWeight; }
int switch_PriorAssignCtl_portWeight(void)         { return PriorAssignCtl.portWeight; }
int switch_PriorAssignCtl_ip0AddrPrior(void)       { return PriorAssignCtl.ip0AddrPrior; }
int switch_PriorAssignCtl_ip1AddrPrior(void)       { return PriorAssignCtl.ip1AddrPrior; }
int switch_PriorAssignCtl_ip0AddrBit127To96(void)  { return (int)PriorAssignCtl.ip0AddrBit127To96; }
int switch_PriorAssignCtl_ip0MaskBit127To96(void)  { return (int)PriorAssignCtl.ip0MaskBit127To96; }
int switch_PriorAssignCtl_ip1AddrBit127To96(void)  { return (int)PriorAssignCtl.ip1AddrBit127To96; }
int switch_PriorAssignCtl_ip1MaskBit127To96(void)  { return (int)PriorAssignCtl.ip1MaskBit127To96; }
int switch_PriorAssignCtl_ip0AddrBit95To64(void)   { return (int)PriorAssignCtl.ip0AddrBit95To64; }
int switch_PriorAssignCtl_ip0MaskBit95To64(void)   { return (int)PriorAssignCtl.ip0MaskBit95To64; }
int switch_PriorAssignCtl_ip1AddrBit95To64(void)   { return (int)PriorAssignCtl.ip1AddrBit95To64; }
int switch_PriorAssignCtl_ip1MaskBit95To64(void)   { return (int)PriorAssignCtl.ip1MaskBit95To64; }

/* -- StormCfgCtl (单例) -- */
int switch_StormCfgCtl_enable(void)        { return StormCfgCtl.enable; }
int switch_StormCfgCtl_delayInterval(void) { return (int)StormCfgCtl.delayInterval; }

/* -- VlanIdCamCtl (单例，16 个 vlanId) -- */
int switch_VlanIdCamCtl_vlanId(int i) {
    switch (i) {
        case  0: return VlanIdCamCtl.vlanId0;
        case  1: return VlanIdCamCtl.vlanId1;
        case  2: return VlanIdCamCtl.vlanId2;
        case  3: return VlanIdCamCtl.vlanId3;
        case  4: return VlanIdCamCtl.vlanId4;
        case  5: return VlanIdCamCtl.vlanId5;
        case  6: return VlanIdCamCtl.vlanId6;
        case  7: return VlanIdCamCtl.vlanId7;
        case  8: return VlanIdCamCtl.vlanId8;
        case  9: return VlanIdCamCtl.vlanId9;
        case 10: return VlanIdCamCtl.vlanId10;
        case 11: return VlanIdCamCtl.vlanId11;
        case 12: return VlanIdCamCtl.vlanId12;
        case 13: return VlanIdCamCtl.vlanId13;
        case 14: return VlanIdCamCtl.vlanId14;
        case 15: return VlanIdCamCtl.vlanId15;
        default: return 0;
    }
}

/* -- Ds1qPriorMap_mem[idx] -- */
int switch_Ds1qPriorMap_prior(int idx) { return PRIOR1Q_OK(idx) ? Ds1qPriorMap_mem[idx].prior : 0; }

/* -- DsDscpPriorMap_mem[idx] -- */
int switch_DsDscpPriorMap_prior(int idx) { return PRIORDSCP_OK(idx) ? DsDscpPriorMap_mem[idx].prior : 0; }

/* ================================================================
 * Trace 索引变量 getter（用于定位实际命中的表项）
 * ================================================================ */
int switch_giHashIdx(void)     { return (int)g_trace_giHashIdx; }
int switch_giVlanIdx(void)     { return (int)g_trace_giVlanIdx; }
int switch_giAclIdx(void)      { return (int)g_trace_giAclIdx; }
int switch_giStormCtlIdx(void) { return (int)g_trace_giStormCtlIdx; }
int switch_giStormSubIdx(void) { return (int)g_trace_giStormSubIdx; }
int switch_giLrnHash(void)     { return (int)g_trace_giLrnHash; }
int switch_giLrnSubIdx(void)   { return (int)g_trace_giLrnSubIdx; }
