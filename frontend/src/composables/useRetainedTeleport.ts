import { onActivated, onDeactivated, onMounted, ref, shallowRef } from 'vue'

/** 缓存页离开时把侧栏收回，返回时连接当前外壳的落点，保留组件及其状态。 */
export function useRetainedTeleport(selector: string) {
  const target = shallowRef<string | HTMLElement>(selector)
  // 首次同步渲染时外壳可能尚未接入 document，先就地渲染，挂载后再移入右栏。
  const disabled = ref(true)

  function connect() {
    const element = document.querySelector<HTMLElement>(selector)
    target.value = element ?? selector
    disabled.value = !element
  }

  onMounted(connect)
  onDeactivated(() => { disabled.value = true })
  onActivated(connect)

  return { target, disabled }
}
