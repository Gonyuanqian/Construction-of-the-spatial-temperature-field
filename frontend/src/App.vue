<script setup lang="ts">
import { watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthenticatedShell from './components/AuthenticatedShell.vue'
import { useAuth } from './composables/useAuth'
import { useDataset } from './composables/useDataset'
import { allowed } from './router/access'
import { homeFor } from './composables/useAuth'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
watch(() => auth.user.value?.role, role => {
  if (role && !route.meta.public && !allowed(route, role)) void router.replace(homeFor(role))
})
watch(auth.revision, () => {
  useDataset().reset()
  if (!auth.user.value && !route.meta.public) void router.replace({ path: '/login', query: { redirect: route.fullPath } })
}, { flush: 'sync' })
watchEffect(() => {
  if (route.meta.public || !auth.user.value) document.documentElement.classList.remove('theme-live')
})
</script>

<template>
  <RouterView v-if="route.meta.public" />
  <AuthenticatedShell v-else-if="auth.user.value && allowed(route, auth.user.value.role)" :key="`${auth.user.value.id}:${auth.revision.value}`" />
  <main v-else class="session-loading" role="status">正在验证登录状态…</main>
</template>

<style scoped>
.session-loading { margin: auto; padding: var(--gap-l); color: var(--ink-muted); }
</style>
