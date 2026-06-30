#ifndef _8M_TYPES_H_
#define _8M_TYPES_H_

/* Auto-generated from DSL project */
/* Original: types.h */

#include <stdint.h>

/*
** 8m DSL — 共享结构体类型定义
** 符合 8m_AST_Compiler_Design.md §2.3 规范
**
** [输出映射] → 8m_types.h  (+ include guard _8M_TYPES_H_)
** [自动include] ← parser.c, switchX.c, main.c
*/

struct ParserResult{
	uint64_t macDa;
	uint64_t macSa;
	uint8_t  vlanPrior;
	uint16_t vlanId;
	uint8_t  vlanTagged;
	uint8_t   isLoopDetection;
	uint8_t  loopTtl;
	uint8_t   isArp;
	uint8_t   isIpv4;
	uint8_t   isIpv6;
	uint8_t  ipDscp;
	uint8_t   isUnknownPkt;
}


/* @externs */

#endif /* _8M_TYPES_H_ */