"""集装箱档案业务规则：状态流转、字段校验与筛选口径都收在这里。

箱况、箱型以档案为唯一来源：堆存记录与闸口通行只存关联箱号，
展示时通过 ``attach_archive`` 实时带上档案里的值，保证三处页面取同一份。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "container"
REQUIRED_FIELDS = ["箱号", "箱型", "箱况等级"]
EDITABLE_FIELDS = ["箱号", "箱型", "箱况等级", "所属船公司", "尺寸规格", "自重", "检验到期日", "箱体状态"]
STATUS_ORDER = ["待检", "可周转", "待修", "已报废"]
ACTION_RULES = {"登记检验": "可周转", "标记可周转": "待修", "报废箱体": "已报废"}
NEGATIVE_ACTIONS = []
# 其他模块里按关联箱号引用档案的表，改箱号时一并同步，避免引用断链
LINKED_MODULES = ("yardstore", "gate", "storage", "damage")


def archive_snapshot(container_no: str) -> dict[str, Any] | None:
    """按箱号取档案记录；未登记时返回 None。"""
    for row in store.rows(MODULE):
        if str(row.get("箱号", "")) == container_no:
            return row
    return None


def attach_archive(row: dict[str, Any]) -> dict[str, Any]:
    """给带关联箱号的记录附上档案里的箱型、箱况，档案改了这里跟着变。"""
    merged = dict(row)
    container = archive_snapshot(str(row.get("关联箱号", "")))
    merged["箱型"] = container.get("箱型", "") if container else "未登记"
    merged["箱况等级"] = container.get("箱况等级", "") if container else "未登记"
    merged["箱体状态"] = container.get("箱体状态", "") if container else "未登记"
    return merged


class ContainerService:
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
            rows = [row for row in rows if keyword in str(row.get("箱号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

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
        return entry, "集装箱已登记"

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"集装箱 {entry_id} 不存在或已归档"
        changed = {field: values[field] for field in EDITABLE_FIELDS if str(values.get(field) or "").strip()}
        if not changed:
            return None, "没有可更新的字段，请先修改再保存"
        old_no = str(entry.get("箱号", ""))
        entry.update(changed)
        new_no = str(entry.get("箱号", ""))
        if old_no and new_no and new_no != old_no:
            self._sync_container_no(old_no, new_no)
        store.save()
        return entry, "集装箱资料已更新"

    def _sync_container_no(self, old_no: str, new_no: str) -> None:
        """箱号变更时，把堆存、闸口等模块里的关联箱号一起改，保持引用不断。"""
        for module in LINKED_MODULES:
            for row in store.rows(module):
                if str(row.get("关联箱号", "")) == old_no:
                    row["关联箱号"] = new_no

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"集装箱 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于集装箱档案可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        store.save()
        return entry, f"集装箱已{action}"

    def stats(self) -> list[dict[str, Any]]:
        """统计卡片随档案实时计算，改完箱型、箱况立即反映。"""
        rows = store.rows(MODULE)
        today = date.today()

        def inspection_due(row: dict[str, Any]) -> bool:
            try:
                return date.fromisoformat(str(row.get("检验到期日", ""))) <= today
            except ValueError:
                return False

        return [
            {"label": "在册箱量", "value": sum(1 for row in rows if row.get("status") != STATUS_ORDER[-1])},
            {"label": "待修箱量", "value": sum(1 for row in rows if row.get("status") == "待修")},
            {"label": "检验到期箱量", "value": sum(1 for row in rows if inspection_due(row))},
        ]
