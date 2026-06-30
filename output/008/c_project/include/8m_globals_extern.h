#ifndef _8M_GLOBALS_EXTERN_H_
#define _8M_GLOBALS_EXTERN_H_

#include <stdint.h>

Ds1qPriorMap_entry_t Ds1qPriorMap;
DsAcl_entry_t DsAcl;
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
extern uint32_t giTpid;
extern uint32_t piDestPort;
extern uint32_t piIsLoopDetect;
extern uint32_t piLoopTtl;
extern uint32_t piOutNoVlan;
extern uint32_t piPktLength;
extern uint32_t piPktTagged;
extern uint32_t piPrior;
extern uint32_t piSrcPort;
extern uint32_t piVlanId;
extern uint32_t prExistVlan;
extern uint32_t prIpDa;
extern uint32_t prIpDscp;
extern uint32_t prIpSa;
extern uint32_t prIsArp;
extern uint32_t prIsIpv4;
extern uint32_t prIsIpv6;
extern uint32_t prIsLoopDetection;
extern uint32_t prLoopTtl;
extern uint64_t prMacDa;
extern uint64_t prMacSa;
extern uint32_t prVlanId;
extern uint32_t prVlanPrior;

#endif /* _8M_GLOBALS_EXTERN_H_ */
