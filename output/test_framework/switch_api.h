/**
 * switch_api.h — 8m 交换芯片标准测试接口
 *
 * 设计原则:
 *   1. tb.c 只通过此头文件中的函数与交换机模型交互
 *   2. tb.c 不直接访问任何内部全局变量 (extern)
 *   3. tb.c 不感知 forward_tick / parser / switchX / egress 的存在
 *   4. 每个 L2 功能对应一组 get/set/action 接口
 *
 * 使用:
 *   #include "switch_api.h"          ← tb.c 唯一需要 include 的项目头文件
 *   switch_init();                   ← 每次测试前调用
 *   switch_process_packet(pkt,n,p);  ← 输入包，运行流水线
 *   result = switch_xxx();           ← 读取输出，判断 PASS/FAIL
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

/** 初始化交换机（复位所有表项和寄存器到默认状态） */
void switch_init(void);

/** 输入一个以太网帧，运行 parser → switchX → egress 全流水线
 *  @param pkt      以太网帧字节数组（会被 egress 修改）
 *  @param len      帧长度（字节）
 *  @param src_port 源端口号 (0..7)
 */
void switch_process_packet(uint8_t *pkt, int len, int src_port);

/** enqueue_packet 被调用的次数（即发送的包数） */
int  switch_enqueue_count(void);

/** parser 解析出的 VLAN ID */
uint32_t switch_vlan_id(void);

/** parser 解析出的 VLAN Priority (802.1p CoS) */
uint32_t switch_vlan_priority(void);

/** 获取包的当前状态（egress 编辑后的 PacketByte[] 首地址） */
uint8_t* switch_packet_buffer(void);

/** 包是否被丢弃 */
int switch_is_discarded(void);


/* ================================================================
 * STP / 端口状态
 * ================================================================ */

#define SW_STP_DISABLED   0
#define SW_STP_BLOCKING   1
#define SW_STP_LISTENING  2
#define SW_STP_LEARNING   3
#define SW_STP_FORWARDING 4

/** 设置端口 STP 状态 */
void switch_stp_set_state(int port, int state);

/** 查询端口是否在转发状态 */
int  switch_port_is_forwarding(int port);


/* ================================================================
 * IGMP Snooping / 组播
 * ================================================================ */

/** 模拟主机加入组播组（port 端口订阅 group_ip 组播地址） */
void switch_igmp_join(int port, uint32_t group_ip);

/** 模拟主机离开组播组 */
void switch_igmp_leave(int port, uint32_t group_ip);

/** 查询组播组的成员端口位图 */
uint16_t switch_igmp_member_ports(uint32_t group_ip);


/* ================================================================
 * ACL 访问控制
 * ================================================================ */

/** 添加一条 ACL 拒绝规则（任意字段传 NULL/0 表示不匹配该字段） */
void switch_acl_add_deny(uint8_t *src_mac, uint8_t *dst_mac,
                         uint16_t ether_type, uint16_t vlan_id);

/** 添加一条 ACL 允许规则 */
void switch_acl_add_permit(uint8_t *src_mac, uint8_t *dst_mac,
                           uint16_t ether_type, uint16_t vlan_id);

/** 清空所有 ACL 规则 */
void switch_acl_clear(void);


/* ================================================================
 * 端口安全
 * ================================================================ */

/** 设置端口允许学习的最大 MAC 地址数 */
void switch_port_set_max_mac(int port, int max);

/** 查询端口当前已学习的 MAC 地址数 */
int  switch_port_mac_count(int port);


/* ================================================================
 * 统计计数器
 * ================================================================ */

/** 端口接收包计数 */
uint64_t switch_port_rx_packets(int port);

/** 端口发送包计数 */
uint64_t switch_port_tx_packets(int port);

/** 端口丢弃包计数 */
uint64_t switch_port_drop_packets(int port);


/* ================================================================
 * 便利宏（tb.c 中使用）
 * ================================================================ */

extern int  g_tb_ok, g_tb_ng;
#define TB_TEST(n) printf("  [%2d] %-45s ", g_tb_ok+g_tb_ng+1, n)
#define TB_PASS()  do{puts("PASS");g_tb_ok++;}while(0)
#define TB_FAIL(m) do{printf("FAIL - %s\n",m);g_tb_ng++;}while(0)

#ifdef __cplusplus
}
#endif
#endif /* _SWITCH_API_H_ */
