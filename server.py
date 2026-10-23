"""Local hotel inspection demo. Python 3.10+, no third-party dependencies."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from core import CHECKS, MANUAL_CHECKS, STANDARD_VERSION, ZONES, new_inspection, normalize_observations, now, summary, unknown_items, validate_review
from model import call_vision, initial_config, validate_config
from access import MobileAccess
from offline import offline_observations
from capture import TASKS, PROTOCOL, MAX_PHOTOS, coverage, gate_items, validate_photo_task

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("INSPECTOR_DATA_DIR", ROOT / "data"))
from credentials import CredentialStore, CredentialError
CREDENTIALS = CredentialStore()
CONFIG = initial_config(CREDENTIALS)
LOCK = threading.RLock()
PHOTO_LABELS = {"bed-hair-detail.png": "床品细节近照", "bed-low-light.png": "卧室暗光全景", "bath-basin-stain.png": "卫生间台盆残留"}
SCENARIOS = [
    {"id": "clean", "title": "可见项目正常", "description": "卧室与卫生间齐全，展示照片通过后仍需人工确认。", "photos": [("bed-clean.png", "bedroom"), ("bath-clean.png", "bathroom")]},
    {"id": "defects", "title": "发现污渍与垃圾", "description": "床品污渍与地面纸团，展示问题定位及整改闭环。", "photos": [("bed-dirty.png", "bedroom"), ("bath-clean.png", "bathroom")]},
    {"id": "incomplete", "title": "缺少卫生间照片", "description": "只有卧室照片；未拍到的项目保持无法判断。", "photos": [("bed-clean.png", "bedroom")]},
    {"id": "hair_detail", "title": "床品细节补拍", "description": "近照可见细长异物；局部照片不能替代全景。", "photos": [("bed-hair-detail.png", "bedroom"), ("bath-clean.png", "bathroom")]},
    {"id": "basin_stain", "title": "台盆残留物", "description": "清晰可见的台盆残留，需清洁后补拍。", "photos": [("bed-clean.png", "bedroom"), ("bath-basin-stain.png", "bathroom")]},
    {"id": "low_light", "title": "卧室照片过暗", "description": "能辨认房间轮廓，但检查细节证据不足。", "photos": [("bed-low-light.png", "bedroom"), ("bath-clean.png", "bathroom")]},
]

STANDARD_BASE = [(t["example"],t["zone"],t["id"]) for t in TASKS]
SCENARIOS += [
    {"id":"standard_clean","title":"六项标准取证","description":"六类生成样例齐全；照片观察仍不等于整房达标。","capture_protocol":PROTOCOL,"photos":STANDARD_BASE},
    {"id":"standard_defect","title":"床品细节发现问题","description":"必拍照片齐全，床品细节可见疑似毛发。","capture_protocol":PROTOCOL,"photos":[("bed-hair-detail.png",z,t) if t=="bed_detail" else (f,z,t) for f,z,t in STANDARD_BASE]},
    {"id":"standard_missing","title":"缺少马桶必拍图","description":"其他照片再多也不能补足缺少的马桶任务。","capture_protocol":PROTOCOL,"photos":[p for p in STANDARD_BASE if p[2]!="toilet"]},
    {"id":"standard_dark","title":"全景过暗需补拍","description":"六项已添加不等于六项证据可用。","capture_protocol":PROTOCOL,"photos":[("bed-low-light.png",z,t) if t=="bed_overview" else (f,z,t) for f,z,t in STANDARD_BASE]},
    {"id":"standard_supplement","title":"补充图发现遗漏","description":"六项标准图之外的细节发现问题，同样阻止放房。","capture_protocol":PROTOCOL,"photos":STANDARD_BASE+[("bed-hair-detail.png","bedroom",None)]},
]


def public_config():
    with LOCK:
        return {"configured": bool(CONFIG["api_key"]) and "{" not in CONFIG["base_url"],
                "base_url": CONFIG["base_url"], "model": CONFIG["model"],
                "remember_supported": CREDENTIALS.supported, "remembered": bool(CONFIG.get("remembered")),
                "credential_source": CONFIG.get("credential_source", "none"),
                "storage_error": CONFIG.get("storage_error"),
                "last_connection_test": CONFIG.get("last_connection_test"),
                "connection_testing": bool(CONFIG.get("connection_testing"))}


def configure_model(payload):
    from urllib.parse import urlsplit
    with LOCK:
        if payload.get("clear"):
            try: CREDENTIALS.delete()
            except CredentialError: raise ValueError("本机保存未能清除，当前连接保持原状。") from None
            CONFIG.update(api_key="", remembered=False, credential_source="none", storage_error=None, last_connection_test=None)
            return public_config()
        if "remember" in payload and type(payload["remember"]) is not bool:
            raise ValueError("记住本机选项必须为布尔值。")
        remember = payload.get("remember", bool(CONFIG.get("remembered")))
        candidate = {k: payload.get(k, CONFIG[k]) for k in ("base_url", "model", "api_key")}
        provided_key = payload.get("api_key")
        if provided_key is not None and not isinstance(provided_key, str):
            raise ValueError("API Key格式无效。")
        if not str(candidate.get("api_key") or "").strip():
            candidate["api_key"] = CONFIG["api_key"]
        candidate = validate_config(candidate)
        if CONFIG["api_key"] and urlsplit(candidate["base_url"]).hostname != urlsplit(CONFIG["base_url"]).hostname and not (provided_key or "").strip():
            raise ValueError("服务地址已换到其他域名，请重新填写对应的Key。")
        try:
            if remember:
                CREDENTIALS.save(candidate)
            elif CONFIG.get("remembered"):
                CREDENTIALS.delete()
        except CredentialError:
            raise ValueError("本机凭据保存未完成，当前连接未改动；可取消记住本机后使用临时连接。") from None
        CONFIG.update(candidate, remembered=remember, remember_supported=CREDENTIALS.supported,
                      credential_source="windows_credential" if remember else "session",
                      storage_error=None, last_connection_test=None)
        return public_config()


def test_model_connection():
    with LOCK:
        if CONFIG.get("connection_testing"):
            raise ValueError("连接验证正在进行，请稍候。")
        snapshot = validate_config(CONFIG)
        CONFIG["connection_testing"] = True
    result, error = None, None
    try:
        photo = (ROOT / "assets" / "standard-bed-detail.png").read_bytes()
        record = create_record({"room": "连接验证 · 生成床品图", "mode": "live", "capture_protocol": PROTOCOL,
                                "photos": [{"name": "connection-evidence.png", "zone": "bedroom", "task_id": "bed_detail", "kind": "required",
                                            "data": base64.b64encode(photo).decode("ascii")}]})
        result = analyze_record(record["id"], config_override=snapshot)
        success = result["analysis_status"] == "complete" and result.get("observation_source", {}).get("realtime") is True and any(q.get("usable") for q in result.get("quality", {}).values())
        error = result.get("analysis_error") or (None if success else "接口已返回，但未确认图像证据可用，请查看留档。")
        check = {"at": now(), "status": "success" if success else "error", "model": result.get("model"),
                 "inspection_id": result["id"], "elapsed_seconds": result.get("elapsed_seconds"), "message": error}
        with LOCK:
            same = all(CONFIG.get(k) == snapshot[k] for k in ("api_key", "base_url", "model"))
            if same: CONFIG["last_connection_test"] = check
            CONFIG["connection_testing"] = False
        return {"success": success, "configuration_changed": not same, "test": check, "config": public_config(), "inspection": result}
    finally:
        with LOCK: CONFIG["connection_testing"] = False


@contextmanager
def database():
    connection = sqlite3.connect(DATA / "inspections.sqlite3")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "uploads").mkdir(exist_ok=True)
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS inspections (id TEXT PRIMARY KEY, body TEXT NOT NULL)")


def save(record):
    with database() as db:
        db.execute("INSERT OR REPLACE INTO inspections VALUES (?,?)", (record["id"], json.dumps(record, ensure_ascii=False)))


def get(record_id):
    with database() as db:
        row = db.execute("SELECT body FROM inspections WHERE id=?", (record_id,)).fetchone()
    if not row:
        raise ValueError("没有找到这轮检查。")
    return json.loads(row[0])


def public(record):
    result = {**record}
    result["photos"] = [{**p, "url": "/" + p["path"]} for p in record["photos"]]
    result["summary"] = summary(record["items"], record=record)
    from adjudication import effective_view
    effective_items, effective_review = effective_view(record)
    result["effective_review"] = effective_review
    result["feedback_state"] = {i["id"]:{"effective_status":effective_review.get("overrides",{}).get(i["id"],{}).get("status",i["status"]),"feedback":i.get("human_feedback",[])} for i in effective_items}
    from triage import plan
    result["triage"] = plan(record)
    from review_policy import independent_review
    result["independent_review"] = independent_review(record)
    from findings import item_findings
    result["finding_counts"] = {status: sum(f.get("status")==status for i in record["items"] for f in item_findings(i)) for status in ("fail","unknown")}
    if record.get("capture_protocol")==PROTOCOL:
        result["capture_coverage"]=coverage(record["photos"],record["quality"] if record["analysis_status"] in ("complete","error") else None)
    return result


def fixture_result(record):
    """Explicit preset observations, never used to recognize arbitrary uploads."""
    if record["scenario"] not in {"clean", "defects", "incomplete"}:
        return {"photos": [], "items": [{"id": c["id"], "status": "unknown", "evidence": "自有照片未调用真实模型，不能产生识别结论", "image_id": None, "bbox": None} for c in CHECKS]}
    by_zone = {p["zone"]: p["id"] for p in record["photos"]}
    raw = {"photos": [{"image_id": p["id"], "usable": True, "reason": "预设案例照片：清晰，可用于演示指定项目"} for p in record["photos"]], "items": []}
    for check in CHECKS:
        image_id = by_zone.get(check["zone"])
        raw["items"].append({"id": check["id"], "status": "pass" if image_id else "unknown", "evidence": "预设观察：该照片可见区域未发现本项异常" if image_id else "缺少卫生间照片，无法评估本项", "image_id": image_id, "bbox": None})
    if record["scenario"] == "defects":
        for item in raw["items"]:
            if item["id"] == "linen_clean":
                item.update(status="fail", evidence="预设观察：床单右下区域有明显棕色污渍，需现场核实并处理", bbox=[0.64, 0.49, 0.74, 0.59])
            if item["id"] == "litter":
                item.update(status="fail", evidence="预设观察：床左下方地面有纸团，需清理后补拍", bbox=[0.06, 0.81, 0.23, 0.96])
    return raw


def create_record(payload):
    mode = payload.get("mode", "demo")
    if mode not in ("demo", "live", "offline"):
        raise ValueError("分析模式无效。")
    scenario_id = payload.get("scenario")
    photos = []
    if scenario_id:
        scenario = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if not scenario:
            raise ValueError("案例不存在。")
        for entry in scenario["photos"]:
            filename,zone=entry[:2]
            task_id=entry[2] if len(entry)>2 else None
            path = ROOT / "assets" / filename
            if not path.is_file():
                raise ValueError("该案例的照片尚未准备完成。")
            photos.append({"task_id":task_id,"kind":"required" if task_id else "supplement","origin":"ai_generated","id": uuid4().hex[:12], "name": PHOTO_LABELS.get(filename, next((t["name"] for t in TASKS if t["id"]==task_id), ZONES[zone])), "zone": zone, "path": "assets/" + filename, "mime": "image/png", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    else:
        supplied = payload.get("photos", [])
        if not isinstance(supplied, list) or not 1 <= len(supplied) <= MAX_PHOTOS:
            raise ValueError("请添加1至10张生成照片。")
        prepared = []
        for source in supplied:
            if not isinstance(source, dict) or source.get("zone") not in ZONES:
                raise ValueError("请为每张照片选择拍摄区域。")
            try:
                blob = base64.b64decode(source.get("data", ""), validate=True)
            except (ValueError, TypeError):
                raise ValueError("照片编码无效。") from None
            ext = "jpg" if blob.startswith(b"\xff\xd8\xff") else "png" if blob.startswith(b"\x89PNG\r\n\x1a\n") else "webp" if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP" else None
            if not ext or not 1 <= len(blob) <= 5_000_000:
                raise ValueError("请使用不超过5MB的JPG、PNG或WebP图片。")
            if payload.get("capture_protocol")==PROTOCOL:
                validate_photo_task(source)
            from routing import verify_assignment
            verified=verify_assignment(source,hashlib.sha256(blob).hexdigest(),DATA)
            prepared.append((source, blob, ext, verified))
        for source, blob, ext, verified in prepared:
            photo_id = uuid4().hex[:12]
            filename = f"{photo_id}.{ext}"
            (DATA / "uploads" / filename).write_bytes(blob)
            photos.append({"assignment":verified,"task_id":source.get("task_id"),"kind":source.get("kind","supplement"),"origin":"ai_generated_declared","id": photo_id, "name": str(source.get("name", "上传照片"))[:150], "zone": source["zone"], "path": "data/uploads/" + filename, "mime": "image/jpeg" if ext == "jpg" else "image/" + ext, "sha256": hashlib.sha256(blob).hexdigest()})
    protocol=(scenario.get("capture_protocol") if scenario_id else payload.get("capture_protocol"))
    if protocol not in (None,PROTOCOL):
        raise ValueError("拍摄标准版本无效。")
    if protocol==PROTOCOL:
        required_ids=[p["task_id"] for p in photos if p.get("task_id")]
        if len(required_ids)!=len(set(required_ids)):
            raise ValueError("同一必拍任务只能提交一张照片，请替换原图或放入补充照片。")
    parent_id = payload.get("parent_id")
    if parent_id:
        get(parent_id)
    record = new_inspection(payload.get("room", "1208"), photos, mode, scenario_id, parent_id)
    record.update(capture_protocol=protocol,material_origin="ai_generated",simulation_only=True)
    with LOCK:
        save(record)
    return public(record)


def analyze_record(record_id, config_override=None):
    with LOCK:
        record = get(record_id)
        if record["analysis_status"] == "analyzing":
            raise ValueError("分析正在进行，请稍候。")
        if record["reviews"] or record["analysis_status"] == "complete":
            raise ValueError("本轮已有结果或人工复核。请新建一轮检查，保留历史记录。")
        record["analysis_status"] = "analyzing"
        config = dict(config_override) if config_override is not None else CONFIG.copy()
        save(record)
    started = time.monotonic()
    try:
        if record["mode"] == "demo":
            raw = fixture_result(record)
            meta = {"model": "preset-demo (no model call)", "usage": None}
        elif record["mode"] == "offline":
            raw, meta = offline_observations(record["photos"], ROOT, DATA)
        else:
            raw, meta = call_vision(config, record["photos"], ROOT, DATA)
        record["items"], record["quality"] = normalize_observations(raw, record["photos"])
        if record.get("capture_protocol")==PROTOCOL:
            record["items"]=gate_items(record["items"],record["photos"],record["quality"])
        from triage import apply_item_policy
        record["items"] = apply_item_policy(record["items"], record["mode"])
        record.update(analysis_status="complete", analysis_error=None, raw_response=raw, **meta)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "分析过程异常，本轮结果保持无法判断。"
        record.update(analysis_status="error", analysis_error=message, items=unknown_items("分析失败，需重试或逐项现场检查"))
    record["elapsed_seconds"] = round(time.monotonic() - started, 2)
    if record["analysis_status"] == "error":
        message = "本轮处理失败，保持待人工检查"
    else:
        message = {"demo": "预设流程案例；未调用模型", "offline": "按图片哈希加载对话AI观察；离线回放，未进行实时识别", "live": "实时视觉模型分析完成"}[record["mode"]]
    record["events"].append({"at": now(), "type": "analyzed", "message": message})
    with LOCK:
        save(record)
    return public(record)


def review_record(record_id, payload):
    with LOCK:
        record = get(record_id)
        if record["analysis_status"] in ("pending", "analyzing"):
            raise ValueError("请先完成本轮分析。")
        if record.get("rework_started_at") or (record["reviews"] and record["reviews"][-1]["action"] in ("release", "rework")):
            raise ValueError("本轮检查已结束，请创建整改复查或新检查。")
        review = validate_review(payload, record)
        record["reviews"].append(review)
        record["events"].append({"at": review["at"], "type": "reviewed", "message": f"{review['reviewer']}：" + {"save": "保存复核草稿", "rework": "要求整改/补拍", "release": "演示放房（现场核实为模拟）" if review.get("manual_mode")=="simulated" else "人工确认放房（本地演示状态）"}[review["action"]]})
        save(record)
    return public(record)



def adjudicate_record(record_id,payload):
    from adjudication import validate_feedback
    with LOCK:
        record=get(record_id)
        entry=validate_feedback(record,payload)
        previous=next((a for a in record.get("adjudications",[]) if a["id"]==entry["id"]),None)
        if previous:
            keys=("target_id","reviewer","outcome","reason","issue_type","issue_description","basis","basis_reference","photo_ids")
            if any(previous.get(k)!=entry.get(k) for k in keys):raise ValueError("同一提交编号的内容不同，请重新提交。")
            return public(record)
        record.setdefault("adjudications",[]).append(entry)
        record["events"].append({"at":entry["at"],"type":"human_adjudication","message":entry["reviewer"]+"："+{"issue":"确认是问题","no_issue":"确认不是问题","inconclusive":"仍无法判断"}[entry["outcome"]]+"；依据已留档，未改写原始AI观察。"})
        save(record)
    return public(record)

def export_adjudications():
    from adjudication import training_rows
    with LOCK,database() as db:
        records=[json.loads(r[0]) for r in db.execute("SELECT body FROM inspections ORDER BY rowid")]
    return "".join(json.dumps(row,ensure_ascii=False)+"\n" for record in records for row in training_rows(record)).encode("utf-8")

def start_rework_record(record_id, payload):
    """A cleaner accepts visible issues, without creating a supervisor review."""
    from triage import plan
    with LOCK:
        record = get(record_id)
        if not plan(record)["can_start_rework"]:
            raise ValueError("本轮没有可直接整改的问题，或已结束；疑点需复核，证据不足需补图。")
        record["rework_started_at"] = now()
        record["rework_actor"] = str(payload.get("actor", "演示保洁")).strip()[:100] or "演示保洁"
        record["rework_item_ids"] = list(dict.fromkeys(row.get("check_id",row["id"]) for row in plan(record)["groups"]["direct_rework"]))
        record["events"].append({"at": record["rework_started_at"], "type": "cleaner_rework", "message": record["rework_actor"]+"：按已标明问题开始整改；未创建主管复核，整改后另开关联批次。"})
        save(record)
    return public(record)


def submit_record(record_id):
    with LOCK:
        record = get(record_id)
        if record["analysis_status"] not in ("complete", "error"):
            raise ValueError("请先完成本轮检查。")
        if record.get("rework_started_at") or (record["reviews"] and record["reviews"][-1]["action"] in ("release", "rework")):
            raise ValueError("本轮已结束，请创建新检查。")
        if not record.get("submitted_at"):
            record["submitted_at"] = now()
            record["events"].append({"at": record["submitted_at"], "type": "submitted", "message": "保洁提交主管复核；房间保持待确认"})
            save(record)
    return public(record)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Do not log request bodies, API keys or uploaded content.
        pass

    def json_response(self, status, value, cookie=None):
        wire = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(wire)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(wire)

    def check_origin(self):
        self.server.mobile_access.check_origin(self.headers.get("Host"), self.headers.get("Origin"))

    def check_access(self):
        if not self.server.mobile_access.authorized(self.client_address[0], self.headers.get("Cookie")):
            raise PermissionError("请先输入电脑页面显示的手机连接码。")

    def local_client(self):
        return self.server.mobile_access.is_local(self.client_address[0])

    def do_GET(self):
        try:
            self.check_origin()
            path = self.path.split("?", 1)[0]
            if path.startswith(("/api/", "/data/uploads/")):
                self.check_access()
            if path == "/api/access":
                return self.json_response(200, self.server.mobile_access.info(self.local_client()))
            if path == "/api/bootstrap":
                return self.json_response(200, {"routing_enabled":True,"capture_tasks":TASKS,"capture_protocol":PROTOCOL,"max_photos":MAX_PHOTOS,"synthetic_only":True,"checks": CHECKS, "manual_checks": MANUAL_CHECKS, "standard_version": STANDARD_VERSION, "zones": ZONES, "access": self.server.mobile_access.info(self.local_client()), "scenarios": [{**{k: v for k, v in s.items() if k != "photos"}, "photos": [{"file": entry[0], "zone": entry[1], "task_id":entry[2] if len(entry)>2 else None,"kind":"required" if len(entry)>2 and entry[2] else "supplement","name":PHOTO_LABELS.get(entry[0], next((t["name"] for t in TASKS if len(entry)>2 and t["id"]==entry[2]),ZONES[entry[1]]))} for entry in s["photos"]]} for s in SCENARIOS], "config": public_config()})
            if path == "/api/history":
                with LOCK, database() as db:
                    records = [public(json.loads(row[0])) for row in db.execute("SELECT body FROM inspections ORDER BY rowid DESC LIMIT 60")]
                return self.json_response(200, [{k: r.get(k) for k in ("id", "room", "created_at", "mode", "analysis_status", "summary", "reviews", "parent_id", "submitted_at", "observation_source", "rework_started_at", "replayed_from")} for r in records])
            if path == "/api/feedback/export":
                if not self.local_client():raise PermissionError("请在启动服务的电脑上导出完整人工裁决数据。")
                content=export_adjudications()
                self.send_response(200)
                self.send_header("Content-Type","application/x-ndjson; charset=utf-8")
                self.send_header("Content-Disposition",'attachment; filename="human-adjudications.jsonl"')
                self.send_header("Content-Length",str(len(content)))
                self.send_header("Cache-Control","no-store")
                self.end_headers();self.wfile.write(content)
                return
            if path.startswith("/api/inspections/"):
                return self.json_response(200, public(get(path.rsplit("/", 1)[1])))
            relative = "static/index.html" if path == "/" else path.lstrip("/")
            allowed = relative.startswith(("static/", "assets/", "data/uploads/"))
            if not allowed:
                return self.json_response(404, {"error": "文件不存在"})
            if relative.startswith("data/uploads/"):
                file = DATA / "uploads" / Path(relative).name
            else:
                file = (ROOT / relative).resolve()
                if not file.is_relative_to(ROOT / "static") and not file.is_relative_to(ROOT / "assets"):
                    return self.json_response(404, {"error": "文件不存在"})
            if not file.is_file():
                return self.json_response(404, {"error": "文件不存在"})
            content = file.read_bytes()
            self.send_response(200)
            mime = {".js": "application/javascript", ".css": "text/css", ".html": "text/html"}.get(file.suffix.lower()) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else ""))
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except PermissionError as exc:
            self.json_response(403, {"error": str(exc), "pair_required": True})
        except ValueError as exc:
            self.json_response(400, {"error": str(exc)})

    def do_POST(self):
        try:
            self.check_origin()
            if "application/json" not in self.headers.get("Content-Type", ""):
                raise ValueError("请发送JSON请求。")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 42_000_000:
                raise ValueError("请求大小无效或照片过大。")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("请求格式不正确。")
            path = self.path.split("?", 1)[0]
            if path == "/api/pair":
                cookie = self.server.mobile_access.pair(self.client_address[0], payload.get("code", ""))
                return self.json_response(200, {"paired": True}, cookie=cookie)
            self.check_access()
            if path in ("/api/config", "/api/config/test"):
                if not self.local_client():
                    raise ValueError("请在启动服务的电脑上配置或验证模型。")
                return self.json_response(200, configure_model(payload) if path == "/api/config" else test_model_connection())
            if path == "/api/photos/route":
                from routing import route
                with LOCK:
                    routing_config=CONFIG.copy()
                return self.json_response(200,route(payload,routing_config,ROOT,DATA))
            if path == "/api/inspections":
                return self.json_response(201, create_record(payload))
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "inspections"]:
                if parts[3] == "adjudications":
                    return self.json_response(200,adjudicate_record(parts[2],payload))
                if parts[3] == "start-rework":
                    return self.json_response(200, start_rework_record(parts[2], payload))
                if parts[3] == "submit":
                    return self.json_response(200, submit_record(parts[2]))
                if parts[3] == "analyze":
                    return self.json_response(200, analyze_record(parts[2]))
                if parts[3] == "review":
                    return self.json_response(200, review_record(parts[2], payload))
            self.json_response(404, {"error": "接口不存在"})
        except PermissionError as exc:
            self.json_response(403, {"error": str(exc), "pair_required": True})
        except (ValueError, TypeError) as exc:
            self.json_response(400, {"error": str(exc)})
        except Exception:
            self.json_response(500, {"error": "本地服务处理失败，请保留当前页面并重试。"})


def main():
    parser = argparse.ArgumentParser(description="Local hotel room inspection demo")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--lan", action="store_true", help="Enable paired access from phones on a private network")
    parser.add_argument("--address", action="append", default=None, help="Optional private IPv4 host to allow for LAN access")
    args = parser.parse_args()
    initialize()
    # A restarted process cannot complete a previous in-flight request.
    with LOCK, database() as db:
        interrupted = [json.loads(row[0]) for row in db.execute("SELECT body FROM inspections")]
    for record in interrupted:
        if record["analysis_status"] == "analyzing":
            record.update(analysis_status="error", analysis_error="上次分析因服务中断未完成，请重试。", items=unknown_items("分析中断，待重试"))
            save(record)
    server = ThreadingHTTPServer(("0.0.0.0" if args.lan else "127.0.0.1", args.port), Handler)
    server.mobile_access = MobileAccess(args.port, lan=args.lan, addresses=args.address)
    print(f"Hotel inspection demo: http://127.0.0.1:{args.port}", flush=True)
    print(f"Project: {ROOT}\nData: {DATA}", flush=True)
    if args.lan:
        for address in server.mobile_access.addresses:
            print(f"Phone address: http://{address}:{args.port}/", flush=True)
        print("Phone pairing code: open My > Phone access on the local computer page.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
