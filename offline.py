
"""Load previously recorded conversation vision observations for exact images."""
import hashlib
import json
from pathlib import Path
from core import CHECKS
from capture import TASKS

def offline_observations(photos, root, data_dir):
    root, data_dir = Path(root), Path(data_dir)
    try:
        bundle_bytes=(root/"observations/catalog.json").read_bytes()
        bundle=json.loads(bundle_bytes)
    except (OSError, ValueError):
        raise ValueError("离线观察记录不可用，保持无法判断；不能改用预设通过。") from None
    if bundle.get("kind")!="recorded_conversation_vision" or not isinstance(bundle.get("photos"),list):
        raise ValueError("离线观察记录格式无效。")
    known={}
    for entry in bundle["photos"]:
        digest=entry.get("sha256")
        if not isinstance(digest,str) or len(digest)!=64 or digest in known:
            raise ValueError("离线观察记录的图片标识无效或重复。")
        known[digest]=entry
    raw={"photos":[],"items":[]}
    candidates={c["id"]:[] for c in CHECKS}
    matched=0
    matched_entries=[]
    for photo in photos:
        path=data_dir/"uploads"/Path(photo["path"]).name if photo["path"].startswith("data/uploads/") else root/photo["path"]
        try:
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest=None
        entry=known.get(digest) if digest==photo.get("sha256") else None
        if entry is None or entry.get("zone")!=photo["zone"] or (photo.get("task_id") and photo["task_id"] not in entry.get("capture_tasks",[])):
            raw["photos"].append({"image_id":photo["id"],"usable":False,"reason":"未找到完全相同且区域一致的离线看图记录；没有实时识别。"})
            continue
        matched+=1
        matched_entries.append({"image_id":photo["id"],"sha256":digest,"record_id":entry.get("record_id")})
        usable=entry.get("usable") is True
        raw["photos"].append({"image_id":photo["id"],"usable":usable,"task_match":True,"reason":entry.get("quality_reason","已有对话看图观察")})
        for item in entry.get("items",[]):
            if item.get("id") not in candidates:
                continue
            candidate={**item,"image_id":photo["id"],"bbox":item.get("bbox"),"_task_id":photo.get("task_id")}
            if not usable:
                candidate.update(status="unknown",bbox=None)
            candidates[item["id"]].append(candidate)
    for check in CHECKS:
        rows=candidates[check["id"]]
        # Any observed defect wins over normal observations in the same batch.
        chosen=next((x for x in rows if x.get("status")=="fail"),None)
        preferred=next((t["id"] for t in TASKS if check["id"] in t["checks"]),None)
        chosen=chosen or next((x for x in rows if x.get("status")=="pass" and x.get("_task_id")==preferred),None)
        chosen=chosen or next((x for x in rows if x.get("_task_id")==preferred),None)
        chosen=chosen or next((x for x in rows if x.get("status")=="pass"),None)
        chosen=chosen or (rows[0] if rows else None)
        raw["items"].append(chosen or {"id":check["id"],"status":"unknown","evidence":"本项没有匹配的离线观察证据，需对话看图、接入模型或现场核实。","image_id":None,"bbox":None})
    provenance={
        "kind":"offline_conversation","label":"对话 AI 观察 · 离线回放","realtime":False,
        "matched_photos":matched,"total_photos":len(photos),"matches":matched_entries,
        "selection_policy":"task-priority-1.1","catalog_sha256":hashlib.sha256(bundle_bytes).hexdigest(),
        "limitations":bundle.get("limitations",[]),
        "position_note":"问题框为对话中估计的疑似区域，非像素级标注。",
    }
    meta={"model":"recorded-conversation-vision","usage":None,"observation_source":provenance}
    return raw,meta
