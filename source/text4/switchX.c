/*
** Switch packet from ingress port to egress port queue
** Input: ParserResult
**
** [输出映射] → 8m_switchX.c
**   #include "8m_switchX.h"      (规则1: 同名头文件)
**   #include "8m_types.h"        (规则2: 引用 ParserResult 字段)
**   #include "8m_globals.h"      (规则3: 引用 piSrcPort, piPktLength)
**   #include "8m_parser.h"       (规则4: 引用 prMacDa, prVlanId 等 extern)
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
	// 1.5 ACL filtering (before L2 lookup)
	giAclIdx[4:0] = 0;
	for( i = 0; i < 32; i++ ) {
		DsAcl = DsAcl Table[ i ];
		if( DsAcl.action == 1'b0 && DsAcl.etherType[15:0] == giTpid ) {
			piDiscard = 1;
		}
	}

	// 1.6 STP port state check
	if( DsPort.stpState[2:0] == 3'b001 ) {
		piDiscard = 1;
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
		if( (DsMacKey.{ fid[11:0], macAddr[47:0] } == { giFid, prMacDa }) && DsMacValid.valid[i] ) {
			DsMacFwd =  DsMac Table[ (giHashIdx<<2)+i ];
			piBrgHit = 1;
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
			if( DsStormCtrl.usePkt ) {
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
		if( (DsMacKey.{ fid{i}, macAddr{i} } == { giFid, prMacSa }) && DsMacValid.valid[i] ) {
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
				giLruFlag = DsMacAging.aging{i};
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
			// [text4新增] 端口安全: maxMacNum限制
			if( DsPort.maxMacNum[7:0] > 0 && L2LearnCtl.sysLearnNum >= DsPort.maxMacNum[7:0] ) {
				// do nothing, MAC learning disabled by port security
			} else {
				update DsMacKey using newDsMacKeyEntry at { giLrnHash }.{ giLrnSubIdx };
				update DsMac using newDsMacEntry at { giLrnHash, giLrnSubIdx };
				DsMacAging[ giLrnHash ].aging{ giLrnSubIdx } = 0;
				DsMacValid[ giLrnHash ].valid[ giLrnSubIdx ]  = 1;
				if( giLrnNew ) {
					L2LearnCtl.sysLearnNum++;
				}
			}
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
					piPrior = piVlanPrior >= piDscpPrior ? piVlanPrior : piDscpPrior;
				}
			} else if( giDscpPriorAssign ){
				piPrior = piDscpPrior;
				if( PriorAssignCtl.dscpWeight == PriorAssignCtl.portWeight ) {
					piPrior = piDscpPrior >= piPortPrior ? piDscpPrior : piPortPrior;
				} else if ( PriorAssignCtl.dscpWeight == PriorAssignCtl.vlanWeight ) {
					piPrior = piDscpPrior >= piVlanPrior ? piDscpPrior : piVlanPrior ;
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
			giQid[5:0] 	= {i, piPrior};	
		
		// 7.2 enqueue
			Enqueue PacketByte with updated header waiting for outgoing;
		}
	}
}
