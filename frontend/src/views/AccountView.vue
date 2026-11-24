<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { postJson } from '../api/client'
import { useAuth, passwordError } from '../composables/useAuth'
import Card from '../components/Card.vue'
const auth = useAuth(), router = useRouter()
const previous = ref(''), next = ref(''), confirm = ref(''), busy = ref(false), error = ref('')
async function submit() {
  if (busy.value) return
  error.value = passwordError(next.value) || (next.value !== confirm.value ? '两次输入的新密码不一致。' : '')
  if (error.value) return
  busy.value = true
  try {
    await postJson('/api/auth/password', { current_password: previous.value, new_password: next.value })
    previous.value = next.value = confirm.value = ''
    auth.clear('密码已修改，请使用新密码重新登录。')
    await router.replace('/login')
  } catch (e) { error.value = e instanceof Error ? e.message : '修改失败，请重试。' }
  finally { busy.value = false }
}
onUnmounted(() => { previous.value = next.value = confirm.value = '' })
</script>
<template>
  <section class="workspace-page account-page">
    <header class="workspace-heading"><div><h2>账号与密码</h2><p class="note">管理当前账号的登录密码。</p></div></header>
    <Card class="account-profile"><h3>{{ auth.user.value?.display_name }}</h3><p class="note">账号：{{ auth.user.value?.username }}　身份：{{ auth.isAdmin.value ? '管理员' : '普通用户' }}</p></Card>
    <Card><h3 class="panel-title">修改密码</h3><p v-if="error" role="alert" class="form-message error">{{ error }}</p>
      <form class="form-stack" @submit.prevent="submit"><label>当前密码<input v-model="previous" type="password" autocomplete="current-password" required :disabled="busy"></label><label>新密码<input v-model="next" type="password" autocomplete="new-password" required :disabled="busy"></label><label>确认新密码<input v-model="confirm" type="password" autocomplete="new-password" required :disabled="busy"></label><p class="note">密码至少 8 个字符。修改后，已有登录会话将失效。</p><button class="primary" type="submit" :disabled="busy || !previous || !next || !confirm">{{ busy ? '正在保存…' : '修改密码并重新登录' }}</button></form>
    </Card>
  </section>
</template>
<style scoped>
.account-page { max-width: 640px; }.account-profile h3 { margin-bottom: 8px; }.form-message { margin-bottom: 16px; }
</style>
