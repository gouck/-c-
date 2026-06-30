#ifndef _8M_GLOBALS_H_
#define _8M_GLOBALS_H_

/* Auto-generated from DSL project */
/* Original: globals.h */

#include <stdint.h>

/*
** 8m DSL — 全局变量声明
** 符合 8m_AST_Compiler_Design.md §2.3 规范
**
** [输出映射] → 8m_globals.h  (+ include guard _8M_GLOBALS_H_)
** [自动include] ← main.c, parser.c(prMacDa引用PacketByte)
*/

extern uint8_t  PacketByte[];
extern uint8_t  piSrcPort;
extern uint16_t piPktLength;


/* @externs */

#endif /* _8M_GLOBALS_H_ */