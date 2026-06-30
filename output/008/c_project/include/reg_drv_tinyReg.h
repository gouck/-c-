#ifndef _REG_DRV_TINYREG_H_
#define _REG_DRV_TINYREG_H_

#include <stdint.h>

/* =========================================================
 * Address Macros
 * ========================================================= */

#define DSMAC_ADDR_BASE                     0x2000
#define DSMAC_DEPTH                         2048
#define DSMACAGING_ADDR_BASE                0x3000
#define DSMACAGING_DEPTH                    512
#define DSMACKEY_ADDR_BASE                  0x4000
#define DSMACKEY_DEPTH                      512
#define DSMACSTATIC_ADDR_BASE               0x5000
#define DSMACSTATIC_DEPTH                   512
#define DSMACVALID_ADDR_BASE                0x6000
#define DSMACVALID_DEPTH                    512
#define DSPORT_ADDR_BASE                    0x7000
#define DSPORT_DEPTH                        8
#define DSSTORMCTRL_ADDR_BASE               0x8000
#define DSSTORMCTRL_DEPTH                   32
#define DSVLAN_ADDR_BASE                    0x9000
#define DSVLAN_DEPTH                        16
#define DSACL_ADDR_BASE                     0xA100
#define DSACL_DEPTH                         32

#define L2AGINGCTL_ADDR                     0xA000
#define L2LEARNCTL_ADDR                     0xA020
#define LOOPDETECTCTL_ADDR                  0xA040
#define MIRRORCTL_ADDR                      0xA060
#define PRIORASSIGNCTL_ADDR                 0xA080
#define STORMCFGCTL_ADDR                    0xA0A0
#define VLANIDCAMCTL_ADDR                   0xA0C0

/* =========================================================
 * DsMac  (2048 entries × 1 word)
 * ========================================================= */
typedef struct {
    uint16_t   destMap                  : 10;  /* offset=0, [9:0] */
    uint16_t   destDiscard              : 1 ;  /* offset=0, [10] */
    uint16_t   isMcast                  : 1 ;  /* offset=0, [11] */
    uint16_t   prior                    : 2 ;  /* offset=0, [13:12] */
    uint16_t   __pad0                   : 2 ;  /* padding */
} DsMac_entry_t;

DsMac_entry_t DsMac_mem[2048];

/* =========================================================
 * DsMacAging  (512 entries × 1 word)
 * ========================================================= */
typedef struct {
    uint8_t    aging0                   : 2 ;  /* offset=0, [1:0] */
    uint8_t    aging1                   : 2 ;  /* offset=0, [3:2] */
    uint8_t    aging2                   : 2 ;  /* offset=0, [5:4] */
    uint8_t    aging3                   : 2 ;  /* offset=0, [7:6] */
} DsMacAging_entry_t;

DsMacAging_entry_t DsMacAging_mem[512];

/* =========================================================
 * DsMacKey  (512 entries × 8 words)  [raw word array]
 * ========================================================= */

typedef struct {
    uint32_t word[8];
} DsMacKey_entry_t;

DsMacKey_entry_t DsMacKey_mem[512];

/* ---- DsMacKey inline accessors ---- */

static inline uint16_t DsMacKey_get_fid(DsMacKey_entry_t *e, int g) {
    return (uint16_t)(e->word[g * 2] & 0xFFF);
}

static inline uint64_t DsMacKey_get_macAddr(DsMacKey_entry_t *e, int g) {
    uint64_t hi = ((uint64_t)(e->word[g * 2] >> 16)) & 0xFFFF;
    uint64_t lo = (uint64_t)e->word[g * 2 + 1];
    return (hi << 32) | lo;
}

static inline void DsMacKey_set_fid(DsMacKey_entry_t *e, int g, uint16_t fid) {
    e->word[g * 2] = (e->word[g * 2] & 0xFFFFF000) | (fid & 0xFFF);
}

static inline void DsMacKey_set_macAddr(DsMacKey_entry_t *e, int g, uint64_t mac) {
    e->word[g * 2] = (e->word[g * 2] & 0xFFF) | ((uint32_t)((mac >> 32) & 0xFFFF) << 16);
    e->word[g * 2 + 1] = (uint32_t)(mac & 0xFFFFFFFF);
}

/* =========================================================
 * DsMacStatic  (512 entries × 1 word)
 * ========================================================= */
typedef struct {
    uint8_t    __static                 : 4 ;  /* offset=0, [3:0] */
    uint8_t    __pad0                   : 4 ;  /* padding */
} DsMacStatic_entry_t;

DsMacStatic_entry_t DsMacStatic_mem[512];

/* =========================================================
 * DsMacValid  (512 entries × 1 word)
 * ========================================================= */
typedef struct {
    uint8_t    valid                    : 4 ;  /* offset=0, [3:0] */
    uint8_t    __pad0                   : 4 ;  /* padding */
} DsMacValid_entry_t;

DsMacValid_entry_t DsMacValid_mem[512];

/* =========================================================
 * DsPort  (8 entries × 4 words)
 * ========================================================= */
typedef struct {
    uint32_t   portVid                  : 12;  /* offset=0, [11:0] */
    uint32_t   dot1qBasedVlan           : 1 ;  /* offset=0, [12] */
    uint32_t   aft                      : 2 ;  /* offset=0, [14:13] */
    uint32_t   keepVlanTag              : 1 ;  /* offset=0, [15] */
    uint32_t   portMacHi                : 16;  /* offset=0, [31:16] */
    uint32_t   portMacLo                : 32;  /* offset=1, [31:0] */
    uint16_t   stpState                 : 3 ;  /* offset=2, [2:0] */  /* [text4新增] STP端口状态 */
    uint16_t   maxMacNum                : 8 ;  /* offset=2, [10:3] */ /* [text4新增] 端口安全MAC上限 */
    uint16_t   __pad2                   : 5 ;  /* padding */
    uint8_t    allowBrg2Src             : 1 ;  /* offset=3, [0] */
    uint8_t    lrnDisable               : 1 ;  /* offset=3, [1] */
    uint8_t    prior                    : 2 ;  /* offset=3, [3:2] */
    uint8_t    rmaMode                  : 1 ;  /* offset=3, [4] */
    uint8_t    mirrorEn                 : 1 ;  /* offset=3, [5] */
    uint8_t    updateMacSa              : 1 ;  /* offset=3, [6] */
    uint8_t    strictPvid               : 1 ;  /* offset=3, [7] */
} DsPort_entry_t;

DsPort_entry_t DsPort_mem[8];

/* =========================================================
 * DsStormCtrl  (32 entries × 4 words)
 * ========================================================= */
typedef struct {
    uint8_t    enable                   : 1 ;  /* offset=0, [0] */
    uint8_t    usePkt                   : 1 ;  /* offset=0, [1] */
    uint8_t    __pad0                   : 6 ;  /* padding */
    uint32_t   cntThrd                  : 32;  /* offset=1, [31:0] */
    uint32_t   counter                  : 32;  /* offset=2, [31:0] */
    uint32_t   step                     : 32;  /* offset=3, [31:0] */
} DsStormCtrl_entry_t;

DsStormCtrl_entry_t DsStormCtrl_mem[32];

/* =========================================================
 * DsVlan  (16 entries × 2 words)
 * ========================================================= */
typedef struct {
    uint32_t   fid                      : 12;  /* offset=0, [11:0] */
    uint32_t   vlanBmp                  : 10;  /* offset=0, [21:12] */
    uint32_t   untagFlag                : 10;  /* offset=0, [31:22] */
    uint16_t   leakyUcast               : 1 ;  /* offset=1, [0] */
    uint16_t   leakyMcast               : 1 ;  /* offset=1, [1] */
    uint16_t   leakyBcast               : 1 ;  /* offset=1, [2] */
    uint16_t   leakyArp                 : 1 ;  /* offset=1, [3] */
    uint16_t   leakyMirror              : 1 ;  /* offset=1, [4] */
    uint16_t   egressFilter             : 1 ;  /* offset=1, [5] */
    uint16_t   dot1qPriorEn             : 1 ;  /* offset=1, [6] */
    uint16_t   mirrorEn                 : 1 ;  /* offset=1, [7] */
    uint16_t   prior                    : 2 ;  /* offset=1, [9:8] */
    uint16_t   __pad1                   : 6 ;  /* padding */
} DsVlan_entry_t;

DsVlan_entry_t DsVlan_mem[16];

/* =========================================================
 * [text4新增] DsAcl — ACL过滤表 (32 entries × 3 words)
 * ========================================================= */
typedef struct {
    uint16_t   action                   : 1 ;  /* offset=0, [0] */   /* 0=deny, 1=permit */
    uint16_t   etherType                : 15;  /* offset=0, [15:1] */
    uint32_t   vlanId                   : 12;  /* offset=1, [11:0] */
    uint32_t   srcMacHi                 : 16;  /* offset=1, [27:12] */
    uint32_t   __pad1                   : 4 ;  /* padding */
    uint32_t   srcMacLo                 : 32;  /* offset=2, [31:0] */
} DsAcl_entry_t;

DsAcl_entry_t DsAcl_mem[32];

/* =========================================================
 * L2AgingCtl Register (2 words)
 * ========================================================= */
typedef struct {
    uint8_t    fastAgingEn              : 1 ;  /* offset=0, [0] */  /* default=0 */
    uint8_t    agingEn                  : 1 ;  /* offset=0, [1] */  /* default=1 */
    uint8_t    fastAgingAll             : 1 ;  /* offset=0, [2] */  /* default=1 */
    uint8_t    fastAgingByPort          : 1 ;  /* offset=0, [3] */  /* default=0 */
    uint8_t    portId                   : 4 ;  /* offset=0, [7:4] */  /* default=4'b0 */
    uint32_t   cycleThrd                : 32;  /* offset=1, [31:0] */  /* default=32'b0 */
} L2AgingCtl_t;

extern L2AgingCtl_t L2AgingCtl;

/* =========================================================
 * L2LearnCtl Register (1 word)
 * ========================================================= */
typedef struct {
    uint32_t   sysLearnNum              : 16;  /* offset=0, [15:0] */  /* default=16'b0 */
    uint32_t   lruEn                    : 1 ;  /* offset=0, [16] */  /* default=1'b0 */
    uint32_t   __pad0                   : 15;  /* padding */
} L2LearnCtl_t;

extern L2LearnCtl_t L2LearnCtl;

/* =========================================================
 * LoopDetectCtl Register (3 words)
 * ========================================================= */
typedef struct {
    uint32_t   en                       : 1 ;  /* offset=0, [0] */  /* default=0 */
    uint32_t   ttl                      : 4 ;  /* offset=0, [7:4] */  /* default=4'b0 */
    uint32_t   loopMacHi                : 16;  /* offset=0, [31:16] */  /* default=16'b0 */
    uint32_t   __pad0                   : 11;  /* padding */
    uint32_t   loopMacLo                : 32;  /* offset=1, [31:0] */  /* default=32'b0 */
    uint32_t   detectInterval           : 32;  /* offset=2, [31:0] */  /* default=32'b0 */
} LoopDetectCtl_t;

extern LoopDetectCtl_t LoopDetectCtl;

/* =========================================================
 * MirrorCtl Register (1 word)
 * ========================================================= */
typedef struct {
    uint8_t    srcMirrorPort            : 4 ;  /* offset=0, [3:0] */  /* default=4'b0 */
    uint8_t    vlanMirrorPort           : 4 ;  /* offset=0, [7:4] */  /* default=4'b0 */
} MirrorCtl_t;

extern MirrorCtl_t MirrorCtl;

/* =========================================================
 * PriorAssignCtl Register (17 words)
 * ========================================================= */
typedef struct {
    uint16_t   ipDscpEn                 : 1 ;  /* offset=0, [0] */  /* default=1'b0 */
    uint16_t   ipAddrEn                 : 1 ;  /* offset=0, [1] */  /* default=1'b0 */
    uint16_t   macDaEn                  : 1 ;  /* offset=0, [2] */  /* default=1'b0 */
    uint16_t   rldpEn                   : 1 ;  /* offset=0, [3] */  /* default=1'b0 */
    uint16_t   rldpPrior                : 2 ;  /* offset=0, [5:4] */  /* default=2'b0 */
    uint16_t   dscpWeight               : 2 ;  /* offset=0, [7:6] */  /* default=2'b0 */
    uint16_t   vlanWeight               : 2 ;  /* offset=0, [9:8] */  /* default=2'b0 */
    uint16_t   portWeight               : 2 ;  /* offset=0, [11:10] */  /* default=2'b0 */
    uint16_t   ip0AddrPrior             : 2 ;  /* offset=0, [13:12] */  /* default=2'b0 */
    uint16_t   ip1AddrPrior             : 2 ;  /* offset=0, [15:14] */  /* default=2'b0 */
    uint32_t   ip0AddrBit127To96        : 32;  /* offset=1, [31:0] */  /* default=32'b0 */
    uint32_t   ip0MaskBit127To96        : 32;  /* offset=3, [31:0] */  /* default=32'b0 */
    uint32_t   ip1AddrBit127To96        : 32;  /* offset=5, [31:0] */  /* default=32'b0 */
    uint32_t   ip1MaskBit127To96        : 32;  /* offset=7, [31:0] */  /* default=32'b0 */
    uint32_t   ip0AddrBit95To64         : 32;  /* offset=9, [31:0] */  /* default=32'b0 */
    uint32_t   ip0MaskBit95To64         : 32;  /* offset=11, [31:0] */  /* default=32'b0 */
    uint32_t   ip1AddrBit95To64         : 32;  /* offset=13, [31:0] */  /* default=32'b0 */
    uint32_t   ip1MaskBit95To64         : 32;  /* offset=15, [31:0] */  /* default=32'b0 */
} PriorAssignCtl_t;

extern PriorAssignCtl_t PriorAssignCtl;

/* =========================================================
 * StormCfgCtl Register (2 words)
 * ========================================================= */
typedef struct {
    uint8_t    enable                   : 1 ;  /* offset=0, [0] */  /* default=1'b0 */
    uint8_t    __pad0                   : 7 ;  /* padding */
    uint32_t   delayInterval            : 32;  /* offset=1, [31:0] */  /* default=32'b0 */
} StormCfgCtl_t;

extern StormCfgCtl_t StormCfgCtl;

/* =========================================================
 * VlanIdCamCtl Register (8 words)
 * ========================================================= */
typedef struct {
    uint32_t   vlanId0                  : 12;  /* offset=0, [11:0] */  /* default=12'b0 */
    uint32_t   vlanId1                  : 12;  /* offset=0, [23:12] */  /* default=12'b0 */
    uint32_t   __pad0                   : 8 ;  /* padding */
    uint32_t   vlanId2                  : 12;  /* offset=1, [11:0] */  /* default=12'b0 */
    uint32_t   vlanId3                  : 12;  /* offset=1, [23:12] */  /* default=12'b0 */
    uint32_t   __pad1                   : 8 ;  /* padding */
    uint32_t   vlanId4                  : 12;  /* offset=2, [11:0] */  /* default=12'b0 */
    uint32_t   vlanId5                  : 12;  /* offset=2, [23:12] */  /* default=12'b0 */
    uint32_t   __pad2                   : 8 ;  /* padding */
    uint32_t   vlanId6                  : 12;  /* offset=3, [11:0] */  /* default=12'b0 */
    uint32_t   vlanId7                  : 12;  /* offset=3, [23:12] */  /* default=12'b0 */
    uint32_t   __pad3                   : 8 ;  /* padding */
    uint32_t   vlanId8                  : 12;  /* offset=4, [11:0] */  /* default=12'b0 */
    uint32_t   vlanId9                  : 12;  /* offset=4, [23:12] */  /* default=12'b0 */
    uint32_t   __pad4                   : 8 ;  /* padding */
    uint32_t   vlanId10                 : 12;  /* offset=5, [11:0] */  /* default=12'b0 */
    uint32_t   vlanId11                 : 12;  /* offset=5, [23:12] */  /* default=12'b0 */
    uint32_t   __pad5                   : 8 ;  /* padding */
    uint32_t   vlanId12                 : 12;  /* offset=6, [11:0] */  /* default=12'b0 */
    uint32_t   vlanId13                 : 12;  /* offset=6, [23:12] */  /* default=12'b0 */
    uint32_t   __pad6                   : 8 ;  /* padding */
    uint32_t   vlanId14                 : 12;  /* offset=7, [11:0] */  /* default=12'b0 */
    uint32_t   vlanId15                 : 12;  /* offset=7, [23:12] */  /* default=12'b0 */
    uint32_t   __pad7                   : 8 ;  /* padding */
} VlanIdCamCtl_t;

extern VlanIdCamCtl_t VlanIdCamCtl;

/* =========================================================
 * Register initialisation
 * ========================================================= */

void reg_init(void);

#endif /* _REG_DRV_TINYREG_H_ */
