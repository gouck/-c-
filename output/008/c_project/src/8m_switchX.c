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

void switchX() {
        uint32_t giAclIdx = 0; /* var-decl */
        uint32_t giFid = 0; /* var-decl */
        uint32_t giHashIdx = 0; /* var-decl */
        uint32_t giIpAddr0Seg = 0; /* var-decl */
        uint32_t giIpAddr1Seg = 0; /* var-decl */
        uint32_t giLrnHash = 0; /* var-decl */
        uint32_t giLruFlag = 0; /* var-decl */
        uint32_t giQid = 0; /* var-decl */
        uint32_t giStormSubIdx = 0; /* var-decl */
        uint32_t giVid = 0; /* var-decl */
        uint32_t giVlanIdx = 0; /* var-decl */
        uint32_t piAft = 0; /* var-decl */
        uint32_t piDscpPrior = 0; /* var-decl */
        uint32_t piFid = 0; /* var-decl */
        uint32_t piFwdBmp = 0; /* var-decl */
        uint32_t piIpAddrPrior = 0; /* var-decl */
        uint32_t piMacDaPrior = 0; /* var-decl */
        uint32_t piPortPrior = 0; /* var-decl */
        uint32_t piPortVid = 0; /* var-decl */
        uint32_t piUntagFlag = 0; /* var-decl */
        uint32_t piVlanMember = 0; /* var-decl */
        uint32_t piVlanPrior = 0; /* var-decl */
        uint32_t giDscpPriorAssign = 0; /* auto-declared */
        uint32_t giLrnHit = 0; /* auto-declared */
        uint32_t giLrnNew = 0; /* auto-declared */
        uint32_t giLrnSubIdx = 0; /* auto-declared */
        uint32_t giLruLrn = 0; /* auto-declared */
        uint32_t giPriorWeight = 0; /* auto-declared */
        uint32_t giStormCtlIdx = 0; /* auto-declared */
        uint32_t giVlanHit = 0; /* auto-declared */
        uint32_t giVlanPriorAssigne = 0; /* auto-declared */
        uint32_t giVlanTagged = 0; /* auto-declared */
        uint32_t i = 0; /* auto-declared */
        uint32_t newDsMacEntry = 0; /* auto-declared */
        uint32_t newDsMacKeyEntry = 0; /* auto-declared */
        uint32_t pi1qBasedVlan = 0; /* auto-declared */
        uint32_t pi1qPriorEn = 0; /* auto-declared */
        uint32_t piAllowBrg2Src = 0; /* auto-declared */
        uint32_t piBcast = 0; /* auto-declared */
        uint32_t piBrgHit = 0; /* auto-declared */
        uint32_t piDiscard = 0; /* auto-declared */
        uint32_t piEgressFilter = 0; /* auto-declared */
        uint32_t piFlooding = 0; /* auto-declared */
        uint32_t piLeakyArp = 0; /* auto-declared */
        uint32_t piLeakyBcast = 0; /* auto-declared */
        uint32_t piLeakyMcast = 0; /* auto-declared */
        uint32_t piLeakyMirror = 0; /* auto-declared */
        uint32_t piLeakyUcast = 0; /* auto-declared */
        uint32_t piLrnDisable = 0; /* auto-declared */
        uint32_t piMcast = 0; /* auto-declared */
        uint32_t piPortMirror = 0; /* auto-declared */
        uint32_t piRmaMode = 0; /* auto-declared */
        uint32_t piVlanMirror = 0; /* auto-declared */
        memcpy(&DsPort, &DsPort_mem[piSrcPort], sizeof(DsPort_entry_t));
        piPortVid = DsPort.portVid;
        pi1qBasedVlan = DsPort.dot1qBasedVlan;
        piAft = DsPort.aft;
        piLrnDisable = DsPort.lrnDisable;
        piAllowBrg2Src = DsPort.allowBrg2Src;
        piPortPrior = BITFIELD_GET(DsPort.prior, 1, 0);
        piRmaMode = DsPort.rmaMode;
        piPortMirror = DsPort.mirrorEn;
        giVid = piPortVid;
        if (((pi1qBasedVlan && (prExistVlan != 0)) && (prVlanId != 0))) {
            giVid = prVlanId;
            if ((DsPort.strictPvid && (prVlanId != piPortVid))) {
                piDiscard = 1;
        }
    }
        giVlanIdx = 0;
        giVlanHit = 0;
        for (i = 0; (i < 16); (i++)) {
            if ((giVid == FIELD_INDEX_GET(VlanIdCamCtl, vlanId, i))) {
                giVlanIdx = i;
                giVlanHit = 1;
                break;
        }
    }
        if (giVlanHit) {
            memcpy(&DsVlan, &DsVlan_mem[giVlanIdx], sizeof(DsVlan_entry_t));
            piFwdBmp = ((uint64_t)(0) << 10) | (BITFIELD_GET(DsVlan.vlanBmp, 9, 0));
            piVlanMember = DsVlan.vlanBmp;
            piFid = BITFIELD_GET(DsVlan.fid, 11, 0);
            pi1qPriorEn = DsVlan.dot1qPriorEn;
            memcpy(&Ds1qPriorMap, &Ds1qPriorMap_mem[prVlanPrior], sizeof(Ds1qPriorMap_entry_t));
            piVlanPrior = BITFIELD_GET(Ds1qPriorMap.prior, 1, 0);
            piUntagFlag = ((uint64_t)(63) << 10) | (BITFIELD_GET(DsVlan.untagFlag, 9, 0));
            piVlanMirror = DsVlan.mirrorEn;
            piEgressFilter = DsVlan.egressFilter;
            piLeakyUcast = DsVlan.leakyUcast;
            piLeakyMcast = DsVlan.leakyMcast;
            piLeakyBcast = DsVlan.leakyBcast;
            piLeakyArp = DsVlan.leakyArp;
            piLeakyMirror = DsVlan.leakyMirror;
    } else {
            piDiscard = 1;
    }
        giVlanTagged = ((prExistVlan != 0) && (prVlanId != 0));
        switch (piAft) {
            case 1: {
                piDiscard = (!giVlanTagged);
                break;
        } break;
            case 2: {
                piDiscard = giVlanTagged;
                break;
        } break;
            case 3: {
                piDiscard = 1;
                break;
        } break;
            default: ; break;
    }
        /* [text4新增] ACL: 遍历DsAcl表，匹配则丢弃 */
        giAclIdx = 0;
        for (i = 0; (i < 32); (i++)) {
            memcpy(&DsAcl, &DsAcl_mem[i], sizeof(DsAcl_entry_t));
            if (((DsAcl.action == 0) && (BITFIELD_GET(DsAcl.etherType, 15, 0) == giTpid))) {
                piDiscard = 1;
        }
    }
        /* [text4新增] STP: Blocking状态端口丢弃 */
        if ((BITFIELD_GET(DsPort.stpState, 2, 0) == 1)) {
            piDiscard = 1;
    }
        piBcast = (prMacDa == 0xffffffffffff);
        piMcast = ((!piBcast) && (((prMacDa) >> (40)) & 1));
        if ((!piDiscard)) {
            if (piMcast) {
                giFid = giVid;
        } else {
                giFid = piFid;
        }
            giHashIdx = hash1(((uint64_t)(giFid) << 48) | (prMacDa));
            memcpy(&DsMacKey, &DsMacKey_mem[giHashIdx], sizeof(DsMacKey_entry_t));
            memcpy(&DsMacValid, &DsMacValid_mem[giHashIdx], sizeof(DsMacValid_entry_t));
            piBrgHit = 0;
            for (i = 0; (i < 4); (i++)) {
                if ((((DsMacKey_get_fid(&(DsMacKey), i) == (giFid)) && (DsMacKey_get_macAddr(&(DsMacKey), i) == (prMacDa))) && (((DsMacValid.valid) >> (i)) & 1))) {
                    memcpy(&DsMacFwd, &DsMac_mem[(((uint32_t)(giHashIdx) << (2)) + i)], sizeof(DsMac_entry_t));
                    piBrgHit = 1;
                    break;
            }
        }
            if (piBrgHit) {
                piMacDaPrior = BITFIELD_GET(DsMacFwd.prior, 1, 0);
                if (DsMacFwd.destDiscard) {
                    piDiscard = 1;
            } else {
                    piFwdBmp = ((uint64_t)(0) << 10) | (BITFIELD_GET(DsMacFwd.destMap, 9, 0));
            }
        } else {
                piFlooding = 1;
        }
            if (piBcast) {
                giStormSubIdx = 3;
        } else if ((piMcast && (!piBrgHit))) {
                giStormSubIdx = 2;
        } else if ((piMcast && piBrgHit)) {
                giStormSubIdx = 1;
        } else if (((!piMcast) && (!piBrgHit))) {
                giStormSubIdx = 0;
        }
            giStormCtlIdx = (((uint32_t)(piSrcPort) << (2)) + BITFIELD_GET(giStormSubIdx, 1, 0));
            memcpy(&DsStormCtrl, &DsStormCtrl_mem[giStormCtlIdx], sizeof(DsStormCtrl_entry_t));
            if (DsStormCtrl.enable) {
                if (DsStormCtrl.usePkt) {
                    if ((BITFIELD_GET(DsStormCtrl.counter, 31, 0) == 0)) {
                        piDiscard = 1;
                } else {
                        (DsStormCtrl.counter--);
                }
            } else {
                    if ((DsStormCtrl.counter < piPktLength)) {
                        piDiscard = 1;
                } else {
                        DsStormCtrl.counter -= piPktLength;
                }
            }
        }
    }
        if (((!piLrnDisable) && (!piDiscard))) {
            giLrnHash = hash1(((uint64_t)(giFid) << 48) | (prMacSa));
            memcpy(&DsMacKey, &DsMacKey_mem[giLrnHash], sizeof(DsMacKey_entry_t));
            memcpy(&DsMacValid, &DsMacValid_mem[giLrnHash], sizeof(DsMacValid_entry_t));
            for (i = 0; (i < 4); (i++)) {
                if ((((DsMacKey_get_fid(&(DsMacKey), i) == (giFid)) && (DsMacKey_get_macAddr(&(DsMacKey), i) == (prMacSa))) && (((DsMacValid.valid) >> (i)) & 1))) {
                    memcpy(&DsMacLrn, &DsMac_mem[(((uint32_t)(giLrnHash) << (2)) + i)], sizeof(DsMac_entry_t));
                    giLrnHit = 1;
                    giLrnSubIdx = i;
                    break;
            } else {
                    giLrnHit = 0;
            }
        }
            if ((!giLrnHit)) {
                giLrnNew = 0;
                for (i = 0; (i < 4); (i++)) {
                    if ((!(((DsMacValid_mem[giLrnHash].valid) >> (i)) & 1))) {
                        giLrnNew = 1;
                        giLrnSubIdx = i;
                        break;
                }
            }
        }
            if (((!giLrnHit) && L2LearnCtl.lruEn)) {
                memcpy(&DsMacAging, &DsMacAging_mem[giLrnHash], sizeof(DsMacAging_entry_t));
                giLruFlag = 0;
                for (i = 0; (i < 4); (i++)) {
                    if ((giLruFlag <= FIELD_INDEX_GET(DsMacAging, aging, i))) {
                        giLruFlag = FIELD_INDEX_GET(DsMacAging, aging, i);
                        giLruLrn = 1;
                        giLrnSubIdx = i;
                }
            }
        }
            newDsMacKeyEntry = ((uint64_t)(prMacSa) << 12) | (giFid);
            newDsMacEntry = ((uint64_t)(((uint32_t)(1) << (piSrcPort))) << 4) | (((uint64_t)(0) << 3) | (((uint64_t)(0) << 2) | (0)));
            if (giLrnHit) {
                memcpy(&DsMac_mem[((uint64_t)(giHashIdx) << 2) | (giLrnSubIdx)], &newDsMacEntry, sizeof(DsMac_entry_t));
                switch (giLrnSubIdx & 0x3) {
    case 0: DsMacAging_mem[giLrnHash].aging0 = 0; break;
    case 1: DsMacAging_mem[giLrnHash].aging1 = 0; break;
    case 2: DsMacAging_mem[giLrnHash].aging2 = 0; break;
    case 3: DsMacAging_mem[giLrnHash].aging3 = 0; break;
}
        } else if ((giLrnNew || giLruLrn)) {
                /* [text4新增] 端口安全: MAC数量达上限则跳过学习 */
                if (((BITFIELD_GET(DsPort.maxMacNum, 7, 0) > 0) && (L2LearnCtl.sysLearnNum >= BITFIELD_GET(DsPort.maxMacNum, 7, 0)))) {
            } else {
                    memcpy(&DsMacKey_mem[giLrnHash], &newDsMacKeyEntry, sizeof(DsMacKey_entry_t));
                    memcpy(&DsMac_mem[((uint64_t)(giLrnHash) << 2) | (giLrnSubIdx)], &newDsMacEntry, sizeof(DsMac_entry_t));
                    switch (giLrnSubIdx & 0x3) {
    case 0: DsMacAging_mem[giLrnHash].aging0 = 0; break;
    case 1: DsMacAging_mem[giLrnHash].aging1 = 0; break;
    case 2: DsMacAging_mem[giLrnHash].aging2 = 0; break;
    case 3: DsMacAging_mem[giLrnHash].aging3 = 0; break;
}
                    BITFIELD_SET(DsMacValid_mem[giLrnHash].valid, giLrnSubIdx, giLrnSubIdx, 1);
                    if (giLrnNew) {
                        (L2LearnCtl.sysLearnNum++);
                }
            }
        }
    }
        if (((prIsIpv4 || prIsIpv6) && PriorAssignCtl.ipDscpEn)) {
            memcpy(&DsDscpPriorMap, &DsDscpPriorMap_mem[BITFIELD_GET(prIpDscp, 5, 0)], sizeof(DsDscpPriorMap_entry_t));
            piDscpPrior = BITFIELD_GET(DsDscpPriorMap.prior, 1, 0);
    }
        if ((PriorAssignCtl.ipAddrEn && (prIsIpv4 || prIsIpv6))) {
            giIpAddr0Seg = (BITFIELD_GET(PriorAssignCtl.ip0AddrBit127To96, 127, 0) & BITFIELD_GET(PriorAssignCtl.ip0MaskBit127To96, 127, 0));
            giIpAddr1Seg = (BITFIELD_GET(PriorAssignCtl.ip1AddrBit127To96, 127, 0) & BITFIELD_GET(PriorAssignCtl.ip1MaskBit127To96, 127, 0));
            if ((((giIpAddr0Seg == prIpSa) & PriorAssignCtl.ip0MaskBit127To96) || ((giIpAddr0Seg == prIpDa) & PriorAssignCtl.ip0MaskBit127To96))) {
                piIpAddrPrior = BITFIELD_GET(PriorAssignCtl.ip0AddrPrior, 1, 0);
        } else if ((((giIpAddr1Seg == prIpSa) & PriorAssignCtl.ip1MaskBit127To96) || ((giIpAddr1Seg == prIpDa) & PriorAssignCtl.ip1MaskBit127To96))) {
                piIpAddrPrior = BITFIELD_GET(PriorAssignCtl.ip1AddrPrior, 1, 0);
        }
    }
        if ((PriorAssignCtl.rldpEn && prIsLoopDetection)) {
            piPrior = BITFIELD_GET(PriorAssignCtl.rldpPrior, 1, 0);
    } else if (PriorAssignCtl.macDaEn) {
            piPrior = piMacDaPrior;
    } else if (PriorAssignCtl.ipAddrEn) {
            piPrior = piIpAddrPrior;
    } else {
            if (((BITFIELD_GET(PriorAssignCtl.portWeight, 1, 0) == BITFIELD_GET(PriorAssignCtl.vlanWeight, 1, 0)) && (PriorAssignCtl.portWeight == BITFIELD_GET(PriorAssignCtl.dscpWeight, 1, 0)))) {
                piPrior = ((piPortPrior)>(piVlanPrior)?((piPortPrior)>(piDscpPrior)?(piPortPrior):(piDscpPrior)):((piVlanPrior)>(piDscpPrior)?(piVlanPrior):(piDscpPrior)));
        } else {
                giVlanPriorAssigne = 0;
                giDscpPriorAssign = 0;
                if (((BITFIELD_GET(PriorAssignCtl.vlanWeight, 1, 0) >= BITFIELD_GET(PriorAssignCtl.portWeight, 1, 0)) && (BITFIELD_GET(PriorAssignCtl.vlanWeight, 1, 0) >= BITFIELD_GET(PriorAssignCtl.dscpWeight, 1, 0)))) {
                    giVlanPriorAssigne = 1;
                    giPriorWeight = PriorAssignCtl.vlanWeight;
            } else if (((BITFIELD_GET(PriorAssignCtl.dscpWeight, 1, 0) >= BITFIELD_GET(PriorAssignCtl.portWeight, 1, 0)) && (BITFIELD_GET(PriorAssignCtl.dscpWeight, 1, 0) >= BITFIELD_GET(PriorAssignCtl.vlanWeight, 1, 0)))) {
                    giPriorWeight = PriorAssignCtl.dscpWeight;
                    giDscpPriorAssign = 1;
            }
                if (giVlanPriorAssigne) {
                    piPrior = piVlanPrior;
                    if ((PriorAssignCtl.vlanWeight == PriorAssignCtl.portWeight)) {
                        piPrior = ((piVlanPrior >= piPortPrior) ? piVlanPrior : piPortPrior);
                } else if ((PriorAssignCtl.vlanWeight == PriorAssignCtl.dscpWeight)) {
                        piPrior = ((piVlanPrior >= piDscpPrior) ? piVlanPrior : piDscpPrior);
                }
            } else if (giDscpPriorAssign) {
                    piPrior = piDscpPrior;
                    if ((PriorAssignCtl.dscpWeight == PriorAssignCtl.portWeight)) {
                        piPrior = ((piDscpPrior >= piPortPrior) ? piDscpPrior : piPortPrior);
                } else if ((PriorAssignCtl.dscpWeight == PriorAssignCtl.vlanWeight)) {
                        piPrior = ((piDscpPrior >= piVlanPrior) ? piDscpPrior : piVlanPrior);
                }
            } else {
                    piPrior = piPortPrior;
                    if ((PriorAssignCtl.portWeight == PriorAssignCtl.vlanWeight)) {
                        piPrior = ((piPortPrior >= piVlanPrior) ? piPortPrior : piVlanPrior);
                } else if ((PriorAssignCtl.portWeight == PriorAssignCtl.dscpWeight)) {
                        piPrior = ((piPortPrior >= piDscpPrior) ? piPortPrior : piDscpPrior);
                }
            }
        }
    }
        if ((piMcast && (BITFIELD_GET(prMacDa, 47, 8) == 0x0180c20000))) {
            switch (BITFIELD_GET(prMacDa, 7, 0)) {
                case 0x00: if (piRmaMode) {
                    piDiscard = 1;
            } break;
                case 0x03: if (piRmaMode) {
                    piDiscard = 1;
            } break;
                case 0x0e: if (piRmaMode) {
                    piDiscard = 1;
            } break;
                case 0x11: case 0x12: case 0x13: case 0x14: case 0x15: case 0x16: case 0x17: case 0x18: case 0x19: case 0x1a: case 0x1b: case 0x1c: case 0x1d: case 0x1e: case 0x1f: if (piRmaMode) {
                    piDiscard = 1;
            } break;
                case 0x21: if (piRmaMode) {
                    piDiscard = 1;
            } break;
                case 0x31: case 0x32: case 0x33: case 0x34: case 0x35: case 0x36: case 0x37: case 0x38: case 0x39: case 0x3a: case 0x3b: case 0x3c: case 0x3d: case 0x3e: case 0x3f: if (piRmaMode) {
                    piDiscard = 1;
            } break;
        }
    }
        if (piFlooding) {
            piFwdBmp = ((uint64_t)(0) << 10) | (piVlanMember);
    }
        if (piPortMirror) {
            piFwdBmp |= ((uint32_t)(1) << (BITFIELD_GET(MirrorCtl.srcMirrorPort, 3, 0)));
    }
        if (piVlanMirror) {
            piFwdBmp |= ((uint32_t)(1) << (BITFIELD_GET(MirrorCtl.vlanMirrorPort, 3, 0)));
    }
        if ((prIsLoopDetection && ((prLoopTtl <= 1) || (prMacSa == LoopDetectCtl.loopMacHi)))) {
            piDiscard = 1;
    }
        if ((!piAllowBrg2Src)) {
            piFwdBmp &= (~((uint32_t)(1) << (piSrcPort)));
    }
        for (i = 0; (i < 8); (i++)) {
            if (((piEgressFilter && (((piFwdBmp) >> (i)) & 1)) && (!(((piVlanMember) >> (i)) & 1)))) {
                BITFIELD_SET(piFwdBmp, i, i, 0);
                if ((((((piBrgHit && piLeakyUcast) || (piMcast && piLeakyMcast)) || (piBcast && piLeakyBcast)) || (prIsArp && piLeakyArp)) || ((piPortMirror || piVlanMirror) && piLeakyMirror))) {
                    BITFIELD_SET(piFwdBmp, i, i, 1);
            }
        }
    }
        if (piDiscard) {
            piFwdBmp = 0;
    }
        for (i = 0; (i < 16); (i++)) {
            if ((((piFwdBmp) >> (i)) & 1)) {
                piDestPort = (i & 0x7);
                piVlanId = giVid;
                piPrior = piPrior;
                piOutNoVlan = (((piUntagFlag) >> (i)) & 1);
                piPktTagged = prExistVlan;
                piIsLoopDetect = prIsLoopDetection;
                piLoopTtl = (prLoopTtl - 1);
                piPktLength = piPktLength;
                giQid = ((uint64_t)(i) << 2) | (piPrior);
                enqueue_packet(NULL, 0); /* TODO */
        }
    }
}
