"""Validated locations for each observed issue. Never invent locations."""
from __future__ import annotations

def valid_box(box):
    return isinstance(box,list) and len(box)==4 and all(type(v) in (int,float) and 0<=v<=1 for v in box) and box[0]<box[2] and box[1]<box[3]

def item_findings(item):
    if isinstance(item.get("findings"),list):return item["findings"]
    if item.get("status") in ("fail","unknown") and item.get("image_id"):
        return [{k:item.get(k) for k in ("status","evidence","image_id","bbox","uncertainty_type")}]
    return []

def normalize_item_findings(item,source,photos,quality):
    explicit="findings" in source
    if not explicit:
        rows=item_findings(item)
        item["findings"]=[{**r,"id":item["id"]+"-01","source":"legacy_single"} for r in rows]
        return item
    supplied=source["findings"]
    if not isinstance(supplied,list):
        item.update(status="unknown",image_id=None,bbox=None,uncertainty_type="ambiguous",evidence="模型的问题位置列表格式无效，需人工核实。",findings=[])
        return item
    accepted=[];invalid=max(0,len(supplied)-20);seen=set()
    for row in supplied[:20]:
        if not isinstance(row,dict) or row.get("status") not in ("fail","unknown") or not isinstance(row.get("evidence"),str) or not row["evidence"].strip():
            invalid+=1;continue
        photo_id=row.get("image_id")
        if not isinstance(photo_id,str) or photo_id not in photos or photos[photo_id].get("zone")!=item["zone"] or quality.get(photo_id,{}).get("usable") is not True:
            invalid+=1;continue
        uncertainty=row.get("uncertainty_type")
        if uncertainty not in ("none","ambiguous","missing","quality","specification"):
            uncertainty="ambiguous" if row["status"]=="unknown" else "none"
        if row["status"]=="unknown" and uncertainty=="none":uncertainty="ambiguous"
        status="unknown" if uncertainty!="none" else row["status"]
        box=row.get("bbox") if valid_box(row.get("bbox")) else None
        entry={"id":item["id"]+"-%02d"%(len(accepted)+1),"source":"model_multi","status":status,"evidence":row["evidence"].strip()[:1000],"image_id":photo_id,"bbox":box,"uncertainty_type":uncertainty}
        signature=(status,photo_id,tuple(box or []),entry["evidence"])
        if signature in seen:continue
        seen.add(signature);accepted.append(entry)
    item["findings"]=accepted
    if invalid:item["invalid_finding_count"]=invalid
    primary=next((f for f in accepted if f["status"]=="fail"),None) or next(iter(accepted),None)
    if primary:
        old=item["status"]
        item.update(status=primary["status"],image_id=primary["image_id"],bbox=primary["bbox"],uncertainty_type=primary["uncertainty_type"])
        if old!=item["status"]:
            item["aggregation_adjustment"]={"original_status":source.get("status"),"rule":"findings_determine_check_status"}
            item["evidence"]=primary["evidence"]
    elif invalid or source.get("status")=="fail":
        item.update(status="unknown",image_id=None,bbox=None,uncertainty_type="ambiguous",evidence="问题定位证据未通过校验，需人工核实，不能视为通过。")
    return item
