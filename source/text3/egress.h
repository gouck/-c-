/*
** 8m DSL — egress() 接口声明
** 符合 8m_AST_Compiler_Design.md §2.3 规范
**
** [输出映射] → 8m_egress.h  (+ include guard _8M_EGRESS_H_)
** [自动include] ← main.c (调用egress)
*/

void egress();
