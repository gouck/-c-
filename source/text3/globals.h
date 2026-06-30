/*
** 8m DSL — 全局变量声明
** 符合 8m_AST_Compiler_Design.md §2.3 规范
**
** [输出映射] → 8m_globals.h  (+ include guard _8M_GLOBALS_H_)
** [自动include] ← main.c, parser.c(prMacDa引用PacketByte)
*/

uint8  PacketByte[];
uint8  piSrcPort[2:0] = channelId[2:0];
uint16 piPktLength[11:0] = packetLength[11:0];
