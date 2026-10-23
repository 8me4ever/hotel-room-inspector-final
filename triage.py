"""Evidence-based workflow routing; never authorizes room release."""
from __future__ import annotations
import copy
from capture import PROTOCOL, TASKS, coverage
from adjudication import effective_view, targets, evidence_for

VERSION = "evidence-triage-1.2"
UNCERTAINTY_TYPES = {"ambiguous", "missing", "quality", "specification"}
CHECK_TASK = {check: task["id"] for task in TASKS for check in task["checks"]}

def apply_item_policy(items, mode):
    result = copy.deepcopy(items)
    for item in result:
        if mode == "live" and item["id"] == "towels" and item["status"] == "pass":
            item["policy_adjustment"] = {
                "version": VERSION, "rule": "towel_specification_requires_verification",
                "original_status": "pass", "original_evidence": item["evidence"],
            }
            item.update(status="unknown", uncertainty_type="specification",
                        evidence="\u53ef\u89c1\u5dfe\u7c7b\u6570\u91cf\u53ef\u53e6\u8bb0\uff0c\u4f46\u672c\u6f14\u793a\u7167\u7247\u6ca1\u6709\u53ef\u6838\u9a8c\u7684\u5c3a\u91cf\u6216\u914d\u7f6e\u8bc1\u636e\uff0c\u4e0d\u80fd\u76f4\u63a5\u786e\u8ba4\u6d74\u5dfe\u89c4\u683c\uff1b\u9700\u4eba\u5de5\u73b0\u573a\u6216\u914d\u7f6e\u8bb0\u5f55\u6838\u5b9e\u3002")
    return result

def plan(record):
    photos = record.get("photos", [])
    quality = record.get("quality", {})
    effective_items, review = effective_view(record)
    overrides = review.get("overrides", {})
    groups = {k: [] for k in ("direct_rework", "manual_review", "retake", "visible_pass")}
    task_coverage = coverage(photos, quality) if record.get("capture_protocol") == PROTOCOL else None
    ready_tasks = {t["id"] for t in (task_coverage or {}).get("tasks", []) if t["ready"]}
    from findings import item_findings
    for item in effective_items:
        override = overrides.get(item["id"])
        located = item_findings(item) if override is None and item["status"] != "pass" else []
        for index, candidate in enumerate(located or [item]):
            status = override["status"] if override else candidate.get("status",item["status"])
            row = {k: item.get(k) for k in ("id","name","evidence","image_id","bbox","uncertainty_type","observed_count")}
            if located:
                row.update({k:candidate.get(k) for k in ("evidence","image_id","bbox","uncertainty_type")})
                row["finding_id"]=candidate.get("id")
                if len(located)>1:row["name"] += " · %d"%(index+1)
            row.update(check_id=item["id"],original_status=item.get("original_status",item["status"]),effective_status=status,manual_override=override)
            row["review_evidence"]=evidence_for(record,item["id"],row)
            row["latest_feedback"]=candidate.get("latest_feedback")
            if status == "fail":group="direct_rework"
            elif status == "pass":group="visible_pass"
            elif row.get("uncertainty_type") in ("ambiguous","specification"):group="manual_review"
            elif row.get("uncertainty_type") in ("missing","quality"):group="retake"
            elif row.get("image_id") and quality.get(row["image_id"],{}).get("usable"):group="manual_review"
            elif task_coverage is not None:group="manual_review" if CHECK_TASK.get(item["id"]) in ready_tasks else "retake"
            else:group="manual_review" if any(p.get("zone")==item.get("zone") and quality.get(p["id"],{}).get("usable") for p in photos) else "retake"
            row["route"]=group
            groups[group].append(row)
    for index, issue in enumerate(review.get("added_issues", [])):
        groups["direct_rework"].append({"id": "manual-"+str(index), "name": "\u4eba\u5de5\u8865\u5145\u95ee\u9898", "evidence": issue, "image_id": None, "bbox": None, "route": "direct_rework", "effective_status": "fail"})
    return {"version": VERSION, "groups": groups, "counts": {k: len(v) for k, v in groups.items()},"feedback_targets":targets(record),
            "retake_tasks": [t for t in (task_coverage or {}).get("tasks", []) if not t["ready"]],
            "can_start_rework": record.get("analysis_status") == "complete" and bool(groups["direct_rework"]) and not record.get("rework_started_at") and review.get("action") not in ("release", "rework"),
            "release_authorized": False}
