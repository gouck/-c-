#include "../include/reg_drv_common.h"
#include "../include/reg_drv_tinyReg.h"
#include "../include/reg_drv_tinyReg2.h"
#include <stdint.h>
#include <string.h>

/* =================================================== */
/*  8m auto-generated C code                             */
/* =================================================== */


__attribute__((weak)) void enqueue_packet(void *pkt, int len) {}
__attribute__((weak)) void send_packet(void *pkt, int len) {}

/* Global table-read entry variables */
Ds1qPriorMap_entry_t Ds1qPriorMap;
DsAcl_entry_t DsAcl;           /* [text4新增] ACL表读缓存 */
DsPort_entry_t DsDestPort;
DsDscpPriorMap_entry_t DsDscpPriorMap;
DsMac_entry_t DsMac;
DsMacAging_entry_t DsMacAging;
DsMac_entry_t DsMacFwd;
DsMacKey_entry_t DsMacKey;
DsMac_entry_t DsMacLrn;
DsMacStatic_entry_t DsMacStatic;
DsMacValid_entry_t DsMacValid;
DsPort_entry_t DsPort;
DsStormCtrl_entry_t DsStormCtrl;
DsVlan_entry_t DsVlan;

/* Cross-function shared variables (parser → switchX → egress) */
uint32_t giTpid = 0;
uint32_t piDestPort = 0;
uint32_t piIsLoopDetect = 0;
uint32_t piLoopTtl = 0;
uint32_t piOutNoVlan = 0;
uint32_t piPktLength = 0;
uint32_t piPktTagged = 0;
uint32_t piPrior = 0;
uint32_t piSrcPort = 0;
uint32_t piVlanId = 0;
uint32_t prExistVlan = 0;
uint32_t prIpDa = 0;
uint32_t prIpDscp = 0;
uint32_t prIpSa = 0;
uint32_t prIsArp = 0;
uint32_t prIsIpv4 = 0;
uint32_t prIsIpv6 = 0;
uint32_t prIsLoopDetection = 0;
uint32_t prLoopTtl = 0;
uint64_t prMacDa = 0;
uint64_t prMacSa = 0;
uint32_t prVlanId = 0;
uint32_t prVlanPrior = 0;

void forward_tick(void);
void updateStormCtrl_tick(void);
void normalAging_tick(void);
void fastAging_tick(void);
void sendLoopDetect_tick(void);
void egress(void);
void parser(uint8_t *PacketByte);
void switchX(void);

