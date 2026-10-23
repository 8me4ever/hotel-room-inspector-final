"""Versioned required capture tasks; supplementary photos never fill a slot."""
PROTOCOL = "standard-capture-1.0"
MAX_PHOTOS = 10
TASKS = [
    {"id":"bed_overview","name":"床铺全景","zone":"bedroom","checks":["bed_neat"],"hint":"拍全床面、枕头和被子；不能用局部近照替代。","example":"bed-clean.png"},
    {"id":"bed_detail","name":"床品细节","zone":"bedroom","checks":["linen_clean"],"hint":"拍清指定枕头和床单区域；只判断可见范围。","example":"standard-bed-detail.png"},
    {"id":"floor_scene","name":"地面与床边","zone":"bedroom","checks":["litter","floor_clean"],"hint":"拍清通道、床边和指定角落；床底盲区另行核实。","example":"standard-floor.png"},
    {"id":"basin","name":"台盆与台面","zone":"bathroom","checks":["basin_clean"],"hint":"完整展示台盆内壁、排水口和台面，避免遮挡。","example":"standard-basin.png"},
    {"id":"toilet","name":"马桶内壁与座圈","zone":"bathroom","checks":["toilet_clean"],"hint":"打开盖板，拍到座圈和内壁；不证明消毒完成。","example":"standard-toilet.png"},
    {"id":"supplies","name":"毛巾与备品","zone":"bathroom","checks":["towels","amenities"],"hint":"完整展示配置区，数量、尺寸及包装内容应可辨。","example":"standard-supplies.png"},
]
BY_ID = {t["id"]:t for t in TASKS}

def validate_photo_task(photo):
    task_id=photo.get("task_id")
    if task_id is not None and task_id not in BY_ID:
        raise ValueError("拍摄任务无效。")
    if task_id and (photo.get("kind") != "required" or photo.get("zone") != BY_ID[task_id]["zone"]):
        raise ValueError("必拍任务与照片类型或区域不一致。")
    if not task_id and photo.get("kind") != "supplement":
        raise ValueError("补充照片不能冒充必拍任务。")

def coverage(photos, quality=None):
    rows=[]
    for task in TASKS:
        assigned=[p for p in photos if p.get("task_id")==task["id"] and p.get("kind")=="required" and p.get("zone")==task["zone"]]
        ready=len(assigned)==1 and (quality is None or quality.get(assigned[0]["id"],{}).get("usable") is True)
        rows.append({"id":task["id"],"name":task["name"],"present":len(assigned)==1,"ready":ready,"image_id":assigned[0]["id"] if len(assigned)==1 else None})
    return {"protocol":PROTOCOL,"total":len(TASKS),"present":sum(r["present"] for r in rows),"ready":sum(r["ready"] for r in rows),"complete":all(r["ready"] for r in rows),"tasks":rows,"missing":[r["name"] for r in rows if not r["ready"]]}

def gate_items(items,photos,quality):
    blocked={t["id"] for t in coverage(photos,quality)["tasks"] if not t["ready"]}
    blocked_checks={c for t in TASKS if t["id"] in blocked for c in t["checks"]}
    photo_map={p["id"]:p for p in photos}
    check_task={c:t["id"] for t in TASKS for c in t["checks"]}
    for item in items:
        if item["status"]=="pass" and (item["id"] in blocked_checks or photo_map.get(item.get("image_id"),{}).get("task_id")!=check_task.get(item["id"])):
            item.update(status="unknown",uncertainty_type="missing",image_id=None,bbox=None,findings=[],evidence="必拍任务缺失或照片不可用；其他区域／补充照片不能代替该任务。")
    return items
