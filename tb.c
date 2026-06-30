/**
 * tb.c — 8m 交换芯片 C 模型测试平台
 *
 * 编译: gcc tb.c output.c -o tb.exe -std=c99 -w -fcommon
 *       (需要 -fcommon 因为 reg_drv.h 中的 _mem[] 在两个 .c 里暂定定义)
 * 运行: ./tb.exe
 *
 * 数据流:
 *   1. 填充 PacketByte[] (以太网帧)
 *   2. 设置 piSrcPort, piPktLength
 *   3. 调用 forward_tick() → parser() → switchX() → egress()
 *   4. 检查: enqueue 次数, prVlanId (parser输出), PacketByte[] 内容
 */

#include <stdio.h>
#include <string.h>
#include <stdint.h>

uint8_t  PacketByte[512];

#include "reg_drv_common.h"
#include "reg_drv_tinyReg.h"
#include "reg_drv_tinyReg2.h"

L2AgingCtl_t      L2AgingCtl;
L2LearnCtl_t      L2LearnCtl;
LoopDetectCtl_t   LoopDetectCtl;
MirrorCtl_t       MirrorCtl;
PriorAssignCtl_t  PriorAssignCtl;
StormCfgCtl_t     StormCfgCtl;
VlanIdCamCtl_t    VlanIdCamCtl;

extern uint32_t piSrcPort, piPktLength;
extern uint32_t prVlanId, piVlanId, piPrior;

static int g_enq;
void enqueue_packet(void *pkt, int len) { g_enq++; (void)pkt; (void)len; }
void send_packet(void *pkt, int len) { (void)pkt; (void)len; }
void forward_tick(void);

static int g_ok, g_ng;
#define T(n) printf("  [%2d] %-45s ", g_ok+g_ng+1, n)
#define OK()  do{puts("PASS");g_ok++;}while(0)
#define NG(m) do{printf("FAIL - %s\n",m);g_ng++;}while(0)

static void mac(int o, const char *s){
    unsigned b[6]; sscanf(s,"%x:%x:%x:%x:%x:%x",b,b+1,b+2,b+3,b+4,b+5);
    for(int i=0;i<6;i++) PacketByte[o+i]=(uint8_t)b[i];
}
static void u16(int o,uint16_t v){PacketByte[o]=(uint8_t)(v>>8);PacketByte[o+1]=(uint8_t)v;}

static void init_tables(void){
    int i;
    for(i=0;i<8;i++){
        memset(&DsPort_mem[i],0,sizeof(DsPort_mem[0]));
        DsPort_mem[i].portVid=100+i; DsPort_mem[i].aft=0;
        DsPort_mem[i].allowBrg2Src=1; DsPort_mem[i].dot1qBasedVlan=0;
    }
    for(i=0;i<16;i++){
        memset(&DsVlan_mem[i],0,sizeof(DsVlan_mem[0]));
        DsVlan_mem[i].vlanBmp=0xFF; DsVlan_mem[i].fid=100+i;
        DsVlan_mem[i].untagFlag=0xFF;
    }
    memset(Ds1qPriorMap_mem,0,sizeof(Ds1qPriorMap_mem));
    memset(DsStormCtrl_mem,0,sizeof(DsStormCtrl_mem));
    memset(DsMac_mem,0,sizeof(DsMac_mem));
    memset(DsMacKey_mem,0,sizeof(DsMacKey_mem));
    memset(DsMacValid_mem,0,sizeof(DsMacValid_mem));
    memset(DsMacStatic_mem,0,sizeof(DsMacStatic_mem));
    memset(DsMacAging_mem,0,sizeof(DsMacAging_mem));
    memset(&VlanIdCamCtl,0,sizeof(VlanIdCamCtl));
    for(i=0;i<16;i++){
        switch(i){
            case 0:VlanIdCamCtl.vlanId0=100;break; case 1:VlanIdCamCtl.vlanId1=101;break;
            case 2:VlanIdCamCtl.vlanId2=102;break; case 3:VlanIdCamCtl.vlanId3=103;break;
            case 4:VlanIdCamCtl.vlanId4=104;break; case 5:VlanIdCamCtl.vlanId5=105;break;
            case 6:VlanIdCamCtl.vlanId6=106;break; case 7:VlanIdCamCtl.vlanId7=107;break;
            case 8:VlanIdCamCtl.vlanId8=108;break; case 9:VlanIdCamCtl.vlanId9=109;break;
            case 10:VlanIdCamCtl.vlanId10=110;break; case 11:VlanIdCamCtl.vlanId11=111;break;
            case 12:VlanIdCamCtl.vlanId12=112;break; case 13:VlanIdCamCtl.vlanId13=113;break;
            case 14:VlanIdCamCtl.vlanId14=114;break; case 15:VlanIdCamCtl.vlanId15=115;break;
        }
    }
    memset(&L2AgingCtl,0,sizeof(L2AgingCtl));
    memset(&L2LearnCtl,0,sizeof(L2LearnCtl));
    memset(&LoopDetectCtl,0,sizeof(LoopDetectCtl));
    memset(&MirrorCtl,0,sizeof(MirrorCtl));
    memset(&PriorAssignCtl,0,sizeof(PriorAssignCtl));
    memset(&StormCfgCtl,0,sizeof(StormCfgCtl));
}

static void test_vlan_parse(void){
    T("VLAN VID=100 parser");
    init_tables(); memset(PacketByte,0,512); g_enq=0;
    piSrcPort=0; piPktLength=64;
    mac(0,"02:00:00:00:00:01"); mac(6,"02:00:00:00:00:02");
    u16(12,0x8100); u16(14,0x0064);
    forward_tick();
    if(prVlanId!=100) NG("prVlanId!=100"); else OK();
}

static void test_bcast(void){
    T("广播 flooding >=7 enqueue");
    init_tables(); memset(PacketByte,0,512); g_enq=0;
    piSrcPort=0; piPktLength=64;
    mac(0,"ff:ff:ff:ff:ff:ff"); mac(6,"02:00:00:00:00:01"); u16(12,0x0800);
    forward_tick();
    if(g_enq<7) NG("enqueue<7"); else OK();
}

static void test_ucast_flood(void){
    T("未知单播 flooding >=1 enqueue");
    init_tables(); memset(PacketByte,0,512); g_enq=0;
    piSrcPort=1; piPktLength=64;
    mac(0,"02:00:00:00:00:01"); mac(6,"02:00:00:00:00:02"); u16(12,0x0800);
    forward_tick();
    if(g_enq<1) NG("enqueue==0"); else OK();
}

static void test_untag(void){
    T("VLAN untag -> TPID移除");
    init_tables(); memset(PacketByte,0,512); g_enq=0;
    piSrcPort=0; piPktLength=64;
    mac(0,"02:00:00:00:00:01"); mac(6,"02:00:00:00:00:02");
    u16(12,0x8100); u16(14,0x0064);
    forward_tick();
    uint16_t t=(PacketByte[12]<<8)|PacketByte[13];
    if(t==0x8100) NG("仍有TPID"); else OK();
}

int main(void){
    printf("\n========================================\n");
    printf("  8m Switch Chip - C Model Testbench\n");
    printf("========================================\n\n");
    test_vlan_parse();
    test_bcast();
    test_ucast_flood();
    test_untag();
    printf("\n========================================\n");
    printf("  %d tests: %d PASS, %d FAIL\n",g_ok+g_ng,g_ok,g_ng);
    printf("========================================\n");
    return g_ng?1:0;
}
