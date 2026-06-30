#ifndef _REG_DRV_TINYREG2_H_
#define _REG_DRV_TINYREG2_H_

#include <stdint.h>

/* =========================================================
 * Address Macros
 * ========================================================= */

#define DS1QPRIORMAP_ADDR_BASE              0x0000
#define DS1QPRIORMAP_DEPTH                  8
#define DSDSCPPRIORMAP_ADDR_BASE            0x1000
#define DSDSCPPRIORMAP_DEPTH                64


/* =========================================================
 * Ds1qPriorMap  (8 entries × 1 word)
 * ========================================================= */
typedef struct {
    uint8_t    prior                    : 2 ;  /* offset=0, [1:0] */
    uint8_t    __pad0                   : 6 ;  /* padding */
} Ds1qPriorMap_entry_t;

Ds1qPriorMap_entry_t Ds1qPriorMap_mem[8];

/* =========================================================
 * DsDscpPriorMap  (64 entries × 1 word)
 * ========================================================= */
typedef struct {
    uint8_t    prior                    : 2 ;  /* offset=0, [1:0] */
    uint8_t    __pad0                   : 6 ;  /* padding */
} DsDscpPriorMap_entry_t;

DsDscpPriorMap_entry_t DsDscpPriorMap_mem[64];

/* =========================================================
 * Register initialisation
 * ========================================================= */

void reg_init(void);

#endif /* _REG_DRV_TINYREG2_H_ */
