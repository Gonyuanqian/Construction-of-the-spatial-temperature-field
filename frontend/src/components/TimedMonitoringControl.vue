<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, useId } from 'vue'
import { MONITORING_INTERVALS } from '../composables/useTimedMonitoring'
import Icon from './Icon.vue'

const props = defineProps<{
  enabled: boolean; intervalMinutes: number; nextAt: number | null
  busy?: boolean; paused?: boolean; error?: string; available: boolean
}>()
const emit = defineEmits<{ start: []; stop: []; interval: [minutes: number] }>()
const open = ref(false), root = ref<HTMLElement>(), trigger = ref<HTMLButtonElement>(), select = ref<HTMLSelectElement>()
const id = useId()
const nextTime = computed(() => props.nextAt === null ? '' : new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
}).format(new Date(props.nextAt)))
async function toggle() { open.value = !open.value; if (open.value) { await nextTick(); select.value?.focus() } }
function outside(event: PointerEvent) { if (!root.value?.contains(event.target as Node)) open.value = false }
function escape(event: KeyboardEvent) { if (event.key === 'Escape' && open.value) { event.stopPropagation(); open.value = false; trigger.value?.focus() } }
async function changeMonitoring() {
  if (props.enabled) emit('stop'); else emit('start')
  await nextTick(); root.value?.querySelector<HTMLButtonElement>('.timed-action')?.focus()
}
onMounted(() => { document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape) })
onUnmounted(() => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) })
</script>

<template>
  <div ref="root" class="timed-control" @keydown="escape">
    <button ref="trigger" type="button" class="timed-trigger" :class="{enabled}" aria-label="定时监测" :aria-expanded="open" :aria-controls="id" aria-haspopup="dialog" @click="toggle">
      <Icon name="clock" /><span>{{ enabled ? '监测中' : '定时监测' }}</span><i v-if="enabled" aria-hidden="true" />
    </button>
    <div v-if="open" :id="id" class="timed-panel" role="dialog" aria-label="定时监测设置">
      <div class="timed-heading"><strong>定时监测</strong><button type="button" aria-label="关闭定时监测设置" @click="open=false">×</button></div>
      <p class="timed-note">按设定间隔获取气象，自动更新温度场。</p>
      <label :for="`${id}-interval`">更新间隔</label>
      <select :id="`${id}-interval`" ref="select" :value="intervalMinutes" @change="emit('interval', Number(($event.target as HTMLSelectElement).value))">
        <option v-for="minutes in MONITORING_INTERVALS" :key="minutes" :value="minutes">每 {{ minutes }} 分钟</option>
      </select>
      <p class="timed-status" role="status">{{ !enabled ? '尚未开启' : paused ? '页面不可见，已暂缓更新' : busy ? '正在更新，完成后继续计时' : `下次更新 ${nextTime}` }}</p>
      <p v-if="error" class="timed-error" role="alert">本次更新失败：{{ error }}。将在下次定时重试。</p>
      <p v-if="!available" class="timed-note">请先选择监测地点。</p>
      <button v-if="enabled" type="button" class="timed-action" @click="changeMonitoring">暂停监测</button>
      <button v-else type="button" class="timed-action" :disabled="!available" @click="changeMonitoring">开启监测</button>
      <p class="timed-note timed-help">开启后立即更新一次。离页或切换标签页时暂缓，返回后继续；刷新页面后需重新开启。短间隔可能复用已获取的气象数据。</p>
    </div>
  </div>
</template>

<style scoped>
.timed-control{position:relative;flex:none;}
.timed-trigger{display:flex;align-items:center;gap:5px;min-height:32px;padding:6px 8px;white-space:nowrap;border:1px solid var(--interact);border-radius:var(--radius);background:var(--card);color:var(--ink-muted);font:inherit;font-size:12px;cursor:pointer;}
.timed-trigger :deep(.icon){--icon-size:15px;}.timed-trigger.enabled{border-color:var(--edge);color:var(--edge);background:color-mix(in srgb,var(--edge) 8%,var(--card));}.timed-trigger i{width:5px;height:5px;border-radius:50%;background:var(--ok);}
.timed-panel{position:absolute;top:calc(100% + 10px);left:0;z-index:70;width:280px;max-width:calc(100vw - 40px);padding:16px;border:1px solid var(--interact);border-radius:var(--radius);background:var(--card);box-shadow:var(--shadow);color:var(--ink);font-size:13px;}
.timed-heading{display:flex;align-items:center;justify-content:space-between;font-size:15px;}.timed-heading button{border:0;background:transparent;color:var(--ink-muted);font-size:22px;cursor:pointer;padding:0 4px;}
.timed-panel label{display:block;margin:12px 0 6px;}.timed-panel select{width:100%;padding:8px;border:1px solid var(--interact);border-radius:var(--radius);background:var(--card);color:var(--ink);font:inherit;}
.timed-status{color:var(--edge);margin:12px 0;}.timed-note{margin:8px 0;color:var(--ink-muted);font-size:12px;line-height:1.6;white-space:normal;}.timed-help{margin-bottom:0;}.timed-error{color:var(--bar);line-height:1.5;overflow-wrap:anywhere;}
.timed-action{width:100%;padding:8px;border:1px solid var(--edge);border-radius:var(--radius);background:color-mix(in srgb,var(--edge) 10%,var(--card));color:var(--edge);font:inherit;cursor:pointer;}.timed-action:disabled{opacity:.5;cursor:default;}
button:focus-visible,select:focus-visible{outline:2px solid var(--edge);outline-offset:3px;}
@media(max-width:640px){.timed-panel{left:auto;right:0;}}
</style>
