"""Bounded local diagnostics: user input, validated plans and execution receipts."""

import json
import re
import time
import uuid
from pathlib import Path

from .translation import atomic_json, state_directory
from .annotations import tool_annotation


def safe(value, depth=0):
    if depth > 4:
        return "[内容已截断]"
    if isinstance(value, dict):
        return {str(k)[:100]: "[已隐藏]" if re.search(r"cookie|password|secret|authorization|api.?key|access.?token|refresh.?token|^token$", str(k), re.I) else safe(v, depth + 1) for k, v in list(value.items())[:20]}
    if isinstance(value, (list, tuple)):
        return [safe(v, depth + 1) for v in value[:20]]
    if isinstance(value, str):
        text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}|\bBearer\s+\S+", "[已隐藏]", value, flags=re.I)
        text = re.sub(r"((?:MUSIC_U|MUSIC_A|__csrf|password|api_key|token)\s*[=:]\s*)[^\s;&]+", r"\1[已隐藏]", text, flags=re.I)
        return text[:4000]
    return value if value is None or isinstance(value, (bool, int, float)) else str(type(value).__name__)


def arguments(value):
    value = safe(value or {})
    encoded = json.dumps(value, ensure_ascii=False)
    return value if len(encoded) <= 4000 else {"preview": encoded[:4000], "truncated": True}


def describe(tool, args=None, name=None):
    name = name or getattr(tool, "name", "unknown")
    key = getattr(tool, "key", None)
    annotation = tool_annotation(name, getattr(tool, "description", ""), key)
    return {
        "name": name, "title": annotation["title_zh"],
        "command": "/" + key.split(":", 1)[1] if isinstance(key, str) and ":" in key else None,
        "plugin": key.split(":", 1)[0] if isinstance(key, str) and ":" in key else None,
        "arguments": arguments(args),
    }


def receipt(result):
    if isinstance(result, dict):
        body = result
    else:
        text = "\n".join(block.text for block in getattr(result, "content", []) if getattr(block, "type", "") == "text")
        try:
            body = json.loads(text)
        except (ValueError, TypeError):
            body = {}
    if not isinstance(body, dict):
        body = {}
    summary = {key: safe(body[key]) for key in ("status", "sent", "code", "reason", "error_type", "must_not_claim_done", "do_not_retry") if key in body}
    if getattr(result, "isError", False):
        summary["status"] = "failed"
    summary.setdefault("status", "returned" if result is not None else "no_receipt")
    if not isinstance(summary["status"], str):
        summary["status"] = "returned"
    return summary


class RouteRecords:
    def __init__(self, directory=None, limit=500):
        self.path = Path(directory or state_directory()) / "route_records.json"
        self.limit = limit
        self.storage_error = None
        self.rows = []
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("records"), list):
                    raise ValueError("Invalid records")
                if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("executions"), list) for row in data["records"]):
                    raise ValueError("Invalid record entry")
                self.rows = data["records"][-limit:]
            except (OSError, ValueError):
                self.storage_error = "记录文件无法读取，已停止覆盖保存"
        for row in self.rows:
            if row.get("status") == "analyzing":
                row["status"] = "interrupted"
            for call in row.get("executions", []):
                if call.get("status") == "running":
                    call["status"] = "unknown"

    def save(self):
        self.rows = self.rows[-self.limit:]
        if self.storage_error:
            raise OSError(self.storage_error)
        atomic_json(self.path, {"records": self.rows})

    def find(self, identity):
        return next((row for row in reversed(self.rows) if row["id"] == identity), None)

    def begin(self, event):
        old = event.get_extra("_intent_bridge_record_id", None)
        if old and self.find(old):
            return old
        text = str(event.message_str or "")
        identity = uuid.uuid4().hex[:16]
        self.rows.append({
            "id": identity, "at": time.time(), "updated_at": time.time(),
            "message_id": str(getattr(event.message_obj, "message_id", ""))[:100],
            "session": str(event.unified_msg_origin)[:200], "user_text": safe(text),
            "input_truncated": len(text) > 4000, "analysis_truncated": len(text) > 1600,
            "status": "analyzing", "planned": [], "executions": [], "dispatch": {}, "events": [],
        })
        event.set_extra("_intent_bridge_record_id", identity)
        self.save()
        return identity

    def patch(self, identity, **fields):
        row = self.find(identity)
        if row:
            row.update(fields, updated_at=time.time())
            self.save()

    def stage(self, identity, stage, **detail):
        row = self.find(identity)
        if row:
            row["events"] = (row["events"] + [{"at": time.time(), "stage": stage, **safe(detail)}])[-12:]
            self.save()

    def dispatch(self, identity, name, status):
        row = self.find(identity)
        if row:
            row["dispatch"][name] = status
            self.save()

    def start_call(self, identity, tool, args, via, name=None):
        row = self.find(identity)
        if row:
            call_id = uuid.uuid4().hex[:12]
            row["executions"].append({"id": call_id, "at": time.time(), "via": via, "status": "running", **describe(tool, args, name)})
            row["executions"] = row["executions"][-20:]
            self.save()
            return call_id

    def end_call(self, identity, call_id, result):
        row = self.find(identity)
        if row:
            call = next((call for call in row["executions"] if call["id"] == call_id), None)
            if call:
                summary = receipt(result)
                call.update(status=summary["status"], result=summary, duration_ms=round((time.time() - call["at"]) * 1000))
                row["updated_at"] = time.time()
                self.save()

    def finish(self, identity):
        row = self.find(identity)
        if row:
            if row["status"] == "analyzing":
                row["status"] = "analysis_incomplete"
            for call in row["executions"]:
                if call["status"] == "running":
                    call["status"] = "unknown"
            self.patch(identity, finished_at=time.time())

    def query(self, offset=0, limit=30, query="", category="all"):
        if category not in {"all", "called", "uncalled"}:
            raise ValueError("Invalid record category")
        query = query.strip().casefold()
        counts = {"called": sum(bool(row.get("executions")) for row in self.rows),
                  "uncalled": sum(not row.get("executions") for row in self.rows)}
        rows = sorted(self.rows, key=lambda row: row["at"], reverse=True)
        if category != "all":
            rows = [row for row in rows if bool(row.get("executions")) == (category == "called")]
        if query:
            rows = [row for row in rows if query in json.dumps(row, ensure_ascii=False).casefold()]
        offset = min(offset, max(0, (len(rows) - 1) // limit * limit)) if rows else 0
        return {"items": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit, "retention": self.limit, "storage_error": self.storage_error, "category": category, "counts": counts}
