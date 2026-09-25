"""堆存记录业务规则：状态流转、字段校验与筛选口径都收在这里。

堆场清单只列仍在堆场的箱子：已提离（含闸口放行出闸联动）的记录
默认不再出现，需要查历史时按状态筛选。箱况、箱型实时取集装箱档案。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.container import archive_snapshot, attach_archive
from app.store import store

MODULE = "yardstore"
REQUIRED_FIELDS = ["堆存单号", "关联箱号", "箱区编号"]
EDITABLE_FIELDS = ["堆存单号", "关联箱号", "箱区编号", "贝位号", "堆存开始", "堆存结束", "堆存天数", "堆存状态"]
STATUS_ORDER = ["待进场", "堆存中", "待提离", "已提离"]
ACTION_RULES = {"确认进场": "堆存中", "确认提离": "已提离", "撤销堆存": "待进场"}
NEGATIVE_ACTIONS = ["撤销堆存"]
DEPARTED_STATUS = "已提离"


def _yard_ids() -> set[str]:
    return {str(row.get("箱区编号", "")) for row in store.rows("yard")}


class YardstoreService:
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
            rows = [row for row in rows if keyword in str(row.get("堆存单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        else:
            # 堆场清单只列在堆箱子，已提离的走状态筛选查看历史
            rows = [row for row in rows if row.get("status") != DEPARTED_STATUS]
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
        error = self._check_refs(values)
        if error:
            return None, error
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field, "") for field in EDITABLE_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        store.save()
        return entry, "堆存单已登记"

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"堆存单 {entry_id} 不存在或已归档"
        changed = {field: values[field] for field in EDITABLE_FIELDS if str(values.get(field) or "").strip()}
        if not changed:
            return None, "没有可更新的字段，请先修改再保存"
        error = self._check_refs({**entry, **changed})
        if error:
            return None, error
        entry.update(changed)
        store.save()
        return entry, "堆存单已更新"

    def _check_refs(self, values: dict[str, Any]) -> str:
        """关联箱号要在档案里、箱区编号要在堆场里，否则堆存单对不上实际位置。"""
        container_no = str(values.get("关联箱号", "")).strip()
        if container_no and archive_snapshot(container_no) is None:
            return f"关联箱号 {container_no} 未在集装箱档案登记，请先在档案中维护"
        yard_no = str(values.get("箱区编号", "")).strip()
        if yard_no and yard_no not in _yard_ids():
            return f"箱区编号 {yard_no} 在堆场管理中不存在，请核对实际位置"
        return ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"堆存单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于堆存记录可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if target == "堆存中" and not str(entry.get("堆存开始", "")).strip():
            entry["堆存开始"] = date.today().isoformat()
        if target == DEPARTED_STATUS:
            entry["提离时间"] = date.today().isoformat()
        store.save()
        return entry, f"堆存单已{action}"

    def mark_departed(self, container_no: str) -> int:
        """闸口放行出闸后，把该箱号仍在堆场清单里的堆存单一并提离。"""
        moved = 0
        for row in store.rows(MODULE):
            if str(row.get("关联箱号", "")) == container_no and row.get("status") != DEPARTED_STATUS:
                row["status"] = DEPARTED_STATUS
                row["pending"] = False
                row["提离时间"] = date.today().isoformat()
                moved += 1
        if moved:
            store.save()
        return moved

    def stats(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        today = date.today().isoformat()
        return [
            {"label": "堆存中箱量", "value": sum(1 for row in rows if row.get("status") == "堆存中")},
            {"label": "今日进场箱量", "value": sum(1 for row in rows if str(row.get("堆存开始", "")) == today)},
            {"label": "今日提离箱量", "value": sum(1 for row in rows if str(row.get("提离时间", "")) == today)},
        ]
