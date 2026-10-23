"""Independent human review for high-risk photographed areas, even after AI pass."""
from __future__ import annotations
from capture import PROTOCOL
VERSION="independent-review-1.0"
SPECS=(
 {"id":"linen_clean","name":"床品独立复查","zone":"bedroom","tasks":("bed_overview","bed_detail"),"focus":"查看床面、枕套接缝与细节，核查细线、毛发、污渍；不要只看AI框。"},
 {"id":"basin_clean","name":"台盆台面独立复查","zone":"bathroom","tasks":("basin",),"focus":"查看盆内与整块台面，区分石纹、光影与附着痕迹；不要只看AI框。"},
)

def independent_review(record,review=None):
    enabled=record.get("capture_protocol")==PROTOCOL
    review=review if review is not None else (record.get("reviews") or [{}])[-1]
    confirmations=review.get("risk_reviews",{})
    rows=[]
    if enabled:
        for spec in SPECS:
            photos=[p for p in record.get("photos",[]) if p.get("zone")==spec["zone"] and (p.get("task_id") in spec["tasks"] or p.get("kind")=="supplement") and record.get("quality",{}).get(p["id"],{}).get("usable") is True]
            expected=[p["id"] for p in photos]
            c=confirmations.get(spec["id"],{})
            complete=bool(expected) and c.get("reviewed") is True and isinstance(c.get("reason"),str) and bool(c["reason"].strip()) and isinstance(c.get("photo_ids"),list) and len(c["photo_ids"])==len(expected) and set(c["photo_ids"])==set(expected)
            rows.append({**{k:spec[k] for k in ("id","name","focus")},"photo_ids":expected,"complete":complete,"confirmation":c,"ai_status":next((i["status"] for i in record.get("items",[]) if i["id"]==spec["id"]),"unknown")})
    return {"version":VERSION,"enabled":enabled,"rows":rows,"pending":sum(not r["complete"] for r in rows),"complete":all(r["complete"] for r in rows),"changes_ai_status":False,"historical_closed_record":bool(record.get("reviews") and record["reviews"][-1].get("action") in ("release","rework"))}

def validate_risk_reviews(payload,record):
    requirements=independent_review(record)
    source=payload.get("risk_reviews",{})
    if not isinstance(source,dict):raise ValueError("独立复查记录格式无效。")
    allowed={r["id"]:r for r in requirements["rows"]};result={}
    for ident,value in source.items():
        if ident not in allowed or not isinstance(value,dict) or type(value.get("reviewed",False)) is not bool:
            raise ValueError("独立复查项目无效。")
        reason=value.get("reason","")
        ids=value.get("photo_ids",[])
        if not isinstance(reason,str) or len(reason)>1000 or not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):
            raise ValueError("独立复查依据或照片编号无效。")
        if any(i not in allowed[ident]["photo_ids"] for i in ids):raise ValueError("独立复查照片不属于该区域的可用证据。")
        result[ident]={"reviewed":value.get("reviewed") is True,"reason":reason.strip(),"photo_ids":list(ids)}
    return result
