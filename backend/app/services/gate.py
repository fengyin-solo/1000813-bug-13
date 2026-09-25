"""闸口通行业务规则：校验、状态流转、出闸联动与统计口径都收在这里。

通行记录上的箱况直接取自集装箱档案，三处看到的永远是同一份；
出闸放行后联动堆存记录，把对应箱子标记已提离并从堆场清单移除。
"""
from __future__ import annotations

from typing import Any

from app.services.shared import container_condition, is_same_day
from app.services.yardstore import YardstoreService
from app.store import store

MODULE = "gate"
REQUIRED_FIELDS = ["通行编号", "车牌号码", "关联箱号"]
STATUS_ORDER = ["待放行", "已放行", "已拦截", "已复核"]
ACTION_RULES = {"确认放行": "已放行", "拦截车辆": "已拦截", "复核通行": "已复核"}
NEGATIVE_ACTIONS = []
OUTBOUND = "出闸"

_yardstore_service = YardstoreService()


class GateService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        box_no: str | None = None,
        direction: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("通行编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if box_no:
            rows = [row for row in rows if box_no in str(row.get("关联箱号", ""))]
        if direction:
            rows = [row for row in rows if str(row.get("进出方向", "")) == direction]
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
        # 延迟导入，避免模块初始化阶段相互引用。
        from app.services.shared import find_container

        box_no = str(values.get("关联箱号") or "").strip()
        if find_container(box_no) is None:
            return None, [f"关联箱号 {box_no} 不在集装箱档案中，请先建档"]
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
        # 出闸放行是离场动作：同步关闭该箱仍在场的堆存单。
        if action == "确认放行" and str(entry.get("进出方向", "")).strip() == OUTBOUND:
            affected = _yardstore_service.mark_left_for_box(entry.get("关联箱号", ""))
            if affected:
                message += f"，箱 {entry.get('关联箱号')} 的 {affected} 张堆存单已同步标记已提离"
        return self._decorate(dict(entry)), message

    def stats(self) -> dict[str, object]:
        rows = store.rows(MODULE)
        released = [row for row in rows if row.get("status") == "已放行"]
        cards = [
            {"label": "今日进闸车次", "value": sum(
                1 for row in released if str(row.get("进出方向", "")) != OUTBOUND
                and is_same_day(row.get("通行时间"))
            )},
            {"label": "今日出闸车次", "value": sum(
                1 for row in released if str(row.get("进出方向", "")) == OUTBOUND
                and is_same_day(row.get("通行时间"))
            )},
            {"label": "拦截车次", "value": sum(1 for row in rows if row.get("status") == "已拦截")},
        ]
        return {"cards": cards}

    def _decorate(self, view: dict[str, Any]) -> dict[str, Any]:
        view["箱况"] = container_condition(str(view.get("关联箱号", "")).strip())
        view["通行状态"] = view.get("status")
        return view
