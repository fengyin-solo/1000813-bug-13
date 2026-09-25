"""闸口通行业务规则：状态流转、字段校验与筛选口径都收在这里。

确认放行且方向为出闸时，联动把该箱号仍在堆场清单里的堆存单提离，
箱子出闸后不再挂在堆场清单上。箱况、箱型实时取集装箱档案。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.container import attach_archive
from app.services.yardstore import YardstoreService
from app.store import store

MODULE = "gate"
REQUIRED_FIELDS = ["通行编号", "车牌号码", "关联箱号"]
EDITABLE_FIELDS = ["通行编号", "车牌号码", "关联箱号", "进出方向", "通行时间", "道口编号", "值守人员", "通行状态"]
STATUS_ORDER = ["待放行", "已放行", "已拦截", "已复核"]
ACTION_RULES = {"确认放行": "已放行", "拦截车辆": "已拦截", "复核通行": "已复核"}
NEGATIVE_ACTIONS = []

yardstore_service = YardstoreService()


class GateService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("通行编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [attach_archive(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return attach_archive(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field, "") for field in EDITABLE_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        store.save()
        return entry, "通行记录已登记"

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"通行记录 {entry_id} 不存在或已归档"
        changed = {field: values[field] for field in EDITABLE_FIELDS if str(values.get(field) or "").strip()}
        if not changed:
            return None, "没有可更新的字段，请先修改再保存"
        entry.update(changed)
        store.save()
        return entry, "通行记录已更新"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"通行记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于闸口通行可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        message = f"通行记录已{action}"
        if action == "确认放行" and "出" in str(entry.get("进出方向", "")):
            moved = yardstore_service.mark_departed(str(entry.get("关联箱号", "")))
            if moved:
                message += f"，堆场清单已同步移除 {moved} 条堆存单"
        store.save()
        return entry, message

    def stats(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        today = date.today().isoformat()
        return [
            {"label": "今日进闸车次", "value": sum(1 for row in rows if str(row.get("通行时间", "")) == today and "进" in str(row.get("进出方向", "")))},
            {"label": "今日出闸车次", "value": sum(1 for row in rows if str(row.get("通行时间", "")) == today and "出" in str(row.get("进出方向", "")))},
            {"label": "拦截车次", "value": sum(1 for row in rows if row.get("status") == "已拦截")},
        ]
