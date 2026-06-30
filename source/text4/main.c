/*
** Log
** 2018-08-21: change port number from 10 to 8
**
** 全局声明见:  globals.h / types.h
** 接口声明见:  parser.h / switchX.h / egress.h
**
** [输出映射] → 8m_main.c
**   #include "8m_globals.h"      (规则3: 引用 PacketByte[], piSrcPort 等)
**   #include "8m_types.h"        (规则2: process 间接触及 ParserResult)
**   #include "8m_parser.h"       (规则4: 调用 parser(), 使用 prXxx)
**   #include "8m_switchX.h"      (规则4: 调用 switchX(), 使用 piXxx)
**   #include "8m_egress.h"       (规则4: 调用 egress())
**   #include <stdint.h>
**   #include <string.h>
*/
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
				DsMacAging.aging{ giAgingIdx[1:0] }++;
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
