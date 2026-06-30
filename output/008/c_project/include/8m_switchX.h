#ifndef _8M_SWITCHX_H_
#define _8M_SWITCHX_H_

/* Auto-generated from DSL project */
/* Original: switchX.h */

#include <stdint.h>

/*
** 8m DSL — switchX() 接口声明
** 符合 8m_AST_Compiler_Design.md §2.3 规范
**
** [输出映射] → 8m_switchX.h  (+ include guard _8M_SWITCHX_H_)
**               + extern piXxx 变量 (规则4)
** [自动include] ← main.c (调用switchX), egress.c (引用piXxx)
*/

void switchX();



/* Cross-file extern declarations (auto-generated) */
extern uint32_t DsPort;
extern uint32_t DsStormCtrl;
extern uint32_t DsMacValid;
extern uint32_t DsMacAging;


#endif /* _8M_SWITCHX_H_ */