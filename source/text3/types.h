/*
** 8m DSL — 共享结构体类型定义
** 符合 8m_AST_Compiler_Design.md §2.3 规范
**
** [输出映射] → 8m_types.h  (+ include guard _8M_TYPES_H_)
** [自动include] ← parser.c, switchX.c, main.c
*/

struct ParserResult{
	uint48 macDa;
	uint48 macSa;
	uint3  vlanPrior;
	uint12 vlanId;
	uint2  vlanTagged;
	bool   isLoopDetection;
	uint4  loopTtl;
	bool   isArp;
	bool   isIpv4;
	bool   isIpv6;
	uint8  ipDscp;
	bool   isUnknownPkt;
}
