/*
** Log
** 2018-08-21: change port number from 10 to 8
*/
uint8 PacketByte[];
uint8 piSrcPort[2:0] = channelId[2:0];
uint16 piPktLength[11:0] = packetLength[11:0];

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
/*
** Layer 2 switch 
** Input:  Packet 
** 
*/
process forward() {
	while(1) {		// packet drived
		parser( );
		switchX( );
		// Traffic Manager
		egress();
	}
	// Enqueue waiting for being scheduled.
}

/*
** storm control update
*/
process updateStormCtrl() {
	giStormIdx[4:0] = 0;
	while(1) {
		if( StormCfgCtl.enable ) {
			DsStormCtrl = DsStormCtrl Table[ giStormIdx ];
			if( DsStormCtrl.enable ) {
				DsStormCtrl.counter += DsStormCtrl.step[31:0];
				if( DsStormCtrl.counter[31:0] > DsStormCtrl.cntThrd[31:0] ) {
					DsStormCtrl.counter = DsStormCtrl.cntThrd;
				}	
			}
		}
		giStormIdx++;
		Delay( StormCfgCtl.delayInterval[31:0] );
	}
}

/*
** Normal aging
*/
process normalAging() {
	giAgingIdx[10:0] = 0;
	while(1) {
		if( L2AgingCtl.agingEn && !L2AgingCtl.fastAgingEn ) {
			giCycleCnt[31:0]++;
			if( giCycleCnt >= L2AgingCtl.cycleThrd[31:0] ) {
				giCycleCnt = 0;
				DsMacAging = DsMacAging Table[ giAgingIdx[10:2] ];
				DsMacValid = DsMacValid Table[ giAgingIdx[10:2] ];
				DsMacStatic = DsMacStatic Table[ giAgingIdx[10:2] ];
				if( DsMacStatic.static[ giAgingIdx[1:0] ] ) {
					// none
				} else if( DsMacAging.aging{ giAgingIdx[1:0] } < 3 ) {
					DsMacAing.aging{ giAgingIdx[1:0] }++;
				} else if( DsMacValid.valid[ giAgingIdx[1:0] ] ) {
					DsMacValid.valid[ giAgingIdx[1:0] ] = 0;
					L2LearnCtl.sysLearnNum--;
				} else {
					// none
				}
				giAgingIdx++;
			}
		}
	}
}

/*
** fast aging
*/
process fastAging() {	
	giAgingPtr[10:0] = 0;
	while(1) {
		if( L2AgingCtl.agingEn && L2AgingCtl.fastAgingEn ) {
			while( giAgingPtr <= 0x7FF ) {
				DsMacValid = DsMacValid Table[ giAgingPtr[10:2] ];
				DsMacStatic = DsMacStatic Table[ giAgingPtr[10:2] ];
				if( DsMacValid.valid[ giAgingPtr[1:0] ] && !DsMacStatic.static[ giAgingPtr[1:0] ] ) {
					if( L2AgingCtl.fastAgingAll ) {
						DsMacValid.valid[ giAgingPtr[1:0] ] = 1'b0;
						L2LearnCtl.sysLearnNum--;
					} else if( L2AgingCtl.fastAgingByPort ) {
						DsMac = DsMac Table[ giAgingPtr[10:0] ];
//						if( DsMac.port == L2AgingCtl.portId[2:0] )	{
						if( DsMac.destMap[ L2AgingCtl.portId[3:0] ] )	{
							DsMacValid.valid[ giAgingPtr[1:0] ] = 1'b0;
							L2LearnCtl.sysLearnNum--;
						}
					}
				}
				giAgingPtr++;
			}
			L2AgingCtl.fastAgingEn = 0;
		}
	}
	
}

/*
** Send loop detection packet periodically
*/
process sendLoopDetect() {
	while(1) {
		if( LoopDetectCtl.en ) {
			Delay( LoopDetectCtl.detectInterval[31:0] );
			send Loop Detect packet { 0xFFFF_FFFF_FFFF, LoopDetectCtl.loopMac[47:0], 0x8899, 0x2300, 0x000, LoopDetectCtl.ttl[3:0], 352'b0};	// update CRC at MAC 
		}
	}
}

/*
** Parse input packet from source channel to corresponding fields
** Input: 	PacketHeader is the first 64B of packet
** Output: 	ParserResult
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
		prVlanId[11:0]	= { PacketByte[ giPldOffset ][3:0], PacketByte[ giPldOffset+1 ][7:0] }
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

/*
** Switch packet from ingress port to egress port queue
** Input: ParserResult
*/
void switchX() {
	// 1 vlan assign
	DsPort = DsPort Table[ piSrcPort ];
	piPortVid[11:0] = DsPort.portVid;
	pi1qBasedVlan = DsPort.dot1qBasedVlan;
	piAft[1:0]	= DsPort.aft;
	piLrnDisable = DsPort.lrnDisable;
	piAllowBrg2Src = DsPort.allowBrg2Src;
	piPortPrior[1:0] = DsPort.prior[1:0];
	piRmaMode = DsPort.rmaMode;
	piPortMirror = DsPort.mirrorEn;
	
	giVid[11:0] = piPortVid;	// Used as default vlan id
	if( pi1qBasedVlan && prExistVlan != 0 && prVlanId != 0 ) {
		giVid = prVlanId;
	 	if( DsPort.strictPvid && (prVlanId != piPortVid) ) {
			piDiscard = 1;
		}
	}

	giVlanIdx[3:0] = 0;
	giVlanHit = 0;
	for( i = 0; i < 16; i++ ) {
		if( giVid == VlanIdCamCtl.vlanId{i} ) { 
			giVlanIdx = i; 
			giVlanHit = 1; 
			break; 
		}
	}
	if( giVlanHit ) {
		DsVlan = DsVlan Table[ giVlanIdx ];
		piFwdBmp[15:0] = {6'b0, DsVlan.vlanBmp[9:0] };
		piVlanMember[9:0] = DsVlan.vlanBmp;
		piFid[11:0] = DsVlan.fid[11:0];
		pi1qPriorEn = DsVlan.dot1qPriorEn;
		Ds1qPriorMap = Ds1qPriorMap Table{ prVlanPrior };
		piVlanPrior[1:0] = Ds1qPriorMap.prior[1:0];
		piUntagFlag[15:0] = { 6'b111111, DsVlan.untagFlag[9:0]};
		piVlanMirror = DsVlan.mirrorEn;
		piEgressFilter = DsVlan.egressFilter;
		piLeakyUcast = DsVlan.leakyUcast;
		piLeakyMcast = DsVlan.leakyMcast;
		piLeakyBcast = DsVlan.leakyBcast;
		piLeakyArp = DsVlan.leakyArp;
		piLeakyMirror = DsVlan.leakyMirror;
	} else {
		piDiscard = 1;
	}
	// aft
	giVlanTagged = prExistVlan != 0 && prVlanId != 0;
	switch( piAft ) {
		case 2'b01: { 
			piDiscard = !giVlanTagged; 
			break;
		}
		case 2'b10: {
			piDiscard = giVlanTagged;
			break;
		}
		case 2'b11: { 
			piDiscard = 1;
			break;
		}
		default: ;
	}
	// 2 L2 filtering and forwarding
	piBcast = prMacDa == 0xFFFF_FFFF_FFFF;
	piMcast = !piBcast && prMacDa[40];
	// 2.1 Look up table
	if( !piDiscard ) {
		if( piMcast ) {
			giFid[11:0] = giVid;
		} else {
			giFid = piFid;
		}

		giHashIdx[8:0] = hash1( { giFid, prMacDa } );
		DsMacKey = DsMacKey Table[ giHashIdx ];
		DsMacValid = DsMacValid Table[ giHashIdx ];
		piBrgHit = 0;
		for( i = 0; i < 4; i++ ) {
			if( DsMacKey.{ fid[11:0], macAddr[47:0] } == { giFid, prMacDa } 
			&& DsMacValid.valid[i] ) {
				DsMacFwd =  DsMac Table[ (giHashIdx<<2)+i ];
				piBrgHit = 1
				break;
			} 
		}
	// 2.2 forwarding
		if( piBrgHit ) {
			piMacDaPrior[1:0] = DsMacFwd.prior[1:0];
			if( DsMacFwd.destDiscard ) {
				piDiscard =  1;
			} else {
				piFwdBmp = {6'b0, DsMacFwd.destMap[9:0]};
			}
		} else {
			piFlooding = 1;
		}
		// storm control
		if( piBcast ) {					// broadcast
			giStormSubIdx[1:0] = 3;
		} else if( piMcast && !piBrgHit ) {	// Unknown multicast
			giStormSubIdx = 2;
		} else if( piMcast && piBrgHit ) {	// Known multicast
			giStormSubIdx = 1;				
		} else if( !piMcast && !piBrgHit ) {	// Unknown unicast
			giStormSubIdx = 0;				
		}
		giStormCtlIdx = (piSrcPort<<2) + giStormSubIdx[1:0];
		DsStormCtrl = DsStormCtrl Table[ giStormCtlIdx ];
		
		if( DsStormCtrl.enable ) {
			is( DsStormCtrl.usePkt ) {
				if( DsStormCtrl.counter[31:0] == 0 ) {
					piDiscard = 1;
				} else {
					DsStormCtrl.counter--;
				}
			} else {
				if( DsStormCtrl.counter < piPktLength ) {
					piDiscard = 1;
				} else {
					DsStormCtrl.counter -= piPktLength;
				}
			}
		}
	}

	// 3 L2 learning
	if( !piLrnDisable  && !piDiscard ) {
		giLrnHash[8:0] = hash1( {giFid, prMacSa} );
		DsMacKey = DsMacKey Table[ giLrnHash ];
		DsMacValid = DsMacValid Table[ giLrnHash ];
		for( i = 0; i < 4; i++ ) {
			if( DsMacKey.{ fid{i}, macAddr{i} } == { giFid, prMacSa } 
			&& DsMacValid.valid[i] ) {
				DsMacLrn = DsMac Table[ (giLrnHash<<2)+i ];
				giLrnHit = 1;
				giLrnSubIdx = i;
				break;
			} else {
				giLrnHit = 0;
			}
		}
		if( !giLrnHit ) {
			giLrnNew = 0;
			for( i = 0; i < 4; i++ ) {		// find one empty
				if( !DsMacValid[ giLrnHash ].valid[i] ) {
					giLrnNew = 1;
					giLrnSubIdx = i;
					break;
				}
			}
		}
		if( !giLrnHit && L2LearnCtl.lruEn ) {
			DsMacAging = DsMacAging Table[ giLrnHash ];
			giLruFlag[1:0] = 0;
			for( i = 0; i < 4; i++ ) {		// find the oldest one
				if( giLruFlag <= DsMacAging.aging{i} ) {
					giLruFlag = DsMacAging.aging{i}
					giLruLrn = 1;
					giLrnSubIdx = i;
				}
			}
		}
		
		// update tables
		newDsMacKeyEntry = { prMacSa, giFid };
		newDsMacEntry = { 1<<piSrcPort, 1'b0, 1'b0, 2'b00 };
		if( giLrnHit ) {
			update DsMacLrn using newDsMacEntry at {giHashIdx, giLrnSubIdx};
			DsMacAging[ giLrnHash ].aging{ giLrnSubIdx } = 0;
		} else if( giLrnNew || giLruLrn ) {
			update DsMacKey using newDsMacKeyEntry at { giLrnHash }.{ giLrnSubIdx };
			update DsMac using newDsMacEntry at { giLrnHash, giLrnSubIdx };
			DsMacAging[ giLrnHash ].aging{ giLrnSubIdx } = 0;
			DsMacValid[ giLrnHash ].valid[ giLrnSubIdx ]  = 1	
		}
		if( giLrnNew ) {
			L2LearnCtl.sysLearnNum++;
		}
	}

	// 5 Priority assign
	if( ( prIsIpv4 || prIsIpv6 ) && ( PriorAssignCtl.ipDscpEn ) ) {
		DsDscpPriorMap = DsDscpPriorMap Table{ prIpDscp[5:0] };
		piDscpPrior[1:0] = DsDscpPriorMap.prior[1:0];
	}
	if( PriorAssignCtl.ipAddrEn && ( prIsIpv4 || prIsIpv6 ) ) {
		giIpAddr0Seg[127:0] = PriorAssignCtl.ip0Addr[127:0] & PriorAssignCtl.ip0Mask[127:0];
		giIpAddr1Seg[127:0] = PriorAssignCtl.ip1Addr[127:0] & PriorAssignCtl.ip1Mask[127:0];
		if( ( giIpAddr0Seg == prIpSa & PriorAssignCtl.ip0Mask )
		|| ( giIpAddr0Seg == prIpDa & PriorAssignCtl.ip0Mask ) ) {
			piIpAddrPrior[1:0] = PriorAssignCtl.ip0AddrPrior[1:0];
		} else if( ( giIpAddr1Seg == prIpSa & PriorAssignCtl.ip1Mask )
		|| ( giIpAddr1Seg == prIpDa & PriorAssignCtl.ip1Mask ) ) {
			piIpAddrPrior[1:0] = PriorAssignCtl.ip1AddrPrior[1:0];
		}
	}
	if( PriorAssignCtl.rldpEn && prIsLoopDetection ) {
		piPrior[1:0] = PriorAssignCtl.rldpPrior[1:0];
	} else if( PriorAssignCtl.macDaEn ) {
		piPrior = piMacDaPrior;
	} else if( PriorAssignCtl.ipAddrEn ) {
		piPrior = piIpAddrPrior;
	} else {
		if( ( PriorAssignCtl.portWeight[1:0] == PriorAssignCtl.vlanWeight[1:0] )
		&& ( PriorAssignCtl.portWeight == PriorAssignCtl.dscpWeight[1:0] ) ) {
			piPrior = Max( piPortPrior,  piVlanPrior, piDscpPrior );
		} else {
			// find the weightest priority
			giVlanPriorAssigne = 0; giDscpPriorAssign = 0;
			if( PriorAssignCtl.vlanWeight[1:0] >= PriorAssignCtl.portWeight[1:0] && PriorAssignCtl.vlanWeight[1:0] >= PriorAssignCtl.dscpWeight[1:0] ) {
				giVlanPriorAssigne = 1;
				giPriorWeight = PriorAssignCtl.vlanWeight;
			} else if( PriorAssignCtl.dscpWeight[1:0] >= PriorAssignCtl.portWeight[1:0] && PriorAssignCtl.dscpWeight[1:0] >= PriorAssignCtl.vlanWeight[1:0] ) {
				giPriorWeight = PriorAssignCtl.dscpWeight;
				giDscpPriorAssign = 1;
			}
			// Does it exist equalization weight
			if( giVlanPriorAssigne ) {
				piPrior = piVlanPrior;
				if( PriorAssignCtl.vlanWeight == PriorAssignCtl.portWeight ) {
					piPrior = piVlanPrior >= piPortPrior ? piVlanPrior : piPortPrior;
				} else if ( PriorAssignCtl.vlanWeight == PriorAssignCtl.dscpWeight ) {
					piPrior = piVlanPrio >= piDscpPrior ? piVlanPrior : piDscpPrior;
				}
			} else if( giDscpPriorAssign ){
				piPrior = piDscpPrior;
				if( PriorAssignCtl.dscpWeight == PriorAssignCtl.portWeight ) {
					piPrior = piDscpPrior >= piPortPrior ? piDscpPrior : piPortPrior;
				} else if ( PriorAssignCtl.dscpWeight == PriorAssignCtl.vlanWeight ) {
					piPrior = piDscpPrio >= piVlanPrior ? piDscpPrior : piVlanPrior ;
				}
			} else {
				piPrior = piPortPrior;
				if( PriorAssignCtl.portWeight == PriorAssignCtl.vlanWeight ) {
					piPrior = piPortPrior >= piVlanPrior ? piPortPrior : piVlanPrior;
				} else if( PriorAssignCtl.portWeight == PriorAssignCtl.dscpWeight ) {
					piPrior = piPortPrior >= piDscpPrior ? piPortPrior: piDscpPrior;
				}
			}
		}
	}

	// 6 forwarding bitmap determination
	// Reserved Multicast Address mode
	if( piMcast && ( prMacDa[47:8] == 0x0180c20000 ) ) {
		switch( prMacDa[7:0] ) {
			0x00: if( piRmaMode ) { piDiscard = 1; }
			0x03: if( piRmaMode ) { piDiscard = 1; } 
			0x0e: if( piRmaMode ) { piDiscard = 1; } 
			0x11~1f: if( piRmaMode ) { piDiscard = 1; }
			0x21: if( piRmaMode ) { piDiscard = 1; }
			0x31~3f: if( piRmaMode ) { piDiscard = 1; }
		}
	}
	if( piFlooding ) {
		piFwdBmp = { 6'b0, piVlanMember };
	}
	if( piPortMirror ) {
		piFwdBmp |= 1<<MirrorCtl.srcMirrorPort[3:0];
	} 
	if( piVlanMirror ) {
		piFwdBmp |= 1<<MirrorCtl.vlanMirrorPort[3:0];
	}
	// 6.0 loop detection packet
	if( prIsLoopDetection && ( (prLoopTtl <= 1 ) || (prMacSa == LoopDetectCtl.loopMac) ) ) {
		piDiscard = 1;
	}
	// 6.1 source port excluding
	if( !piAllowBrg2Src ) {
		piFwdBmp &= ~(1<<piSrcPort);
	}
	// 6.2 egress filter
	for( i = 0; i < 8; i++ ) {	
		if( piEgressFilter && piFwdBmp[i] && !piVlanMember[i] ) {
			piFwdBmp[i] = 1'b0;
			if( ( piBrgHit && piLeakyUcast ) || ( piMcast && piLeakyMcast )
			|| ( piBcast && piLeakyBcast ) || ( prIsArp && piLeakyArp )
			|| ( ( piPortMirror || piVlanMirror ) && piLeakyMirror ) ) {
				piFwdBmp[i] = 1'b1;
			}
		}
	}
	if( piDiscard ) { piFwdBmp = 16'b0; }

	// 7 packet replication
	//  traverse fwdBmp
	for( i = 0; i < 16; i++ ) {
		if( piFwdBmp[i] ) {
		// 7.0 generate information for egress
			piDestPort[2:0] = i & 0x7;
			piVlanId[11:0]	= giVid;
			piPrior[1:0] 	= piPrior;
			piOutNoVlan	= piUntagFlag[i];
			piPktTagged	= prExistVlan;
			piIsLoopDetect	= prIsLoopDetection;
			piLoopTtl	= prLoopTtl - 1;
			piPktLength	= piPktLength;
		// 7.1 generate queue id
			qid[5:0] 	= {i, piPrior};	
		
		// 7.2 enqueue
			Enqueue PacketByte with updated header waiting for outgoing;
		}
	}
}

/*
** Egress process 
** Input: Packet from packet memory
**		  Packet infor passed from ingress
** Output: Edited packet waiting for outgoing
*/
void egress() {
	if( piIsLoopDetect ) {
		Replace PacketByte[6] to PacketByte[11] using LoopDetectCtl.loopMac[47:0];
		Replace PacketByte[17] using { 4'h0, piLoopTtl };
	} else {
		DsDestPort = DsPort[ piDestPort ];
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
