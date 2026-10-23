"""Inspection policy. Model observations never directly release a room."""
from __future__ import annotations

import copy
from capture import PROTOCOL, coverage
from findings import normalize_item_findings
from review_policy import independent_review, validate_risk_reviews, VERSION as REVIEW_POLICY_VERSION
from datetime import datetime, timezone
from uuid import uuid4

STANDARD_VERSION = "demo-standard-1.2"
CHECKS = [
    {"id": "bed_neat", "name": "床铺整理", "zone": "bedroom", "rule": "床铺与枕头整理到位，无明显散乱；正常细小褶皱不算问题。"},
    {"id": "linen_clean", "name": "床品污渍与异物", "zone": "bedroom", "rule": "可见床品无明显污渍、毛发或异物；正常布料纹理与褶皱不算问题，不能证明已更换。"},
    {"id": "litter", "name": "可见垃圾与遗留物", "zone": "bedroom", "rule": "已拍摄的地面、床边及桌面无可见垃圾或遗留物。"},
    {"id": "floor_clean", "name": "地面可见污渍", "zone": "bedroom", "rule": "已拍摄地面无明显污渍；未覆盖区域不作结论。"},
    {"id": "basin_clean", "name": "台盆与台面", "zone": "bathroom", "rule": "可见台盆与台面无明显污渍、杂物或残留。"},
    {"id": "toilet_clean", "name": "马桶可见表面", "zone": "bathroom", "rule": "可见马桶表面及内壁无明显污渍；遮挡时无法判断。"},
    {"id": "towels", "name": "浴巾配置", "zone": "bathroom", "rule": "演示房型要求2条浴巾。先记录可见巾类数量；缺少可核验尺寸或配置依据时，规格仍需人工核实。完整配置区可见才能认定数量不足。"},
    {"id": "amenities", "name": "牙具配置", "zone": "bathroom", "rule": "演示房型要求2套牙具。完整展示备品区才能核对，遮挡或不完整时无法判断。"},
]
MANUAL_CHECKS = [
    {"id": "odor", "name": "现场确认无明显异味"},
    {"id": "linen_changed", "name": "核实布草更换记录"},
    {"id": "equipment", "name": "现场检查设备及用水功能"},
    {"id": "hygiene", "name": "核实清洁消毒流程已完成"},
]
ZONES = {"bedroom": "卧室全景", "bathroom": "卫生间与备品"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unknown_items(reason="尚未分析"):
    return [{**c, "status": "unknown", "evidence": reason, "image_id": None, "bbox": None} for c in CHECKS]


def normalize_observations(raw, photos):
    """Keep usable uncertainty evidence; malformed or missing evidence cannot pass."""
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise ValueError("模型未返回约定的检查项列表，本次不能形成通过结论。")
    photo_map = {p["id"]: p for p in photos}
    quality = {}
    photo_rows = raw.get("photos", [])
    for q in photo_rows if isinstance(photo_rows, list) else []:
        if isinstance(q, dict) and isinstance(q.get("image_id"), str) and q["image_id"] in photo_map:
            task_match = q.get("task_match") is True if photo_map[q["image_id"]].get("task_id") else q.get("task_match", True) is not False
            quality[q["image_id"]] = {"usable": q.get("usable") is True and task_match, "image_usable": q.get("usable") is True, "task_match": task_match, "reason": str(q.get("reason", "未说明照片质量"))[:500]}
    indexed, duplicates = {}, set()
    for row in raw["items"]:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            if row["id"] in indexed: duplicates.add(row["id"])
            indexed[row["id"]] = row
    items = []
    for check in CHECKS:
        source = indexed.get(check["id"], {})
        item = {**check, "status": "unknown", "evidence": "未提供有效证据", "image_id": None, "bbox": None, "uncertainty_type": "missing"}
        status, image_id, evidence = source.get("status"), source.get("image_id"), source.get("evidence")
        valid_image = isinstance(image_id, str) and image_id in photo_map and photo_map[image_id]["zone"] == check["zone"] and quality.get(image_id, {}).get("usable") is True
        if check["id"] in duplicates:
            item["evidence"] = "模型对同一检查项重复输出，需人工核实"
        elif status in ("pass", "fail", "unknown") and isinstance(evidence, str) and evidence.strip():
            item["evidence"] = evidence[:1000]
            if valid_image:
                uncertainty = source.get("uncertainty_type")
                if uncertainty not in ("ambiguous", "missing", "quality", "specification"):
                    uncertainty = "specification" if status == "unknown" and check["id"] == "towels" else "ambiguous" if status == "unknown" else "none"
                item.update(status="unknown" if uncertainty != "none" else status, image_id=image_id, uncertainty_type=uncertainty)
                box = source.get("bbox")
                if isinstance(box, list) and len(box) == 4 and all(type(v) in (int, float) and 0 <= v <= 1 for v in box) and box[0] < box[2] and box[1] < box[3]:
                    item["bbox"] = box
                if type(source.get("observed_count")) is int and 0 <= source["observed_count"] <= 100:
                    item["observed_count"] = source["observed_count"]
            elif status == "unknown":
                item["uncertainty_type"] = "quality" if isinstance(image_id, str) and image_id in quality and not quality[image_id]["usable"] else "missing"
            else:
                item["evidence"] = "证据照片缺失、区域不符或照片不可用，需补拍或人工核实"
        item = normalize_item_findings(item, source if check["id"] not in duplicates else {}, photo_map, quality)
        items.append(item)
    return items, quality


def summary(items, review=None, record=None):
    if record is not None:
        from adjudication import effective_view
        items, review = effective_view(record, review)
    overrides = (review or {}).get("overrides", {})
    effective = [{**i, "effective_status": overrides.get(i["id"], {}).get("status", i["status"])} for i in items]
    counts = {s: sum(i["effective_status"] == s for i in effective) for s in ("pass", "fail", "unknown")}
    if (review or {}).get("added_issues"):
        counts["fail"] += len(review["added_issues"])
    decision = "rework" if counts["fail"] else "needs_review" if counts["unknown"] else "photo_pass"
    return {"counts": counts, "decision": decision, "label": {"rework": "发现问题 · 建议整改", "needs_review": "证据不足 · 待补拍或人工检查", "photo_pass": "照片检查通过 · 待人工确认"}[decision]}


def validate_review(payload, inspection):
    reviewer = str(payload.get("reviewer", "")).strip()
    if not reviewer:
        raise ValueError("请填写复核人。")
    overrides = payload.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("复核修改格式不正确。")
    check_ids = {i["id"] for i in CHECKS}
    for check_id, value in overrides.items():
        if check_id not in check_ids or not isinstance(value, dict) or value.get("status") not in ("pass", "fail", "unknown"):
            raise ValueError("复核检查项无效。")
        if not str(value.get("reason", "")).strip():
            raise ValueError("修改 AI 结论时，请写明现场核实依据。")
    added = payload.get("added_issues", [])
    if not isinstance(added, list) or any(not isinstance(x, str) or not x.strip() or len(x) > 1000 for x in added) or len(added) > 30:
        raise ValueError("补充问题格式不正确。")
    manual = payload.get("manual", {})
    if not isinstance(manual, dict):
        raise ValueError("现场检查格式不正确。")
    review = {
        "manual_mode":"simulated" if payload.get("manual_mode")=="simulated" else "onsite", "simulation_ack":payload.get("simulation_ack") is True,
        "reviewer": reviewer[:100], "overrides": copy.deepcopy(overrides),
        "added_issues": added, "manual": {c["id"]: manual.get(c["id"]) is True for c in MANUAL_CHECKS},
        "action": payload.get("action", "save"), "note": str(payload.get("note", ""))[:2000], "at": now(),
    }
    if review["action"] not in ("save", "rework", "release"):
        raise ValueError("复核动作无效。")
    review["risk_reviews"] = validate_risk_reviews(payload, inspection)
    review["risk_review_policy"] = REVIEW_POLICY_VERSION
    if review["action"] == "release":
        if inspection.get("capture_protocol")==PROTOCOL and not coverage(inspection["photos"],inspection.get("quality",{}))["complete"]:
            raise ValueError("必拍任务缺失或照片不可用，不能用人工勾选替代补拍。")
        if inspection.get("simulation_only") and (review["manual_mode"]!="simulated" or review["simulation_ack"] is not True):
            raise ValueError("本项目只有生成图；请明确确认现场核实为模拟，不能记录成真实现场通过。")
        if inspection.get("analysis_status") not in ("complete", "error"):
            raise ValueError("请先完成分析。")
        if summary(inspection["items"], review, record=inspection)["decision"] != "photo_pass":
            raise ValueError("仍有问题或无法判断项。请整改、补拍，或逐项填写现场核实结果。")
        if not all(review["manual"].values()):
            raise ValueError("请完成全部现场检查。")
        if not independent_review(inspection, review)["complete"]:
            raise ValueError("请完成床品和台盆台面的独立复查，逐项查看相关原图并填写依据；AI通过不能替代。")
        if payload.get("confirm_full_review") is not True:
            raise ValueError("请确认已查看全部原图并完成现场检查。")
    review["confirm_full_review"] = payload.get("confirm_full_review") is True
    return review


def new_inspection(room, photos, mode, scenario=None, parent_id=None):
    return {
        "id": uuid4().hex, "room": str(room).strip()[:60] or "演示客房",
        "created_at": now(), "standard_version": STANDARD_VERSION, "mode": mode,
        "scenario": scenario, "parent_id": parent_id, "photos": photos,
        "analysis_status": "pending", "analysis_error": None, "items": unknown_items(),
        "quality": {}, "model": None, "usage": None, "elapsed_seconds": None,
        "raw_response": None, "reviews": [], "adjudications": [], "events": [{"at": now(), "type": "created", "message": "创建本轮检查；历史复核结果不继承"}],
    }
