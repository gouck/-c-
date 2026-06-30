/**
 * switch_api.c — 8m 交换芯片标准测试接口实现
 *
 * 职责:
 *   1. 定义所有全局变量（PacketByte[], 寄存器实例, 计数器等）
 *   2. 包装 forward_tick() 的调用，对外隐藏内部变量
 *   3. 实现 switch_api.h 中声明的所有接口函数
 *   4. 提供 enqueue_packet / send_packet 桩函数
 *
 * 编译时需要链接:
 *   8m_common.c   — 全局变量定义 + 弱函数
 *   8m_main.c     — forward_tick() + 各 process
 *   8m_parser.c   — parser()
 *   8m_switchX.c  — switchX()
 *   8m_egress.c   — egress()
 *   reg_drv_*.c   — 寄存器驱动
 */

#include "switch_api.h"
#include "reg_drv_common.h"
#include "reg_drv_tinyReg.h"
#include "reg_drv_tinyReg2.h"
#include <string.h>
#include <stdio.h>

/* ================================================================
 * 全局变量
 * ================================================================ */

uint8_t  PacketByte[512];

L2AgingCtl_t      L2AgingCtl;
L2LearnCtl_t      L2LearnCtl;
LoopDetectCtl_t   LoopDetectCtl;
MirrorCtl_t       MirrorCtl;
PriorAssignCtl_t  PriorAssignCtl;
StormCfgCtl_t     StormCfgCtl;
VlanIdCamCtl_t    VlanIdCamCtl;

extern uint32_t piSrcPort, piPktLength;
extern uint32_t prVlanId, piVlanId, piPrior;

int g_tb_ok = 0, g_tb_ng = 0;

/* ================================================================
 * 桩函数（tb.c 不覆盖时使用默认空实现）
 * ================================================================ */

static int g_enq;

void enqueue_packet(void *pkt, int len) {
    g_enq++;
    (void)pkt; (void)len;
}

void send_packet(void *pkt, int len) {
    (void)pkt; (void)len;
}

/* 由 8m_main.c 提供 */
void forward_tick(void);

/* ================================================================
 * 计数器
 * ================================================================ */

static uint64_t g_rx_cnt[8];
static uint64_t g_tx_cnt[8];
static uint64_t g_drop_cnt[8];

/* ================================================================
 * ACL 规则表（简化实现）
 * ================================================================ */

#define ACL_MAX_RULES 32
static struct {
    uint8_t  valid;
    uint8_t  action;       // 0=deny, 1=permit
    uint8_t  src_mac[6];
    uint8_t  src_mac_mask;
    uint8_t  dst_mac[6];
    uint8_t  dst_mac_mask;
    uint16_t ether_type;
    uint16_t vlan_id;
} g_acl[ACL_MAX_RULES];
static int g_acl_count = 0;

/* ================================================================
 * IGMP 组播表
 * ================================================================ */

#define IGMP_MAX_GROUPS 64
static struct {
    uint32_t group_ip;
    uint16_t member_ports;
} g_igmp[IGMP_MAX_GROUPS];
static int g_igmp_count = 0;

/* ================================================================
 * STP 端口状态
 * ================================================================ */

static int g_stp_state[8];   // 每个端口的 STP 状态

/* ================================================================
 * 端口安全
 * ================================================================ */

static int g_port_max_mac[8];
static int g_port_mac_cnt[8];

/* ================================================================
 * 内部工具
 * ================================================================ */

static void _init_all_tables(void) {
    int i;
    /* DsPort: 8 端口 */
    for (i = 0; i < 8; i++) {
        memset(&DsPort_mem[i], 0, sizeof(DsPort_mem[0]));
        DsPort_mem[i].portVid        = 100 + i;
        DsPort_mem[i].aft            = 0;
        DsPort_mem[i].allowBrg2Src   = 1;
        DsPort_mem[i].dot1qBasedVlan = 0;
    }
    /* DsVlan: 16 VLAN */
    for (i = 0; i < 16; i++) {
        memset(&DsVlan_mem[i], 0, sizeof(DsVlan_mem[0]));
        DsVlan_mem[i].vlanBmp   = 0xFF;
        DsVlan_mem[i].fid       = 100 + i;
        DsVlan_mem[i].untagFlag = 0xFF;
    }
    /* 优先级映射表 */
    memset(Ds1qPriorMap_mem,   0, sizeof(Ds1qPriorMap_mem));
    memset(DsDscpPriorMap_mem, 0, sizeof(DsDscpPriorMap_mem));
    /* 风暴控制表 */
    memset(DsStormCtrl_mem,    0, sizeof(DsStormCtrl_mem));
    /* MAC 表 */
    memset(DsMac_mem,        0, sizeof(DsMac_mem));
    memset(DsMacKey_mem,     0, sizeof(DsMacKey_mem));
    memset(DsMacValid_mem,   0, sizeof(DsMacValid_mem));
    memset(DsMacStatic_mem,  0, sizeof(DsMacStatic_mem));
    memset(DsMacAging_mem,   0, sizeof(DsMacAging_mem));
    memset(DsAcl_mem,        0, sizeof(DsAcl_mem));    // [text4新增]
    /* VlanIdCam */
    memset(&VlanIdCamCtl, 0, sizeof(VlanIdCamCtl));
    for (i = 0; i < 16; i++) {
        switch (i) {
            case  0: VlanIdCamCtl.vlanId0  = 100; break;
            case  1: VlanIdCamCtl.vlanId1  = 101; break;
            case  2: VlanIdCamCtl.vlanId2  = 102; break;
            case  3: VlanIdCamCtl.vlanId3  = 103; break;
            case  4: VlanIdCamCtl.vlanId4  = 104; break;
            case  5: VlanIdCamCtl.vlanId5  = 105; break;
            case  6: VlanIdCamCtl.vlanId6  = 106; break;
            case  7: VlanIdCamCtl.vlanId7  = 107; break;
            case  8: VlanIdCamCtl.vlanId8  = 108; break;
            case  9: VlanIdCamCtl.vlanId9  = 109; break;
            case 10: VlanIdCamCtl.vlanId10 = 110; break;
            case 11: VlanIdCamCtl.vlanId11 = 111; break;
            case 12: VlanIdCamCtl.vlanId12 = 112; break;
            case 13: VlanIdCamCtl.vlanId13 = 113; break;
            case 14: VlanIdCamCtl.vlanId14 = 114; break;
            case 15: VlanIdCamCtl.vlanId15 = 115; break;
        }
    }
    /* 寄存器 */
    memset(&L2AgingCtl,     0, sizeof(L2AgingCtl));
    memset(&L2LearnCtl,     0, sizeof(L2LearnCtl));
    memset(&LoopDetectCtl,  0, sizeof(LoopDetectCtl));
    memset(&MirrorCtl,      0, sizeof(MirrorCtl));
    memset(&PriorAssignCtl, 0, sizeof(PriorAssignCtl));
    memset(&StormCfgCtl,    0, sizeof(StormCfgCtl));
    /* 内部状态 */
    for (i = 0; i < 8; i++) {
        g_rx_cnt[i] = g_tx_cnt[i] = g_drop_cnt[i] = 0;
        g_stp_state[i] = SW_STP_FORWARDING;
        g_port_max_mac[i] = 0;
        g_port_mac_cnt[i] = 0;
    }
    g_acl_count  = 0;
    g_igmp_count = 0;
    g_enq        = 0;
}

/* ================================================================
 * 通用接口实现
 * ================================================================ */

void switch_init(void) {
    memset(PacketByte, 0, sizeof(PacketByte));
    _init_all_tables();
}

void switch_process_packet(uint8_t *pkt, int len, int src_port) {
    g_enq = 0;
    if (src_port >= 0 && src_port < 8) g_rx_cnt[src_port]++;
    memcpy(PacketByte, pkt, len < 512 ? len : 512);
    piSrcPort   = src_port;
    piPktLength = len;

    forward_tick();

    /* 统计丢弃 */
    if (g_enq == 0 && src_port >= 0 && src_port < 8)
        g_drop_cnt[src_port]++;
}

int  switch_enqueue_count(void)  { return g_enq; }
uint32_t switch_vlan_id(void)    { return prVlanId; }
uint32_t switch_vlan_priority(void) { return (prVlanId >> 12) & 0x7; }
uint8_t* switch_packet_buffer(void) { return PacketByte; }
int switch_is_discarded(void)    { return g_enq == 0; }

/* ================================================================
 * STP 实现
 * ================================================================ */

void switch_stp_set_state(int port, int state) {
    if (port >= 0 && port < 8) g_stp_state[port] = state;
}
int switch_port_is_forwarding(int port) {
    return (port >= 0 && port < 8) ? (g_stp_state[port] >= SW_STP_LEARNING) : 0;
}

/* ================================================================
 * IGMP Snooping 实现
 * ================================================================ */

void switch_igmp_join(int port, uint32_t group_ip) {
    for (int i = 0; i < g_igmp_count; i++) {
        if (g_igmp[i].group_ip == group_ip) {
            g_igmp[i].member_ports |= (1 << port);
            return;
        }
    }
    if (g_igmp_count < IGMP_MAX_GROUPS) {
        g_igmp[g_igmp_count].group_ip     = group_ip;
        g_igmp[g_igmp_count].member_ports = (1 << port);
        g_igmp_count++;
    }
}

void switch_igmp_leave(int port, uint32_t group_ip) {
    for (int i = 0; i < g_igmp_count; i++) {
        if (g_igmp[i].group_ip == group_ip) {
            g_igmp[i].member_ports &= ~(1 << port);
            return;
        }
    }
}

uint16_t switch_igmp_member_ports(uint32_t group_ip) {
    for (int i = 0; i < g_igmp_count; i++)
        if (g_igmp[i].group_ip == group_ip)
            return g_igmp[i].member_ports;
    return 0;
}

/* ================================================================
 * ACL 实现
 * ================================================================ */

static void _acl_add_rule(uint8_t action, uint8_t *smac, uint8_t *dmac,
                          uint16_t etype, uint16_t vid) {
    if (g_acl_count >= ACL_MAX_RULES) return;
    g_acl[g_acl_count].valid    = 1;
    g_acl[g_acl_count].action   = action;
    g_acl[g_acl_count].src_mac_mask = smac ? 0xFF : 0;
    g_acl[g_acl_count].dst_mac_mask = dmac ? 0xFF : 0;
    if (smac) memcpy(g_acl[g_acl_count].src_mac, smac, 6);
    if (dmac) memcpy(g_acl[g_acl_count].dst_mac, dmac, 6);
    g_acl[g_acl_count].ether_type = etype;
    g_acl[g_acl_count].vlan_id    = vid;
    g_acl_count++;
}

void switch_acl_add_deny(uint8_t *smac, uint8_t *dmac, uint16_t etype, uint16_t vid) {
    _acl_add_rule(0, smac, dmac, etype, vid);
}
void switch_acl_add_permit(uint8_t *smac, uint8_t *dmac, uint16_t etype, uint16_t vid) {
    _acl_add_rule(1, smac, dmac, etype, vid);
}
void switch_acl_clear(void) { g_acl_count = 0; }

/* ================================================================
 * 端口安全实现
 * ================================================================ */

void switch_port_set_max_mac(int port, int max) {
    if (port >= 0 && port < 8) g_port_max_mac[port] = max;
}
int switch_port_mac_count(int port) {
    return (port >= 0 && port < 8) ? g_port_mac_cnt[port] : 0;
}

/* ================================================================
 * 统计计数器实现
 * ================================================================ */

uint64_t switch_port_rx_packets(int port)   { return (port>=0&&port<8)?g_rx_cnt[port]:0; }
uint64_t switch_port_tx_packets(int port)   { return (port>=0&&port<8)?g_tx_cnt[port]:0; }
uint64_t switch_port_drop_packets(int port) { return (port>=0&&port<8)?g_drop_cnt[port]:0; }
