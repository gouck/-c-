#ifndef _REG_DRV_COMMON_H_
#define _REG_DRV_COMMON_H_

#include <stdint.h>

/* =========================================================
 * BITFIELD helper macros
 * ========================================================= */

#define BITFIELD_GET(val, hi, lo) \
    (((val) >> (lo)) & ((1ULL << ((hi) - (lo) + 1)) - 1))

#define BITFIELD_SET(val, hi, lo, field_val) \
    ((val) = ((val) & ~(((1ULL << ((hi) - (lo) + 1)) - 1) << (lo))) | \
     (((uint64_t)(field_val) & ((1ULL << ((hi) - (lo) + 1)) - 1)) << (lo)))


#endif /* _REG_DRV_COMMON_H_ */
