"""集装箱档案业务规则：箱况唯一来源、字段校验、修改与统计口径都收在这里。

档案、堆存、闸口三处看到的箱况都取自这里的 status，
堆存单与闸口记录不允许再各自保存一份箱况快照。
"""
from __future__ import annotations

from typing import Any

from app.services.shared import today_iso
from app.store import store

MODULE = "container"
REQUIRED_FIELDS = ["箱号", "箱型", "箱况等级"]
# 档案里可直接维护的资料字段；箱号是主键、status 由动作流转，均不在此列。
EDITABLE_FIELDS = ["箱型", "箱况等级", "所属船公司", "尺寸规格", "自重", "检验到期日"]
STATUS_ORDER = ["待检", "可周转", "待修", "已报废"]
ACTION_RULES = {"登记检验": "可周转", "标记可周转": "待修", "报废箱体": "已报废"}
NEGATIVE_ACTIONS = []


class ContainerService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        box_type: str | None = None,
        grade: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("箱号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if box_type:
            rows = [row for row in rows if str(row.get("箱型", "")) == box_type]
        if grade:
            rows = [row for row in rows if grade in str(row.get("箱况等级", ""))]
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
        rows = store.rows(MODULE)
        box_no = str(values.get("箱号")).strip()
        if any(str(row.get("箱号", "")).strip() == box_no for row in rows):
            return None, [f"箱号 {box_no} 已在档案中登记，不能重复建档"]
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._decorate(dict(entry)), []

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """修改档案资料（如改箱型）。只落主数据这一处，其他页面下次读取即跟随。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, [f"集装箱 {entry_id} 不存在或已归档"]
        box_type = str(values.get("箱型") or "").strip()
        if not box_type:
            return None, ["箱型不能为空"]
        for field in EDITABLE_FIELDS:
            if field in values:
                entry[field] = values[field]
        return self._decorate(dict(entry)), []

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
        return self._decorate(dict(entry)), f"集装箱已{action}"

    def stats(self) -> dict[str, object]:
        """统计口径全部实时计算，箱型分布随档案修改立刻变化。"""
        rows = store.rows(MODULE)
        today = today_iso()
        type_counts: dict[str, int] = {}
        for row in rows:
            box_type = str(row.get("箱型", "")) or "未分类"
            type_counts[box_type] = type_counts.get(box_type, 0) + 1
        due = [row for row in rows if str(row.get("检验到期日", ""))[:10] <= today]
        cards = [
            {"label": "在册箱量", "value": len(rows)},
            {"label": "可周转箱量", "value": sum(1 for row in rows if row.get("status") == "可周转")},
            {"label": "待修箱量", "value": sum(1 for row in rows if row.get("status") == "待修")},
            {"label": "检验到期箱量", "value": len(due)},
        ]
        for box_type, count in sorted(type_counts.items()):
            cards.append({"label": f"箱型 {box_type}", "value": count})
        return {"cards": cards}

    def _decorate(self, view: dict[str, Any]) -> dict[str, Any]:
        """展示层看到的箱体状态永远等于流程箱况，杜绝两份状态对不上。"""
        view["箱体状态"] = view.get("status")
        return view
