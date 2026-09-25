"""堆存记录业务规则：校验、状态流转、出闸联动与统计口径都收在这里。

堆存单自身的「堆存状态」描述在场生命周期；
而箱况（待检/可周转/待修/已报废）始终从集装箱档案实时取，
箱区名称始终从堆场管理实时取——堆存单不存这两份的快照。
"""
from __future__ import annotations

from typing import Any

from app.services.shared import (
    container_condition,
    find_yard,
    is_same_day,
    today_iso,
)
from app.store import store

MODULE = "yardstore"
REQUIRED_FIELDS = ["堆存单号", "关联箱号", "箱区编号"]
STATUS_ORDER = ["待进场", "堆存中", "待提离", "已提离"]
ACTION_RULES = {"确认进场": "堆存中", "确认提离": "已提离", "撤销堆存": "待进场"}
NEGATIVE_ACTIONS = ["撤销堆存"]
LEFT_STATUS = "已提离"
# 还在堆场清单里的状态；已提离默认从清单移除。
ON_SITE_STATUSES = ["待进场", "堆存中", "待提离"]


class YardstoreService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        box_no: str | None = None,
        yard_code: str | None = None,
        include_left: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("堆存单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        elif not include_left:
            rows = [row for row in rows if row.get("status") != LEFT_STATUS]
        if box_no:
            rows = [row for row in rows if box_no in str(row.get("关联箱号", ""))]
        if yard_code:
            rows = [row for row in rows if yard_code in str(row.get("箱区编号", ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._decorate(dict(row)) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._decorate(dict(entry)) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        errors = self._validate_refs(values)
        if errors:
            return None, errors
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._decorate(dict(entry)), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"堆存单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于堆存记录可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if action == "确认进场":
            errors = self._validate_refs(entry)
            if errors:
                return None, "；".join(errors)
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if target == LEFT_STATUS and not str(entry.get("堆存结束") or "").strip():
            entry["堆存结束"] = today_iso()
        return self._decorate(dict(entry)), f"堆存单已{action}"

    def mark_left_for_box(self, box_no: str) -> int:
        """闸口出闸放行联动：该箱仍在场的堆存单标记已提离，随后默认从堆场清单移除。"""
        target = str(box_no or "").strip()
        affected = 0
        for row in store.rows(MODULE):
            if (
                str(row.get("关联箱号", "")).strip() == target
                and row.get("status") != LEFT_STATUS
            ):
                row["status"] = LEFT_STATUS
                row["pending"] = False
                if not str(row.get("堆存结束") or "").strip():
                    row["堆存结束"] = today_iso()
                affected += 1
        return affected

    def stats(self) -> dict[str, object]:
        rows = store.rows(MODULE)
        cards = [
            {"label": "在场箱量", "value": sum(1 for row in rows if row.get("status") in ON_SITE_STATUSES)},
            {"label": "堆存中箱量", "value": sum(1 for row in rows if row.get("status") == "堆存中")},
            {"label": "今日进场箱量", "value": sum(
                1 for row in rows if is_same_day(row.get("堆存开始"))
            )},
            {"label": "今日提离箱量", "value": sum(
                1
                for row in rows
                if row.get("status") == LEFT_STATUS and is_same_day(row.get("堆存结束"))
            )},
        ]
        return {"cards": cards}

    def _validate_refs(self, values: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        # 延迟导入，避免与 shared 形成模块初始化环。
        from app.services.shared import find_container

        box_no = str(values.get("关联箱号") or "").strip()
        if box_no and find_container(box_no) is None:
            errors.append(f"关联箱号 {box_no} 不在集装箱档案中，请先建档")
        yard_code = str(values.get("箱区编号") or "").strip()
        if yard_code and find_yard(yard_code) is None:
            errors.append(f"箱区编号 {yard_code} 在堆场管理中不存在，无法落位")
        return errors

    def _decorate(self, view: dict[str, Any]) -> dict[str, Any]:
        box_no = str(view.get("关联箱号", "")).strip()
        yard_code = str(view.get("箱区编号", "")).strip()
        view["箱况"] = container_condition(box_no)
        view["堆存状态"] = view.get("status")
        yard = find_yard(yard_code)
        view["箱区名称"] = str(yard.get("箱区名称", "")) if yard is not None else ""
        view["位置核对"] = "一致" if yard is not None else "箱区不存在"
        return view
