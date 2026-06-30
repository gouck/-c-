/*
** 8m DSL — parser() 接口声明
** 符合 8m_AST_Compiler_Design.md §2.3 规范
**
** [输出映射] → 8m_parser.h  (+ include guard _8M_PARSER_H_)
**               + extern prMacDa, prMacSa, prVlanId, ... (规则4)
** [自动include] ← main.c (调用parser), switchX.c (引用prXxx)
*/

void parser( PacketByte );
