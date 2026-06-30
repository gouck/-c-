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

void forward_tick(void) {
        parser(PacketByte);
        switchX();
        egress();
}

void updateStormCtrl_tick(void) {
        static uint32_t giStormIdx = 0;
        giStormIdx = 0;
        while (1) {
            if (StormCfgCtl.enable) {
                memcpy(&DsStormCtrl, &DsStormCtrl_mem[giStormIdx], sizeof(DsStormCtrl_entry_t));
                if (DsStormCtrl.enable) {
                    DsStormCtrl.counter += BITFIELD_GET(DsStormCtrl.step, 31, 0);
                    if ((BITFIELD_GET(DsStormCtrl.counter, 31, 0) > BITFIELD_GET(DsStormCtrl.cntThrd, 31, 0))) {
                        DsStormCtrl.counter = DsStormCtrl.cntThrd;
                }
            }
        }
            (giStormIdx++);
            static uint32_t _delay = 0;
        if (_delay > 0) {{ _delay--; return; }}
        _delay = BITFIELD_GET(StormCfgCtl.delayInterval, 31, 0);
    }
}

void normalAging_tick(void) {
        static uint32_t giAgingIdx = 0;
        static uint32_t giCycleCnt = 0;
        giAgingIdx = 0;
        while (1) {
            if ((L2AgingCtl.agingEn && (!L2AgingCtl.fastAgingEn))) {
                ({ uint32_t _tmp = BITFIELD_GET(giCycleCnt, 31, 0); uint32_t _res = _tmp++; BITFIELD_SET(giCycleCnt, 31, 0, _tmp); _res; });
                if ((giCycleCnt >= BITFIELD_GET(L2AgingCtl.cycleThrd, 31, 0))) {
                    giCycleCnt = 0;
                    memcpy(&DsMacAging, &DsMacAging_mem[BITFIELD_GET(giAgingIdx, 10, 2)], sizeof(DsMacAging_entry_t));
                    memcpy(&DsMacValid, &DsMacValid_mem[BITFIELD_GET(giAgingIdx, 10, 2)], sizeof(DsMacValid_entry_t));
                    memcpy(&DsMacStatic, &DsMacStatic_mem[BITFIELD_GET(giAgingIdx, 10, 2)], sizeof(DsMacStatic_entry_t));
                    if ((((DsMacStatic.__static) >> (BITFIELD_GET(giAgingIdx, 1, 0))) & 1)) {
                } else if ((FIELD_INDEX_GET(DsMacAging, aging, BITFIELD_GET(giAgingIdx, 1, 0)) < 3)) {
                        ({ uint32_t _tmp = FIELD_INDEX_GET(DsMacAging, aging, BITFIELD_GET(giAgingIdx, 1, 0)); uint32_t _res = _tmp++; switch (BITFIELD_GET(giAgingIdx, 1, 0) & 0x3) { case 0: DsMacAging.aging0 = _tmp; break; case 1: DsMacAging.aging1 = _tmp; break; case 2: DsMacAging.aging2 = _tmp; break; case 3: DsMacAging.aging3 = _tmp; break; } _res; });
                } else if ((((DsMacValid.valid) >> (BITFIELD_GET(giAgingIdx, 1, 0))) & 1)) {
                        BITFIELD_SET(DsMacValid.valid, BITFIELD_GET(giAgingIdx, 1, 0), BITFIELD_GET(giAgingIdx, 1, 0), 0);
                        (L2LearnCtl.sysLearnNum--);
                } else {
                }
                    (giAgingIdx++);
            }
        }
    }
}

void fastAging_tick(void) {
        static int _state = 0;
        static uint32_t giAgingPtr = 0;
        switch (_state) {
            giAgingPtr = 0;
        case 0:
                if ((L2AgingCtl.agingEn && L2AgingCtl.fastAgingEn)) {
                case 1:
                        if (!((giAgingPtr <= 0x7ff))) { _state = 2; break; }
                        memcpy(&DsMacValid, &DsMacValid_mem[BITFIELD_GET(giAgingPtr, 10, 2)], sizeof(DsMacValid_entry_t));
                        memcpy(&DsMacStatic, &DsMacStatic_mem[BITFIELD_GET(giAgingPtr, 10, 2)], sizeof(DsMacStatic_entry_t));
                        if (((((DsMacValid.valid) >> (BITFIELD_GET(giAgingPtr, 1, 0))) & 1) && (!(((DsMacStatic.__static) >> (BITFIELD_GET(giAgingPtr, 1, 0))) & 1)))) {
                            if (L2AgingCtl.fastAgingAll) {
                                BITFIELD_SET(DsMacValid.valid, BITFIELD_GET(giAgingPtr, 1, 0), BITFIELD_GET(giAgingPtr, 1, 0), 0);
                                (L2LearnCtl.sysLearnNum--);
                        } else if (L2AgingCtl.fastAgingByPort) {
                                memcpy(&DsMac, &DsMac_mem[BITFIELD_GET(giAgingPtr, 10, 0)], sizeof(DsMac_entry_t));
                                if ((((DsMac.destMap) >> (BITFIELD_GET(L2AgingCtl.portId, 3, 0))) & 1)) {
                                    BITFIELD_SET(DsMacValid.valid, BITFIELD_GET(giAgingPtr, 1, 0), BITFIELD_GET(giAgingPtr, 1, 0), 0);
                                    (L2LearnCtl.sysLearnNum--);
                            }
                        }
                    }
                        (giAgingPtr++);
                        break; /* stay in state 1 next tick */
                    L2AgingCtl.fastAgingEn = 0;
                }
        }
}

void sendLoopDetect_tick(void) {
        if (LoopDetectCtl.en) {
            static uint32_t _delay = 0;
        if (_delay > 0) {{ _delay--; return; }}
        _delay = BITFIELD_GET(LoopDetectCtl.detectInterval, 31, 0);
            send_packet(NULL, 0); /* TODO */
    }
}
