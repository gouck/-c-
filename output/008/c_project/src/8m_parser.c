#include "../include/reg_drv_common.h"
#include "../include/reg_drv_tinyReg.h"
#include "../include/reg_drv_tinyReg2.h"
#include "../include/8m_runtime.h"
#include "../include/8m_globals_extern.h"
#include <stdint.h>
#include <string.h>

/* Cross-file function prototypes */
void parser(uint8_t *PacketByte);
void switchX(void);
void egress(void);
void forward_tick(void);
void updateStormCtrl_tick(void);
void normalAging_tick(void);
void fastAging_tick(void);
void sendLoopDetect_tick(void);

void parser(uint8_t *PacketByte) {
        uint32_t giPldOffset = 0; /* var-decl */
        uint32_t prIsUnknownPkt = 0; /* auto-declared */
        prMacDa = ((uint64_t)(PacketByte[0]) << 40) | (((uint64_t)(PacketByte[1]) << 32) | (((uint64_t)(PacketByte[2]) << 24) | (((uint64_t)(PacketByte[3]) << 16) | (((uint64_t)(PacketByte[4]) << 8) | (PacketByte[5])))));
        prMacSa = ((uint64_t)(PacketByte[6]) << 40) | (((uint64_t)(PacketByte[7]) << 32) | (((uint64_t)(PacketByte[8]) << 24) | (((uint64_t)(PacketByte[9]) << 16) | (((uint64_t)(PacketByte[10]) << 8) | (PacketByte[11])))));
        giTpid = ((uint64_t)(PacketByte[12]) << 8) | (PacketByte[13]);
        giPldOffset = 14;
        if ((((giTpid == 0x8100) || (giTpid == 0x9100)) || (giTpid == 0x88a8))) {
            prVlanPrior = BITFIELD_GET(PacketByte[giPldOffset], 7, 5);
            prVlanId = ((uint64_t)(BITFIELD_GET(PacketByte[giPldOffset], 3, 0)) << 8) | (BITFIELD_GET(PacketByte[(giPldOffset + 1)], 7, 0));
            prExistVlan = 1;
            giTpid = ((uint64_t)(PacketByte[(giPldOffset + 2)]) << 1) | (PacketByte[(giPldOffset + 3)]);
            giPldOffset += 4;
    }
        if ((giTpid == 0x8899)) {
            prLoopTtl = BITFIELD_GET(PacketByte[(giPldOffset + 3)], 3, 0);
            prIsLoopDetection = 1;
    } else if (((giTpid == 0x0806) || (giTpid == 0x8035))) {
            prIsArp = 1;
    } else if ((giTpid == 0x0800)) {
            prIsIpv4 = 1;
            prIpDscp = BITFIELD_GET(PacketByte[(giPldOffset + 1)], 7, 2);
            prIpSa = _concat_range((giPldOffset + 12), (giPldOffset + 15));
            prIpDa = _concat_range((giPldOffset + 16), (giPldOffset + 19));
    } else if ((giTpid == 0x86dd)) {
            prIsIpv6 = 1;
            prIpDscp = ((uint64_t)(BITFIELD_GET(PacketByte[giPldOffset], 3, 0)) << 2) | (BITFIELD_GET(PacketByte[(giPldOffset + 1)], 7, 6));
            prIpSa = _concat_range((giPldOffset + 8), (giPldOffset + 23));
            prIpDa = _concat_range((giPldOffset + 24), (giPldOffset + 39));
    } else {
            prIsUnknownPkt = 1;
    }
}
