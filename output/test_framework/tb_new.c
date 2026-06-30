/**
 * tb_new.c — 8m 交换芯片标准测试平台（使用 switch_api 接口）
 *
 * 编译（以 001 工程为例）:
 *   cd output/001/c_project
 *   gcc ../test_framework/tb_new.c ../test_framework/switch_api.c \
 *       src/8m_common.c src/8m_main.c src/8m_parser.c \
 *       src/8m_switchX.c src/8m_egress.c \
 *       -o tb_new.exe -std=c99 -w -fcommon -Iinclude -I../test_framework
 *   ./tb_new.exe
 *
 * 数据流:
 *   构造帧 → switch_init() → switch_process_packet() → 检查 switch_xxx()
 */

#include "switch_api.h"
#include "reg_drv_common.h"
#include "reg_drv_tinyReg.h"
#include "reg_drv_tinyReg2.h"
#include <stdio.h>
#include <string.h>

/* ================================================================
 * 测试用例
 * ================================================================ */

static void test_vlan_parse(void) {
    TB_TEST("VLAN VID=100 parser");
    switch_init();
    uint8_t pkt[512] = {0};
    pkt[12]=0x81; pkt[13]=0x00;  // TPID=0x8100
    pkt[14]=0x00; pkt[15]=0x64;  // VID=100
    switch_process_packet(pkt, 64, 0);
    if (switch_vlan_id() != 100) TB_FAIL("VID!=100"); else TB_PASS();
}

static void test_bcast(void) {
    TB_TEST("广播 flooding >=7 enqueue");
    switch_init();
    uint8_t pkt[512] = {0};
    memset(pkt, 0xFF, 6);              // DMAC = broadcast
    pkt[12]=0x08; pkt[13]=0x00;        // EtherType=0x0800
    switch_process_packet(pkt, 64, 0);
    if (switch_enqueue_count() < 7) TB_FAIL("enqueue<7"); else TB_PASS();
}

static void test_ucast_flood(void) {
    TB_TEST("未知单播 flooding >=1 enqueue");
    switch_init();
    uint8_t pkt[512] = {0};
    pkt[0]=0x02; pkt[5]=0x01;          // DMAC=未知单播
    pkt[6]=0x02; pkt[11]=0x02;         // SMAC
    pkt[12]=0x08; pkt[13]=0x00;
    switch_process_packet(pkt, 64, 1);
    if (switch_enqueue_count() < 1) TB_FAIL("enqueue==0"); else TB_PASS();
}

static void test_untag(void) {
    TB_TEST("VLAN untag -> TPID移除");
    switch_init();
    uint8_t pkt[512] = {0};
    pkt[12]=0x81; pkt[13]=0x00;
    pkt[14]=0x00; pkt[15]=0x64;
    switch_process_packet(pkt, 64, 0);
    uint16_t t = (switch_packet_buffer()[12]<<8) | switch_packet_buffer()[13];
    if (t == 0x8100) TB_FAIL("仍有TPID"); else TB_PASS();
}

/* ---- 扩展测试示例 ---- */

static void test_stp_blocking(void) {
    TB_TEST("STP Blocking 端口不转发");
    switch_init();
    // 设置端口1的STP状态为Blocking（通过DsPort表的stpState字段）
    DsPort_mem[1].stpState = 1;   // 1=Blocking
    uint8_t pkt[512] = {0};
    memset(pkt, 0xFF, 6); pkt[12]=0x08; pkt[13]=0x00;
    switch_process_packet(pkt, 64, 1);
    if (switch_enqueue_count() > 0)
        TB_FAIL("blocking port forwarded");
    else TB_PASS();
}

static void test_acl_deny_arp(void) {
    TB_TEST("ACL 拒绝 ARP 包");
    switch_init();
    // 设置 ACL 表第一条规则：action=deny, etherType=0x0806
    DsAcl_mem[0].action    = 0;       // deny
    DsAcl_mem[0].etherType  = 0x0806; // 匹配ARP
    uint8_t pkt[512] = {0};
    pkt[12]=0x08; pkt[13]=0x06;        // EtherType=ARP
    switch_process_packet(pkt, 64, 0);
    if (switch_enqueue_count() > 0)
        TB_FAIL("ARP not blocked by ACL");
    else TB_PASS();
}

static void test_port_security(void) {
    TB_TEST("端口安全 MAC 数量限制");
    switch_init();
    // 设置端口0最多学2个MAC
    DsPort_mem[0].maxMacNum = 2;
    for (int i = 0; i < 3; i++) {
        uint8_t pkt[512] = {0};
        pkt[6] = 0x02; pkt[11] = (uint8_t)(0x10 + i);
        pkt[0] = 0xFF; pkt[5] = 0xFF;
        pkt[12]=0x08; pkt[13]=0x00;
        switch_process_packet(pkt, 64, 0);
    }
    if (switch_port_mac_count(0) > 2)
        TB_FAIL("MAC count exceeds limit");
    else TB_PASS();
}

/* ================================================================
 * 主函数
 * ================================================================ */

int main(void) {
    printf("\n========================================\n");
    printf("  8m Switch Chip - Standard Testbench\n");
    printf("  (using switch_api interface)\n");
    printf("========================================\n\n");

    /* 原始测试 */
    test_vlan_parse();
    test_bcast();
    test_ucast_flood();
    test_untag();

    /* 扩展测试（当前为桩实现，待伪代码功能补齐后生效） */
    test_stp_blocking();
    test_acl_deny_arp();
    test_port_security();

    printf("\n========================================\n");
    printf("  %d tests: %d PASS, %d FAIL\n",
           g_tb_ok + g_tb_ng, g_tb_ok, g_tb_ng);
    printf("========================================\n");
    return g_tb_ng ? 1 : 0;
}
