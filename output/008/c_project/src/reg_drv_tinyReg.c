#include "reg_drv_tinyReg.h"

L2AgingCtl_t L2AgingCtl;
L2LearnCtl_t L2LearnCtl;
LoopDetectCtl_t LoopDetectCtl;
MirrorCtl_t MirrorCtl;
PriorAssignCtl_t PriorAssignCtl;
StormCfgCtl_t StormCfgCtl;
VlanIdCamCtl_t VlanIdCamCtl;

/* =========================================================
 * reg_init – apply default register values at startup
 * ========================================================= */
void reg_init(void) {
    /* ---- L2AgingCtl ---- */
    L2AgingCtl.fastAgingEn = 0;  /* default=0, fastAgingEn register */
    L2AgingCtl.agingEn = 1;  /* default=1, agingEn register */
    L2AgingCtl.fastAgingAll = 1;  /* default=1, fastAgingAll register */
    L2AgingCtl.fastAgingByPort = 0;  /* default=0, fastAgingByPort register */
    L2AgingCtl.portId = 0;  /* default=4'b0, portId register */
    L2AgingCtl.cycleThrd = 0;  /* default=32'b0, cycleThrd register */
    /* ---- L2LearnCtl ---- */
    L2LearnCtl.sysLearnNum = 0;  /* default=16'b0, sysLearnNum register */
    L2LearnCtl.lruEn = 0;  /* default=1'b0, lruEn register */
    /* ---- LoopDetectCtl ---- */
    LoopDetectCtl.en = 0;  /* default=0, en register */
    LoopDetectCtl.ttl = 0;  /* default=4'b0, ttl register */
    LoopDetectCtl.loopMacHi = 0;  /* default=16'b0, loopMacHi register */
    LoopDetectCtl.loopMacLo = 0;  /* default=32'b0, loopMacLo register */
    LoopDetectCtl.detectInterval = 0;  /* default=32'b0, detectInterval register */
    /* ---- MirrorCtl ---- */
    MirrorCtl.srcMirrorPort = 0;  /* default=4'b0, srcMirrorPort register */
    MirrorCtl.vlanMirrorPort = 0;  /* default=4'b0, vlanMirrorPort register */
    /* ---- PriorAssignCtl ---- */
    PriorAssignCtl.ipDscpEn = 0;  /* default=1'b0, ipDscpEn register */
    PriorAssignCtl.ipAddrEn = 0;  /* default=1'b0, ipAddrEn register */
    PriorAssignCtl.macDaEn = 0;  /* default=1'b0, macDaEn register */
    PriorAssignCtl.rldpEn = 0;  /* default=1'b0, rldpEn register */
    PriorAssignCtl.rldpPrior = 0;  /* default=2'b0, rldpPrior register */
    PriorAssignCtl.dscpWeight = 0;  /* default=2'b0, dscpWeight register */
    PriorAssignCtl.vlanWeight = 0;  /* default=2'b0, vlanWeight register */
    PriorAssignCtl.portWeight = 0;  /* default=2'b0, portWeight register */
    PriorAssignCtl.ip0AddrPrior = 0;  /* default=2'b0, ip0AddrPrior register */
    PriorAssignCtl.ip1AddrPrior = 0;  /* default=2'b0, ip1AddrPrior register */
    PriorAssignCtl.ip0AddrBit127To96 = 0;  /* default=32'b0, ip0AddrBit127To96 register */
    PriorAssignCtl.ip0MaskBit127To96 = 0;  /* default=32'b0, ip0MaskBit127To96 register */
    PriorAssignCtl.ip1AddrBit127To96 = 0;  /* default=32'b0, ip1AddrBit127To96 register */
    PriorAssignCtl.ip1MaskBit127To96 = 0;  /* default=32'b0, ip1MaskBit127To96 register */
    PriorAssignCtl.ip0AddrBit95To64 = 0;  /* default=32'b0, ip0AddrBit95To64 register */
    PriorAssignCtl.ip0MaskBit95To64 = 0;  /* default=32'b0, ip0MaskBit95To64 register */
    PriorAssignCtl.ip1AddrBit95To64 = 0;  /* default=32'b0, ip1AddrBit95To64 register */
    PriorAssignCtl.ip1MaskBit95To64 = 0;  /* default=32'b0, ip1MaskBit95To64 register */
    /* ---- StormCfgCtl ---- */
    StormCfgCtl.enable = 0;  /* default=1'b0, enable register */
    StormCfgCtl.delayInterval = 0;  /* default=32'b0, delayInterval register */
    /* ---- VlanIdCamCtl ---- */
    VlanIdCamCtl.vlanId0 = 0;  /* default=12'b0, vlanId0 register */
    VlanIdCamCtl.vlanId1 = 0;  /* default=12'b0, vlanId1 register */
    VlanIdCamCtl.vlanId2 = 0;  /* default=12'b0, vlanId2 register */
    VlanIdCamCtl.vlanId3 = 0;  /* default=12'b0, vlanId3 register */
    VlanIdCamCtl.vlanId4 = 0;  /* default=12'b0, vlanId4 register */
    VlanIdCamCtl.vlanId5 = 0;  /* default=12'b0, vlanId5 register */
    VlanIdCamCtl.vlanId6 = 0;  /* default=12'b0, vlanId6 register */
    VlanIdCamCtl.vlanId7 = 0;  /* default=12'b0, vlanId7 register */
    VlanIdCamCtl.vlanId8 = 0;  /* default=12'b0, vlanId8 register */
    VlanIdCamCtl.vlanId9 = 0;  /* default=12'b0, vlanId9 register */
    VlanIdCamCtl.vlanId10 = 0;  /* default=12'b0, vlanId10 register */
    VlanIdCamCtl.vlanId11 = 0;  /* default=12'b0, vlanId11 register */
    VlanIdCamCtl.vlanId12 = 0;  /* default=12'b0, vlanId12 register */
    VlanIdCamCtl.vlanId13 = 0;  /* default=12'b0, vlanId13 register */
    VlanIdCamCtl.vlanId14 = 0;  /* default=12'b0, vlanId14 register */
    VlanIdCamCtl.vlanId15 = 0;  /* default=12'b0, vlanId15 register */
}

