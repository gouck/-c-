/*
** Parse input packet from source channel to corresponding fields
** Input: 	PacketHeader is the first 64B of packet
** Output: 	ParserResult
**
** [输出映射] → 8m_parser.c
**   #include "8m_parser.h"       (规则1: 同名头文件)
**   #include "8m_types.h"        (规则2: 引用 ParserResult 类型)
**   #include "8m_globals.h"      (规则3: 引用 PacketByte[])
*/
void parser( PacketByte )
{
	prMacDa[47:0] = {PacketByte0, ..., PacketByte5};
	prMacSa[47:0] = {PacketByte6, ..., PacketByte11};

	giTpid[15:0] = {PacketByte12, PacketByte13};
	giPldOffset[7:0] = 14;
	
	// check the first vlan
	if( giTpid == 0x8100 || giTpid == 0x9100 || giTpid == 0x88a8 ) {
		prVlanPrior[2:0] = PacketByte[ giPldOffset ][7:5];
	prVlanId[11:0]	= { PacketByte[ giPldOffset ][3:0], PacketByte[ giPldOffset+1 ][7:0] };
		prExistVlan[1:0] = 2'b01;
		giTpid = { PacketByte[ giPldOffset+2 ], PacketByte[ giPldOffset+3 ] };
		giPldOffset += 4;
	}
/*
	// check the second vlan	
	if( giTpid == 0x8100 || giTpid == 0x9100 || giTpid == 0x88a8 ) {
		prExistVlan[1:0] |= 2'b10;
		giPldOffset += 4;
		giTpid = { PacketByte[ giPldOffset ], PacketByte[ giPldOffset+1 ] };
	} 
*/
	// check payload
	if( giTpid == 0x8899 ) {	// check the packet for loop detection
		prLoopTtl[3:0] = PacketByte[ giPldOffset+3 ][3:0];
		prIsLoopDetection = 1'b1;
	} else if( giTpid == 0x0806 || giTpid == 0x8035 ) {		// ARP, RARP
		prIsArp = 1'b1;
	} else if( giTpid == 0x0800 ) {
		prIsIpv4 = 1'b1;
		prIpDscp[5:0] = PacketByte[ giPldOffset+1 ][7:2];
		prIpSa[31:0] = { PacketByte[ giPldOffset+12 ], ..., PacketByte[ giPldOffset+15 ] }; 
		prIpDa[31:0] = { PacketByte[ giPldOffset+16 ], ..., PacketByte[ giPldOffset+19 ] }; 
	} else if( giTpid == 0x86dd ) {
		prIsIpv6 = 1'b1;
		prIpDscp[5:0] = { PacketByte[ giPldOffset ][3:0], PacketByte[ giPldOffset+1 ][7:6] };
		prIpSa[127:0] = { PacketByte[ giPldOffset+8 ], ..., PacketByte[ giPldOffset+23 ] }; 
		prIpDa[127:0] = { PacketByte[ giPldOffset+24 ], ..., PacketByte[ giPldOffset+39 ] }; 
	} else {
		prIsUnknownPkt = 1'b1;
	}
}