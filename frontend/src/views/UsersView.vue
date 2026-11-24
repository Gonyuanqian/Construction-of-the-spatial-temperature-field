<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { accountApi } from '../api/accounts'
import type { Account } from '../api/session'
import { passwordError, useAuth } from '../composables/useAuth'
import Card from '../components/Card.vue'
import Icon from '../components/Icon.vue'

const auth = useAuth()
const items = ref<Account[]>([]), total = ref(0), offset = ref(0), loading = ref(false), saving = ref(false)
const selected = ref<Account | null>(null), error = ref(''), message = ref(''), resetPassword = ref(''), resetConfirm = ref('')
const form = reactive({ username: '', display_name: '', password: '', role: 'USER' as Account['role'], enabled: true })
let sequence = 0
async function load() {
  const seq = ++sequence; loading.value = true; error.value = ''
  try { const data = await accountApi.list(20, offset.value); if (seq === sequence) { items.value = data.items; total.value = data.total } }
  catch (e) { if (seq === sequence) error.value = e instanceof Error ? e.message : '账号列表读取失败。' }
  finally { if (seq === sequence) loading.value = false }
}
function select(account: Account | null) {
  if (saving.value) return
  selected.value = account
  Object.assign(form, { username: account?.username ?? '', display_name: account?.display_name ?? '', role: account?.role ?? 'USER', enabled: account?.enabled ?? true, password: '' })
  resetPassword.value = resetConfirm.value = ''; error.value = ''; message.value = ''
}
async function save() {
  if (saving.value) return
  error.value = ''
  if (!form.display_name.trim()) { error.value = '请填写显示名称。'; return }
  if (!selected.value) {
    error.value = !/^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$/.test(form.username) ? '账号需为 3 至 64 位字母、数字或 _.-。' : passwordError(form.password)
    if (error.value) return
  }
  saving.value = true; message.value = ''
  const existing = selected.value
  try {
    const account = existing ? await accountApi.update(existing.id, { display_name: form.display_name.trim(), role: form.role, enabled: form.enabled })
      : await accountApi.create({ username: form.username, display_name: form.display_name.trim(), password: form.password, role: form.role })
    form.password = ''
    if (existing?.id === auth.user.value?.id) { auth.clear('账号资料已更新，请重新登录。'); return }
    selected.value = account
    Object.assign(form, { username: account.username, display_name: account.display_name, role: account.role, enabled: account.enabled })
    await load()
    message.value = existing ? '账号资料已保存，该账号的已有登录已撤销。' : '账号已创建，用户可选择棚体配置并接入气象。'
  } catch (e) { error.value = e instanceof Error ? e.message : '保存失败，请重试。' }
  finally { saving.value = false }
}
async function reset() {
  if (!selected.value || saving.value) return
  error.value = passwordError(resetPassword.value) || (resetPassword.value !== resetConfirm.value ? '两次输入的密码不一致。' : '')
  if (error.value) return
  saving.value = true; message.value = ''
  try {
    await accountApi.password(selected.value.id, resetPassword.value)
    resetPassword.value = resetConfirm.value = ''
    if (selected.value.id === auth.user.value?.id) auth.clear('密码已重置，请使用新密码重新登录。')
    else message.value = '密码已重置，该账号的已有登录已撤销。'
  } catch (e) { error.value = e instanceof Error ? e.message : '重置失败，请重试。' }
  finally { saving.value = false }
}
function page(delta: number) { offset.value = Math.max(0, offset.value + delta * 20); void load() }
onMounted(() => { void load() })
onUnmounted(() => { sequence++; form.password = ''; resetPassword.value = resetConfirm.value = '' })
</script>
<template>
  <section class="workspace-page">
    <header class="workspace-heading"><div><h2>用户管理</h2><p class="note">分配账号身份，管理启用状态和登录密码。</p></div><div class="workspace-actions"><button type="button" :disabled="loading || saving" @click="load">刷新列表</button><button type="button" class="primary" :disabled="saving" @click="select(null)"><Icon name="users" /> 新建账号</button></div></header>
    <p v-if="error" role="alert" class="form-message error">{{ error }}</p><p v-if="message" role="status" class="form-message">{{ message }}</p>
    <div class="management-grid">
      <Card>
        <div class="panel-title"><h3>账号列表</h3><span class="note">共 {{ total }} 个账号</span></div>
        <p v-if="loading" role="status" class="note">正在读取账号…</p>
        <div v-else-if="!items.length" class="empty-panel">{{ error ? '暂时无法显示账号，请重试。' : '暂无账号，可在右侧创建。' }}</div>
        <div v-else class="management-table"><table><thead><tr><th>账号</th><th>显示名称</th><th>身份</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="account in items" :key="account.id" :class="{ selected: selected?.id === account.id }"><td><button type="button" class="row-name" :disabled="saving" @click="select(account)">{{ account.username }} <span v-if="account.id === auth.user.value?.id" class="note">（我）</span></button></td><td>{{ account.display_name }}</td><td>{{ account.role === 'ADMIN' ? '管理员' : '普通用户' }}</td><td><span class="status-chip" :class="{ muted: !account.enabled }">{{ account.enabled ? '启用' : '已禁用' }}</span></td><td><button type="button" :aria-label="`管理 ${account.username}`" :disabled="saving" @click="select(account)">管理</button></td></tr></tbody></table></div>
        <div class="pagination"><span class="note">第 {{ Math.floor(offset / 20) + 1 }} 页</span><div class="workspace-actions"><button type="button" :disabled="loading || saving || offset === 0" @click="page(-1)">上一页</button><button type="button" :disabled="loading || saving || offset + 20 >= total" @click="page(1)">下一页</button></div></div>
      </Card>
      <div class="stacked-panels">
        <Card>
          <h3 class="panel-title">{{ selected ? '账号资料' : '新建账号' }}</h3>
          <form class="form-stack" @submit.prevent="save">
            <label>账号<input v-model="form.username" autocomplete="off" maxlength="64" required :disabled="saving || !!selected" placeholder="例如 user001"></label>
            <label>显示名称<input v-model="form.display_name" maxlength="80" required :disabled="saving" placeholder="填写使用者姓名或名称"></label>
            <label>身份<select v-model="form.role" :disabled="saving"><option value="USER">普通用户</option><option value="ADMIN">管理员</option></select></label>
            <p class="note">{{ form.role === 'ADMIN' ? '可训练和管理模型、用户与全部棚体。' : '可通过地区匹配使用实时监测工作台。' }}</p>
            <label v-if="!selected">初始密码<input v-model="form.password" type="password" autocomplete="new-password" required :disabled="saving" placeholder="至少 8 个字符"></label>
            <label v-else class="check-label"><input v-model="form.enabled" type="checkbox" :disabled="saving">启用账号</label>
            <p v-if="selected" class="note">保存资料会撤销该账号的已有登录。系统会保留至少一位启用的管理员。</p>
            <button class="primary" type="submit" :disabled="saving">{{ saving ? '正在保存…' : selected ? '保存账号资料' : '创建账号' }}</button>
            <RouterLink to="/admin/greenhouses" class="authorize-link">查看棚体档案库</RouterLink>
          </form>
        </Card>
        <Card v-if="selected"><h3 class="panel-title">重置密码</h3><form class="form-stack" @submit.prevent="reset"><label>新密码<input v-model="resetPassword" type="password" autocomplete="new-password" required :disabled="saving"></label><label>确认新密码<input v-model="resetConfirm" type="password" autocomplete="new-password" required :disabled="saving"></label><p class="note">重置后，已有会话将失效，用户需使用新密码登录。</p><button type="submit" :disabled="saving || !resetPassword || !resetConfirm">重置并撤销登录</button></form></Card>
      </div>
    </div>
  </section>
</template>
<style scoped>
.authorize-link { color: var(--leaf); text-align: center; font-size: var(--size-note); }.workspace-actions :deep(svg) { width: 17px; vertical-align: middle; }
</style>
