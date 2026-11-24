import { ref, watch } from 'vue'
import { session } from '../api/session'
import { validStoredLocation, type MonitoringLocation } from '../live/monitoringLocation'

export function useMonitoringLocation() {
  const selected = ref<MonitoringLocation | null>(null)
  const storageKey = () => session.user.value ? `tfield.monitoring-location.v1.${session.user.value.id}` : null
  watch(() => session.user.value?.id, () => {
    selected.value = null
    try {
      const key = storageKey(), saved = key ? JSON.parse(localStorage.getItem(key) ?? 'null') : null
      if (validStoredLocation(saved)) selected.value = saved
    } catch { /* A missing or blocked preference never prevents opening the picker. */ }
  }, { immediate: true })
  function save(location: MonitoringLocation) {
    if (!validStoredLocation(location)) return
    selected.value = { ...location }
    try { const key = storageKey(); if (key) localStorage.setItem(key, JSON.stringify(location)) } catch { /* Keep the current selection in memory. */ }
  }
  return { selected, save }
}
