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

void egress() {
        uint32_t newVlanTag = 0; /* var-decl */
        if (piIsLoopDetect) {
            { uint64_t _tmp = BITFIELD_GET(LoopDetectCtl.loopMacHi, 47, 0); memcpy(&(PacketByte[6]), &_tmp, (11)-(6)+1); }
            { uint64_t _tmp = ((uint64_t)(0) << 4) | (piLoopTtl); memcpy(&(PacketByte[17]), &_tmp, (17)-(17)+1); }
    } else {
            memcpy(&DsDestPort, &DsPort_mem[piDestPort], sizeof(DsPort_entry_t));
            newVlanTag = ((uint64_t)(0x8100) << 16) | (((uint64_t)(0) << 15) | (((uint64_t)(piPrior) << 13) | (((uint64_t)(0) << 12) | (piVlanId))));
            if (DsDestPort.updateMacSa) {
                { uint64_t _tmp = ((uint64_t)(BITFIELD_GET(DsDestPort.portMacHi, 47, 32)) << 32) | (BITFIELD_GET(DsDestPort.portMacLo, 31, 0)); memcpy(&(PacketByte[6]), &_tmp, (11)-(6)+1); }
        }
            if (piOutNoVlan) {
                if (piPktTagged) {
                    memmove(&(PacketByte)[12], &(PacketByte)[(15)+1], sizeof(PacketByte)-(15)-1);
            }
        } else {
                if (piPktTagged) {
                    memcpy(&(PacketByte[12]), &(newVlanTag), (15)-(12)+1);
            } else {
                    memmove(&(PacketByte[(11)+sizeof(newVlanTag)]), &(PacketByte[11]), sizeof(PacketByte)-(11)); memcpy(&(PacketByte[11]), &(newVlanTag), sizeof(newVlanTag));
            }
        }
    }
}
