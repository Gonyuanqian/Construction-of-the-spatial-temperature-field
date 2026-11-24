<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
defineProps<{ label: string; drawer?: boolean; busy?: boolean; location?: boolean; wide?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const previousFocus = document.activeElement as HTMLElement | null
onMounted(() => {
  if (dialog.value?.showModal) dialog.value.showModal()
  else dialog.value?.setAttribute('open', '')
})
onUnmounted(() => { previousFocus?.isConnected && previousFocus.focus() })
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="management-dialog" :class="{ drawer, location, wide }" :aria-label="label" :aria-busy="busy"
      @cancel.prevent="!busy && emit('close')" @click="($event.target === $event.currentTarget) && !busy && emit('close')">
      <div class="dialog-content"><slot /></div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.management-dialog { --leaf: var(--management-primary); --leaf-soft: var(--management-tint); --interact: var(--management-primary); width: min(480px, calc(100vw - 32px)); max-height: calc(100dvh - 48px); margin: auto; padding: 0; border: var(--rule); border-radius: 8px; color: var(--ink); background: var(--card); font: inherit; }
.management-dialog::backdrop { background: var(--management-backdrop); }
.dialog-content { padding: 24px; }
.management-dialog.drawer { position: fixed; inset: 0 0 0 auto; margin: 0; width: min(760px, 94vw); max-height: none; height: 100dvh; border-radius: 0; border-right: 0; }
.drawer .dialog-content { padding: 24px 28px; }
.management-dialog.location { --interact: var(--nav-blue); width: min(1000px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); border: 1px solid var(--interact); overflow: auto; }
.location .dialog-content { padding: 0; }
.management-dialog.wide { width: min(1280px, calc(100vw - 32px)); }
</style>
