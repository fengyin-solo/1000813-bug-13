<template>
  <section class="page" data-module="gate">
    <header class="page-head">
      <div>
        <h2>闸口通行管理</h2>
        <p class="page-desc">维护通行记录，围绕通行编号、车牌号码、关联箱号、进出方向做登记、筛选与状态流转。箱况等级实时取自集装箱档案，出闸放行后堆场清单同步移除。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记通行记录</button>
        <button class="btn" type="button" @click="exportRows">导出闸口通行清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <form v-if="editing" class="filter-bar" @submit.prevent="submitForm">
      <label v-for="field in editableFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="editing.values[field]" :placeholder="`请输入${field}`" />
      </label>
      <button class="btn primary" type="submit">{{ editing.id ? '保存修改' : '确认登记' }}</button>
      <button class="btn ghost" type="button" @click="editing = null">取消</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">编辑</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无闸口通行数据，可先登记通行记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条闸口通行记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatItem = { label: string; value: number }

const ENDPOINT = '/api/gate'
// 箱况等级由后端按关联箱号从集装箱档案实时带出，只读展示
const columns = ["通行编号", "车牌号码", "关联箱号", "箱况等级", "进出方向", "通行时间", "道口编号", "值守人员", "通行状态"]
const editableFields = ["通行编号", "车牌号码", "关联箱号", "进出方向", "通行时间", "道口编号", "值守人员", "通行状态"]
const actions = ["确认放行", "拦截车辆", "复核通行"]
const statuses = ["待放行", "已放行", "已拦截", "已复核"]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatItem[]>([])
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = ["通行编号", "车牌号码", "关联箱号"]
const editing = ref<{ id: number | null; values: Record<string, string> } | null>(null)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  editing.value = { id: null, values: {} }
}

function openEdit(row: Row) {
  const values: Record<string, string> = {}
  for (const field of editableFields) {
    values[field] = String(row[field] ?? '')
  }
  editing.value = { id: Number(row.id), values }
}

async function submitForm() {
  if (!editing.value) {
    return
  }
  errorMessage.value = ''
  const { id, values } = editing.value
  try {
    const response = await request(id ? `${ENDPOINT}/${id}` : ENDPOINT, {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '通行记录保存未生效，请稍后重试')
    }
    editing.value = null
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '通行记录保存失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '闸口通行动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '闸口通行操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  const keyword = filters.value[filterFields[0]]
  if (keyword) {
    params.set('keyword', keyword)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('通行记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '闸口通行列表读取失败'
  }
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) {
      stats.value = await response.json()
    }
  } catch {
    // 统计卡片读取失败不阻塞列表展示
  }
}

onMounted(reload)
</script>
