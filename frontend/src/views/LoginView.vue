<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { homeFor, useAuth } from '../composables/useAuth'
import { SYSTEM_TITLE } from '../design/copy'
import Icon from '../components/Icon.vue'
import Card from '../components/Card.vue'

const auth = useAuth()
const router = useRouter()
const username = ref(''), password = ref(''), visible = ref(false), busy = ref(false), error = ref('')
const canRetry = computed(() => auth.phase.value === 'error' && !!auth.token.value)
async function enter() {
  const user = auth.user.value
  if (user) await router.replace(homeFor(user.role))
}
async function submit() {
  if (busy.value || !username.value.trim() || !password.value) return
  busy.value = true; error.value = ''
  try { await auth.login(username.value.trim(), password.value); password.value = ''; await enter() }
  catch (e) { error.value = e instanceof ApiError && e.status === 404 ? '当前后端尚未升级，请启动支持账号登录的新版本后端。' : e instanceof Error ? e.message : '登录失败，请重试。' }
  finally { busy.value = false }
}
async function retry() { if (!busy.value) { busy.value = true; await auth.restore(true); busy.value = false; await enter() } }
onUnmounted(() => { password.value = '' })
</script>
<template>
  <main class="login-page">
    <div class="login-brand"><span><Icon name="leaf" /></span>{{ SYSTEM_TITLE }}</div>
    <div class="login-layout">
      <section class="login-intro">
        <p class="eyebrow">棚内温度，清晰可见</p>
        <h1>从外部气象<br>看见棚内温度分布</h1>
        <p class="intro-copy">选择气象所在地，自动匹配棚体档案，查看三维温度场与历史构场结果。</p>
        <svg class="greenhouse-art" viewBox="0 0 600 260" aria-hidden="true" fill="none">
          <path d="M46 213H554 M80 213V140C80 32 260 32 260 140V213 M110 213V139C110 53 290 53 290 139V213 M140 213V139C140 74 320 74 320 139V213 M170 213V140C170 96 350 96 350 140V213 M200 213V140C200 117 380 117 380 140V213 M260 140 474 95 M80 140 294 95 M80 213 294 168 M260 213 474 168 M294 168V95C294-13 474-13 474 95V168" stroke="currentColor" stroke-width="1.5" />
          <path class="art-accent" d="M88 182 144 176 200 158 256 161 312 133 368 136 425 111 480 116" stroke="currentColor" stroke-width="3" />
          <circle cx="200" cy="158" r="5" fill="currentColor" /><circle cx="312" cy="133" r="5" fill="currentColor" /><circle cx="425" cy="111" r="5" fill="currentColor" />
        </svg>
        <div class="login-capabilities"><span><Icon name="cube" />三维温度场</span><span><Icon name="clock" />历史可追溯</span><span><Icon name="users" />按账号授权</span></div>
      </section>
      <Card class="login-card">
        <p class="eyebrow">欢迎使用</p><h2>登录工作台</h2>
        <p class="note">使用管理员分配的账号登录，系统将按权限开放功能。</p>
        <p v-if="error" role="alert" class="form-message error">{{ error }}</p>
        <p v-else-if="auth.notice.value" role="status" class="form-message">{{ auth.notice.value }}</p>
        <button v-if="canRetry" type="button" :disabled="busy" class="retry-session" @click="retry">重试验证已有会话</button>
        <form class="auth-form form-stack" @submit.prevent="submit">
          <label>账号<input v-model="username" name="username" autocomplete="username" required maxlength="64" placeholder="请输入账号" :disabled="busy"></label>
          <label>密码<span class="password-field"><input v-model="password" name="password" :type="visible ? 'text' : 'password'" autocomplete="current-password" required :disabled="busy" placeholder="请输入密码"><button type="button" :aria-pressed="visible" :aria-label="visible ? '隐藏密码' : '显示密码'" @click="visible = !visible">{{ visible ? '隐藏' : '显示' }}</button></span></label>
          <button class="primary login-submit" type="submit" :disabled="busy || !username.trim() || !password">{{ busy ? '正在登录…' : '登录' }}<Icon name="arrowRight" /></button>
        </form>
        <p class="login-help note">没有账号或忘记密码？请联系系统管理员。</p>
      </Card>
    </div>
    <p class="login-footer note">气象构场结果为模型推算，用于辅助了解棚内温度分布。</p>
  </main>
</template>
<style scoped>
.login-page { min-height: 100%; overflow-y: auto; padding: 36px max(24px, calc((100vw - 1180px) / 2)); background: radial-gradient(ellipse at 18% 58%, var(--leaf-soft), transparent 65%), var(--paper); display: flex; flex-direction: column; }
.login-brand { display: flex; align-items: center; gap: 12px; font-size: 20px; font-weight: var(--w-strong); }
.login-brand > span { display: flex; padding: 10px; background: var(--leaf-soft); color: var(--leaf); border-radius: var(--radius); }
.login-layout { display: grid; grid-template-columns: minmax(0, 1fr) 410px; align-items: center; gap: 72px; flex: 1; padding: 48px 0; }
.eyebrow { color: var(--leaf); font-size: var(--size-note); font-weight: var(--w-strong); letter-spacing: .1em; margin-bottom: 16px; }
.login-intro h1 { font-size: clamp(30px, 3.2vw, 44px); line-height: 1.4; letter-spacing: .02em; }
.intro-copy { max-width: 460px; color: var(--ink-muted); line-height: 1.9; margin-top: 20px; }
.greenhouse-art { display: block; width: 100%; max-width: 540px; height: 220px; margin: 18px 0 8px; color: color-mix(in srgb, var(--leaf) 35%, var(--steel)); }
.art-accent { color: var(--leaf); }
.login-capabilities { display: flex; gap: 22px; flex-wrap: wrap; font-size: var(--size-note); color: var(--ink-muted); }
.login-capabilities span { display: flex; align-items: center; gap: 7px; }
.login-capabilities :deep(svg) { width: 18px; }
.login-card { padding: 36px; border: var(--rule); }
.login-card h2 { font-size: 26px; margin-bottom: 10px; }
.login-card > .note { margin-bottom: 24px; }
.login-card .form-message { margin-bottom: 18px; }
.password-field { display: flex; position: relative; }
.password-field input { padding-right: 60px; }
.password-field button { position: absolute; top: 2px; right: 2px; bottom: 2px; border: 0; background: transparent; color: var(--ink-muted); }
.login-submit { display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 6px; min-height: 44px; }
.login-help { margin: 24px 0 0 !important; text-align: center; }
.login-footer { text-align: center; margin: 0; }
.retry-session { margin-bottom: 16px; width: 100%; }
@media (max-width: 900px) { .login-layout { gap: 30px; grid-template-columns: minmax(0, 1fr) 370px; }.login-card { padding: 28px; }.greenhouse-art { height: 180px; } }
@media (max-width: 720px) { .login-page { padding: 24px; }.login-layout { grid-template-columns: minmax(0, 1fr); padding: 36px 0; gap: 24px; }.login-intro h1 { font-size: 28px; }.greenhouse-art,.login-capabilities { display: none; }.login-card { max-width: 480px; width: 100%; justify-self: center; }.login-brand { font-size: 17px; } }
</style>
