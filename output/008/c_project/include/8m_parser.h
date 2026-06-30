#ifndef _8M_PARSER_H_
#define _8M_PARSER_H_

/* Auto-generated from DSL project */
/* Original: parser.h */

#include <stdint.h>

/*
** 8m DSL — parser() 接口声明
** 符合 8m_AST_Compiler_Design.md §2.3 规范
**
** [输出映射] → 8m_parser.h  (+ include guard _8M_PARSER_H_)
**               + extern prMacDa, prMacSa, prVlanId, ... (规则4)
** [自动include] ← main.c (调用parser), switchX.c (引用prXxx)
*/

void parser(uint8_t *PacketByte);



/* Cross-file extern declarations (auto-generated) */
extern uint32_t prIpSa;
extern uint32_t prVlanId;
extern uint32_t prIsLoopDetection;
extern uint32_t prExistVlan;
extern uint32_t prIpDa;
extern uint32_t giTpid;
extern uint32_t prMacDa;
extern uint32_t prLoopTtl;


#endif /* _8M_PARSER_H_ */