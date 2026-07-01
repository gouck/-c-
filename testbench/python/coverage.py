
"""
coverage.py --- Full register coverage for 8m switch
Bin format: StructName_mem.FieldName=Value
"""
from typing import Dict

def _b1(n): return {f"{n}=0":0, f"{n}=1":0}
def _b2(n): return {f"{n}={v}":0 for v in range(4)}
def _b3(n): return {f"{n}={v}":0 for v in range(8)}
def _b4(n): return {f"{n}={v}":0 for v in range(16)}
def _bw(n): return {f"{n}=0":0, f"{n}=nonzero":0, f"{n}=max":0}
def _bm(n,w): return {f"{n}=0":0, f"{n}=mid":0, f"{n}={2**w-1}":0}

class FunctionalCoverage:
    def __init__(self):
        self.points = {}
        A = self._add
        A("DsMac_mem",{**_bw("DsMac_mem.destMap"),**_b1("DsMac_mem.destDiscard"),**_b1("DsMac_mem.isMcast"),**_b2("DsMac_mem.prior")})
        A("DsMacAging_mem",{**_b2("DsMacAging_mem.aging0"),**_b2("DsMacAging_mem.aging1"),**_b2("DsMacAging_mem.aging2"),**_b2("DsMacAging_mem.aging3")})
        A("DsMacKey_mem",{**_bw("DsMacKey_mem.fid"),**_bw("DsMacKey_mem.macAddr")})
        A("DsMacStatic_mem",{**_b4("DsMacStatic_mem.static")})
        A("DsMacValid_mem",{**_b4("DsMacValid_mem.valid")})
        A("DsPort_mem",{**_bw("DsPort_mem.portVid"),**_b1("DsPort_mem.dot1qBasedVlan"),**_b2("DsPort_mem.aft"),**_b1("DsPort_mem.keepVlanTag"),**_bw("DsPort_mem.portMacHi"),**_bw("DsPort_mem.portMacLo"),**_b3("DsPort_mem.stpState"),**_bm("DsPort_mem.maxMacNum",8),**_b1("DsPort_mem.allowBrg2Src"),**_b1("DsPort_mem.lrnDisable"),**_b2("DsPort_mem.prior"),**_b1("DsPort_mem.rmaMode"),**_b1("DsPort_mem.mirrorEn"),**_b1("DsPort_mem.updateMacSa"),**_b1("DsPort_mem.strictPvid")})
        A("DsStormCtrl_mem",{**_b1("DsStormCtrl_mem.enable"),**_b1("DsStormCtrl_mem.usePkt"),**_bw("DsStormCtrl_mem.cntThrd"),**_bw("DsStormCtrl_mem.counter"),**_bw("DsStormCtrl_mem.step")})
        A("DsVlan_mem",{**_bw("DsVlan_mem.fid"),**_bw("DsVlan_mem.vlanBmp"),**_bw("DsVlan_mem.untagFlag"),**_b1("DsVlan_mem.leakyUcast"),**_b1("DsVlan_mem.leakyMcast"),**_b1("DsVlan_mem.leakyBcast"),**_b1("DsVlan_mem.leakyArp"),**_b1("DsVlan_mem.leakyMirror"),**_b1("DsVlan_mem.egressFilter"),**_b1("DsVlan_mem.dot1qPriorEn"),**_b1("DsVlan_mem.mirrorEn"),**_b2("DsVlan_mem.prior")})
        A("DsAcl_mem",{**_b1("DsAcl_mem.action"),**_bw("DsAcl_mem.etherType"),**_bw("DsAcl_mem.vlanId"),**_bw("DsAcl_mem.srcMacHi"),**_bw("DsAcl_mem.srcMacLo")})
        A("L2AgingCtl",{**_b1("L2AgingCtl.fastAgingEn"),**_b1("L2AgingCtl.agingEn"),**_b1("L2AgingCtl.fastAgingAll"),**_b1("L2AgingCtl.fastAgingByPort"),**_b4("L2AgingCtl.portId"),**_bw("L2AgingCtl.cycleThrd")})
        A("L2LearnCtl",{**_bw("L2LearnCtl.sysLearnNum"),**_b1("L2LearnCtl.lruEn")})
        A("LoopDetectCtl",{**_b1("LoopDetectCtl.en"),**_b4("LoopDetectCtl.ttl"),**_bw("LoopDetectCtl.loopMacHi"),**_bw("LoopDetectCtl.loopMacLo"),**_bw("LoopDetectCtl.detectInterval")})
        A("MirrorCtl",{**_b4("MirrorCtl.srcMirrorPort"),**_b4("MirrorCtl.vlanMirrorPort")})
        A("PriorAssignCtl",{**_b1("PriorAssignCtl.ipDscpEn"),**_b1("PriorAssignCtl.ipAddrEn"),**_b1("PriorAssignCtl.macDaEn"),**_b1("PriorAssignCtl.rldpEn"),**_b2("PriorAssignCtl.rldpPrior"),**_b2("PriorAssignCtl.dscpWeight"),**_b2("PriorAssignCtl.vlanWeight"),**_b2("PriorAssignCtl.portWeight"),**_b2("PriorAssignCtl.ip0AddrPrior"),**_b2("PriorAssignCtl.ip1AddrPrior"),**_bw("PriorAssignCtl.ip0AddrBit127To96"),**_bw("PriorAssignCtl.ip0MaskBit127To96"),**_bw("PriorAssignCtl.ip1AddrBit127To96"),**_bw("PriorAssignCtl.ip1MaskBit127To96"),**_bw("PriorAssignCtl.ip0AddrBit95To64"),**_bw("PriorAssignCtl.ip0MaskBit95To64"),**_bw("PriorAssignCtl.ip1AddrBit95To64"),**_bw("PriorAssignCtl.ip1MaskBit95To64")})
        A("StormCfgCtl",{**_b1("StormCfgCtl.enable"),**_bw("StormCfgCtl.delayInterval")})
        v={}
        for i in range(16): v.update(_bw(f"VlanIdCamCtl.vlanId{i}"))
        A("VlanIdCamCtl",v)
        A("Ds1qPriorMap_mem",{**_b2("Ds1qPriorMap_mem.prior")})
        A("DsDscpPriorMap_mem",{**_b2("DsDscpPriorMap_mem.prior")})
        self.cross = {}
        for a in range(4):
            for t in [0,1]: self.cross[f"DsPort_mem.aft={a}_x_piTagged={t}"]=0
        for a in range(4):
            for p in ["prIsIpv4","prIsIpv6","prIsArp","prIsLoopDetection","unknown"]: self.cross[f"DsPort_mem.aft={a}_x_{p}"]=0
        for t in [0,1]:
            for v in [0,1]: self.cross[f"piTagged={t}_x_giVlanHit={v}"]=0
        for s in range(8):
            for a in range(4): self.cross[f"DsPort_mem.stpState={s}_x_DsPort_mem.aft={a}"]=0

    def _add(self,n,b): self.points[n]=b

    def sample(self,snap,config=None):
        """每包结束调用。所有寄存器字段从 snap 直接读取（无需 config）"""
        def sv(k,d=None): return snap.get(k,d)
        a=sv("piAft",0); t=sv("giVlanTagged",0); vh=sv("giVlanHit",0); p=sv("piPrior",0); ld=sv("piLrnDisable",0)
        i4=sv("prIsIpv4",0); i6=sv("prIsIpv6",0); ia=sv("prIsArp",0); il=sv("prIsLoopDetection",0)
        pt="unknown"
        if i4: pt="prIsIpv4"
        elif i6: pt="prIsIpv6"
        elif ia: pt="prIsArp"
        elif il: pt="prIsLoopDetection"
        # DsPort_mem (trace 可观测 + 寄存器直接读)
        self._inc("DsPort_mem",f"DsPort_mem.aft={a}")
        self._inc("DsPort_mem",f"DsPort_mem.prior={p}")
        self._inc("DsPort_mem",f"DsPort_mem.lrnDisable={ld}")
        for f in ["portVid","stpState","maxMacNum","dot1qBasedVlan","keepVlanTag","portMacHi","portMacLo","allowBrg2Src","rmaMode","mirrorEn","updateMacSa","strictPvid"]:
            self._sc("DsPort_mem",f,snap)
        # DsVlan_mem
        for f in ["fid","vlanBmp","untagFlag","leakyUcast","leakyMcast","leakyBcast","leakyArp","leakyMirror","egressFilter","dot1qPriorEn","mirrorEn","prior"]:
            self._sc("DsVlan_mem",f,snap)
        # DsAcl_mem
        for f in ["action","etherType","vlanId","srcMacHi","srcMacLo"]: self._sc("DsAcl_mem",f,snap)
        # DsMac_mem
        for f in ["destMap","destDiscard","isMcast","prior"]: self._sc("DsMac_mem",f,snap)
        # DsMacAging_mem
        for f in ["aging0","aging1","aging2","aging3"]: self._sc("DsMacAging_mem",f,snap)
        # DsMacKey_mem (snap 中是 macAddrHi/macAddrLo, 合并为 macAddr)
        fid_val = sv("DsMacKey_mem.fid")
        if fid_val is not None: self._sc("DsMacKey_mem","fid",snap)
        mac_hi = sv("DsMacKey_mem.macAddrHi"); mac_lo = sv("DsMacKey_mem.macAddrLo")
        if mac_hi is not None and mac_lo is not None:
            mac_val = (mac_hi << 32) | (mac_lo & 0xFFFFFFFF)
            snap["DsMacKey_mem.macAddr"] = mac_val
            self._sc("DsMacKey_mem","macAddr",snap)
        # DsMacStatic_mem, DsMacValid_mem
        self._sc("DsMacStatic_mem","static",snap); self._sc("DsMacValid_mem","valid",snap)
        # DsStormCtrl_mem
        for f in ["enable","usePkt","cntThrd","counter","step"]: self._sc("DsStormCtrl_mem",f,snap)
        # 单例寄存器
        for rn,fl in [("L2AgingCtl",["fastAgingEn","agingEn","fastAgingAll","fastAgingByPort","portId","cycleThrd"]),("L2LearnCtl",["sysLearnNum","lruEn"]),("LoopDetectCtl",["en","ttl","loopMacHi","loopMacLo","detectInterval"]),("MirrorCtl",["srcMirrorPort","vlanMirrorPort"]),("PriorAssignCtl",["ipDscpEn","ipAddrEn","macDaEn","rldpEn","rldpPrior","dscpWeight","vlanWeight","portWeight","ip0AddrPrior","ip1AddrPrior","ip0AddrBit127To96","ip0MaskBit127To96","ip1AddrBit127To96","ip1MaskBit127To96","ip0AddrBit95To64","ip0MaskBit95To64","ip1AddrBit95To64","ip1MaskBit95To64"]),("StormCfgCtl",["enable","delayInterval"])]:
            for f in fl: self._sc(rn,f,snap)
        # VlanIdCamCtl
        for i in range(16): self._sc("VlanIdCamCtl",f"vlanId{i}",snap)
        # Ds1qPriorMap_mem, DsDscpPriorMap_mem
        self._sc("Ds1qPriorMap_mem","prior",snap); self._sc("DsDscpPriorMap_mem","prior",snap)
        # 交叉覆盖
        self._ci(f"DsPort_mem.aft={a}_x_piTagged={t}")
        self._ci(f"DsPort_mem.aft={a}_x_{pt}")
        self._ci(f"piTagged={t}_x_giVlanHit={vh}")
        s_=sv("DsPort_mem.stpState",0)
        self._ci(f"DsPort_mem.stpState={s_}_x_DsPort_mem.aft={a}")

    def _sc(self,struct,field,snap):
        """从 snapshot 读取寄存器字段值并入库"""
        k=f"{struct}.{field}"; v=snap.get(k)
        if v is None: return
        fn=f"{struct}.{field}"; b=self.points.get(struct,{})
        ex=f"{fn}={v}"
        if ex in b: b[ex]+=1
        elif v==0 and f"{fn}=0" in b: b[f"{fn}=0"]+=1
        else:
            nz=f"{fn}=nonzero"; md=f"{fn}=mid"
            if nz in b and v!=0: b[nz]+=1
            elif md in b and v!=0: b[md]+=1
            import re
            for bk in list(b.keys()):
                m=re.match(r".+=(\\d+)$",bk)
                if m and v==int(m.group(1)) and bk!=ex: b[bk]+=1; break

    def _inc(self,cp,bn):
        if cp in self.points and bn in self.points[cp]: self.points[cp][bn]+=1

    def _ci(self,k):
        if k in self.cross: self.cross[k]+=1

    def report(self):
        lines=["="*64,"  Functional Coverage Report (Full Register)","="*64]
        for n,b in self.points.items():
            c=sum(1 for v in b.values() if v>0); t=len(b); pct=100*c//t if t else 0
            bar="#"*(c*20//t)+"-"*(20-c*20//t) if t else ""
            lines.append(f"\n  Coverpoint: {n}  [{c}/{t}] {bar} {pct}%")
            for bn,cn in b.items():
                if cn>0: lines.append(f"    [>] {bn:50s} {cn:6d}")
            uc=[(bn,cn) for bn,cn in b.items() if cn==0]
            if uc:
                lines.append(f"    --- {len(uc)} uncovered ---")
                for bn,_ in uc[:5]: lines.append(f"    [x] {bn:50s}      0")
        cc=sum(1 for v in self.cross.values() if v>0)
        lines.append(f"\n  Cross Coverage  [{cc}/{len(self.cross)}]")
        for k,cn in sorted(self.cross.items()):
            mk=">" if cn>0 else "x"; lines.append(f"    [{mk}] {k:55s} {cn:4d}")
        ab=sum(len(b) for b in self.points.values())+len(self.cross)
        ac=sum(sum(1 for v in b.values() if v>0) for b in self.points.values()); ac+=sum(1 for v in self.cross.values() if v>0)
        ov=100*ac//ab if ab else 0
        lines.append(f"\n  OVERALL: {ac}/{ab} bins covered ({ov}%)"); lines.append("="*64)
        s="\n".join(lines); print(s); return s

    def to_dict(self):
        return {"points":{k:dict(v) for k,v in self.points.items()},"cross":dict(self.cross)}

    def to_json(self,path="coverage_report.json"):
        import json
        with open(path,"w") as f: json.dump(self.to_dict(),f,indent=2)
        return path

    def to_html(self,path="coverage_report.html",title="8m Switch Coverage Report",stats=None,trace_data=None):
        tb=sum(len(b) for b in self.points.values())+len(self.cross)
        cv=sum(sum(1 for v in b.values() if v>0) for b in self.points.values()); cv+=sum(1 for v in self.cross.values() if v>0)
        ov=100*cv//tb if tb else 0
        h=f'<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{title}</title><style>body{{font-family:Consolas,monospace;background:#1e1e1e;color:#d4d4d4;padding:20px}}h1{{color:#569cd6}}h2{{color:#4ec9b0;border-bottom:1px solid #333;padding-bottom:4px}}.bar{{display:inline-block;height:14px;border-radius:2px}}.bar-hit{{background:#4ec9b0}}.bar-miss{{background:#444}}.covered{{color:#4ec9b0}}.uncovered{{color:#f44747}}.bin{{margin:2px 0;font-size:13px}}.cross{{margin:1px 0;font-size:12px;color:#888}}.summary{{display:flex;gap:20px;margin:10px 0}}.card{{background:#252526;border:1px solid #333;padding:12px;border-radius:6px;flex:1}}.card .val{{font-size:24px;font-weight:bold}}table{{border-collapse:collapse;margin:10px 0;font-size:13px}}th,td{{padding:4px 10px;text-align:right;border-bottom:1px solid #333}}th{{background:#333;color:#aaa;text-align:left}}.ok{{color:#4ec9b0}}.ng{{color:#f44747}}details{{margin:2px 0}}details summary{{cursor:pointer;color:#888;font-size:12px}}details summary:hover{{color:#ccc}}</style></head><body><h1>{title}</h1>'
        if stats:
            sb=stats; h+=f'<div class="summary"><div class="card"><div class="val">{sb.get("total",0)}</div>packets</div><div class="card"><div class="val ok">{sb.get("ok",0)}</div>PASS</div><div class="card"><div class="val ng">{sb.get("ng",0)}</div>FAIL</div><div class="card"><div class="val">{ov}%</div>coverage</div></div><h2>Scoreboard</h2><table><tr><th>Type</th><th>Packets</th><th>OK</th><th>NG</th><th>Rate</th></tr>'
            for ti in sb.get("types",[]): h+=f'<tr><td>{ti["name"]}</td><td>{ti["pkts"]}</td><td class=ok>{ti["ok"]}</td><td class=ng>{ti["ng"]}</td><td>{ti["rate"]}%</td></tr>'
            h+="</table>"
        h+=f'<h2>Coverage ({ov}%)</h2>'
        for n,b in self.points.items():
            c=sum(1 for v in b.values() if v>0); t=len(b); pct=100*c//t if t else 0; bw=40*c//t if t else 0
            h+=f'<div style="margin:8px 0"><b>{n}</b> [{c}/{t}] {pct}% <span class="bar bar-hit" style="width:{bw}px"></span><span class="bar bar-miss" style="width:{40-bw}px"></span></div>'
            for bn,cn in b.items():
                if cn>0: h+=f'<div class="bin"><span class="covered">✓</span> {bn:50s} {cn:6d}</div>'
            uc=[(bn,cn) for bn,cn in b.items() if cn==0]
            for bn,_ in uc[:5]: h+=f'<div class="bin"><span class="uncovered">✗</span> {bn:50s} 0</div>'
            if len(uc)>5: h+=f'<details><summary>... +{len(uc)-5} more uncovered (click to expand)</summary>'
            for bn,_ in uc[5:]: h+=f'<div class="bin"><span class="uncovered">✗</span> {bn:50s} 0</div>'
            if len(uc)>5: h+='</details>'
        cc=sum(1 for v in self.cross.values() if v>0)
        h+=f'<h2>Cross Coverage [{cc}/{len(self.cross)}]</h2>'
        for k,cn in sorted(self.cross.items()):
            cl="covered" if cn>0 else "uncovered"
            h+=f'<div class="cross"><span class="{cl}">{"&#10003;" if cn>0 else "&#10007;"}</span> {k}</div>'
        if trace_data:
            td=trace_data; h+=f'<h2>Waveform Trace (merged) <span style="font-size:14px;color:#888">{td.get("total",0)} packets &rarr; {td.get("unique",0)} patterns</span></h2>'
            hdrs=td.get("headers",[]); rows=td.get("rows",[]); h+="<table><tr>"
            for hdr in hdrs: h+=f"<th>{hdr}</th>"
            h+="<th>sample_pkt(hex)</th></tr>"
            for row in rows:
                h+="<tr>"
                for v in row.get("vals",[]): h+=f"<td>{v}</td>"
                h+=f'<td style="font-size:11px;color:#888;text-align:left;max-width:300px;overflow:hidden">{row.get("hex","")}</td></tr>'
            h+="</table>"
        h+="</body></html>"
        with open(path,"w",encoding="utf-8") as f: f.write(h)
        return path
