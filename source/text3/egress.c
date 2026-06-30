/*
** Egress process 
** Input: Packet from packet memory
**		  Packet infor passed from ingress
** Output: Edited packet waiting for outgoing
**
** [输出映射] → 8m_egress.c
**   #include "8m_egress.h"       (规则1: 同名头文件)
**   #include "8m_globals.h"      (规则3: 引用 PacketByte[])
**   #include "8m_switchX.h"      (规则4: 引用 piXxx extern 变量)
*/
void egress() {
	if( piIsLoopDetect ) {
		Replace PacketByte[6] to PacketByte[11] using LoopDetectCtl.loopMac[47:0];
		Replace PacketByte[17] using { 4'h0, piLoopTtl };
	} else {
		DsDestPort = DsPort Table[ piDestPort ];
		newVlanTag[31:0] = { 0x8100, 1'b0, piPrior, 1'b0, piVlanId };
		if( DsDestPort.updateMacSa ) {
			Replace PacketByte[6] to PacketByte[11] using { DsDestPort.portMacHi[47:32], DsDestPort.portMacLo[31:0] };
		}
		if( piOutNoVlan ) {
			if( piPktTagged ) {
				remove PacketByte[12] ... PacketByte[15];
			} 
		} else {
			if( piPktTagged ) {
				Replace PacketByte[12] to PacketByte[15] using newVlanTag;
			} else {
				Insert newVlanTag after PacketByte[11];
			}
		}
	}
}
