<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import Icon from './Icon.vue'

const auth = useAuth()
const router = useRouter()
const busy = ref(false)
const menu = ref<HTMLDetailsElement | null>(null)
async function logout() {
  if (busy.value) return
  busy.value = true
  try { await auth.logout() } catch { /* Local session was cleared even when the server was unavailable. */ }
  finally { busy.value = false; await router.replace('/login') }
}
</script>
<template>
  <details v-if="auth.user.value" ref="menu" class="account-menu">
    <summary aria-label="账号菜单"><Icon name="users" /><span>{{ auth.user.value.display_name }}</span><small>{{ auth.isAdmin.value ? '管理员' : '用户' }}</small></summary>
    <div class="account-popover">
      <p class="note">{{ auth.user.value.username }}</p>
      <RouterLink to="/account" @click="menu?.removeAttribute('open')">账号与密码</RouterLink>
      <button type="button" :disabled="busy" @click="logout">{{ busy ? '正在退出…' : '退出登录' }}</button>
    </div>
  </details>
</template>
<style scoped>
.account-menu { position: relative; color: var(--ink); font-size: var(--size-note); }
summary { display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 6px 8px; border: var(--rule); border-radius: var(--radius); background: var(--card); }
summary::marker { content: ''; }
summary span { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
summary small { color: var(--ink-muted); white-space: nowrap; }
.account-popover { position: absolute; top: calc(100% + 8px); right: 0; z-index: 100; min-width: 180px; padding: 14px; background: var(--card); border: var(--rule); border-radius: var(--radius); box-shadow: var(--shadow); display: grid; gap: 10px; }
.account-popover p { overflow-wrap: anywhere; }
.account-popover a { color: var(--ink); text-decoration: none; padding: 4px 0; }
</style>
