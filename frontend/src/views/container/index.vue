<template>
  <section class="page" data-module="container">
    <header class="page-head">
      <div>
        <h2>集装箱档案管理</h2>
        <p class="page-desc">维护集装箱，围绕箱号、箱型、箱况等级、所属船公司做登记、筛选与状态流转。档案是箱况的唯一来源，堆存与闸口展示同一份箱况。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记集装箱</button>
        <button class="btn" type="button" @click="exportRows">导出集装箱档案清单</button>
      </div>
    </header>

    <div class="stat-row stats-wrap">
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
            <button class="link" type="button" @click="openEdit(row)">修改资料</button>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无集装箱档案数据，可先登记集装箱</td>
        </tr>
      </tbody>
    </table>

    <div v-if="editing" class="modal-mask" @click.self="closeEdit">
      <div class="modal">
        <h3>修改集装箱资料</h3>
        <p class="modal-hint">箱号 {{ editing.箱号 }} 为主数据，保存后堆存、闸口看到的箱型与统计立即跟随。</p>
        <label v-for="field in editFields" :key="field" class="modal-field">
          <span>{{ field }}</span>
          <input v-model="editForm[field]" />
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeEdit">取消</button>
          <button class="btn primary" type="button" :disabled="saving" @click="saveEdit">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条集装箱档案记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Card = { label: string; value: number }

const ENDPOINT = '/api/container'
const columns = ["箱号", "箱型", "箱况等级", "所属船公司", "尺寸规格", "自重", "检验到期日", "箱体状态"]
const actions = ["登记检验", "标记可周转", "报废箱体"]
const filterFields = ["箱号", "箱型", "箱况等级"]
// 箱号是主键不允许改；箱况（箱体状态）由动作流转，不走资料编辑。
const editFields = ["箱型", "箱况等级", "所属船公司", "尺寸规格", "自重", "检验到期日"]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Card[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})

const editing = ref<Row | null>(null)
const editForm = ref<Record<string, string>>({})
const saving = ref(false)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '集装箱登记入口尚未接入审批流'
}

function openEdit(row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  editing.value = row
  const form: Record<string, string> = {}
  for (const field of editFields) {
    form[field] = row[field] == null ? '' : String(row[field])
  }
  editForm.value = form
}

function closeEdit() {
  editing.value = null
}

async function saveEdit() {
  if (!editing.value) return
  saving.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${editing.value.id}`, {
      method: 'PUT',
      body: JSON.stringify(editForm.value),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '资料未保存，请稍后重试')
    }
    closeEdit()
    noticeMessage.value = '资料已保存，箱型统计与关联页面均已更新'
    // 保存即取数，列表与统计同一轮刷新，不需要切换页面再回来。
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '集装箱资料保存失败'
  } finally {
    saving.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '集装箱档案动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '集装箱档案操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    stats.value = payload.cards ?? []
  } catch {
    // 统计取不到不阻塞列表使用，保留上一次的卡片数据。
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('集装箱列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '集装箱档案列表读取失败'
  }
}

onMounted(() => Promise.all([reload(), loadStats()]))
</script>
