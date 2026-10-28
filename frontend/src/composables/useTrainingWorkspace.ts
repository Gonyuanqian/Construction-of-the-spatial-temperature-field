import {
  computed, effectScope, inject, onScopeDispose, provide, ref, watch,
  type EffectScope, type InjectionKey,
} from 'vue'

import { getJson, postJson } from '../api/client'
import { saveModel } from '../api/models'
import type { CalibrationPayload, DiagnosticsPayload, FeaturesPayload, ParamValue } from '../api/types'
import { useAsync } from './useAsync'
import { useDataset } from './useDataset'
import { useJob } from './useJob'

/** 页面只消费状态；请求、轮询与结果由应用作用域持有，不随路由卸载。 */
function createTrainingWorkspace() {
  const features = useAsync(() => getJson<FeaturesPayload>('/api/features'))
  const cal = useAsync(() => getJson<CalibrationPayload>('/api/calibration'))
  const panelValues = ref<Record<string, ParamValue>>({})
  const diag = useAsync(() => postJson<DiagnosticsPayload>(
    '/api/calibration/diagnostics', { params: { ...panelValues.value } }))
  const job = useJob()
  const modelName = ref('')
  const saving = ref(false)
  const saveError = ref('')
  const optimizing = computed(() => job.submitting.value || job.polling.value
    || job.job.value?.state === 'running')
  let disposed = false
  let panelIdentity = ''

  onScopeDispose(() => {
    disposed = true
    job.stop()
  })

  watch(cal.data, payload => {
    if (!payload) return
    const rows = [...payload.panel.trend, ...payload.panel.idw]
    // 同一份包的普通重读、保存后的来源变化，都不覆盖手调值。
    // 换包、换特征或后端默认参数变化时，才重新播种。
    const identity = JSON.stringify([
      payload.present, payload.created_at, payload.dataset_sig, payload.groups_sig,
      payload.tool_version, payload.feature_groups, payload.trend_kind,
      rows.map(row => [row.key, row.current]),
    ])
    if (identity !== panelIdentity) {
      panelIdentity = identity
      panelValues.value = Object.fromEntries(rows.map(row => [row.key, row.current]))
    }
    if (payload.source === 'unsaved' && !modelName.value) {
      const date = new Date()
      const pad = (n: number) => String(n).padStart(2, '0')
      modelName.value = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} 那一份`
    }
  }, { flush: 'sync' })

  watch(job.job, now => {
    // 即使此刻不在训练页，完成时仍读取新包，更新参数与验证结果。
    if (now?.state === 'done' && (cal.data.value?.job?.id !== now.id
        || cal.data.value?.job?.state !== 'done')) void cal.run()
  })

  async function refresh(): Promise<void> {
    if (disposed) return
    void features.run()
    const previousJob = job.job.value
    await cal.run()
    // 路由往返期间可能已提交新任务，旧的 GET 响应不能覆盖其进度。
    // 数据集切换销毁工作区后，在飞的请求也不能重新启动轮询。
    if (disposed || cal.error.value || job.submitting.value || job.polling.value
        || job.job.value !== previousJob) return
    const latest = cal.data.value?.job ?? null
    if (latest) job.attachFrom(latest)
    else job.job.value = null
  }

  function pick(key: string, value: ParamValue): void {
    panelValues.value = { ...panelValues.value, [key]: value }
  }

  async function optimize(): Promise<void> {
    if (disposed || !cal.data.value || cal.loading.value || optimizing.value
        || diag.loading.value || saving.value) return
    await job.start()
  }

  async function train(): Promise<void> {
    if (disposed || !cal.data.value?.present || cal.loading.value || optimizing.value
        || diag.loading.value || saving.value) return
    await diag.run()
  }

  async function save(): Promise<void> {
    if (disposed || cal.data.value?.source !== 'unsaved' || !modelName.value.trim()
        || cal.loading.value || optimizing.value || diag.loading.value || saving.value) return
    saving.value = true
    saveError.value = ''
    try {
      await saveModel(modelName.value.trim())
      if (!disposed) await cal.run()
    } catch (e) {
      if (!disposed) saveError.value = e instanceof Error ? e.message : String(e)
    } finally {
      saving.value = false
    }
  }

  return {
    features, cal, diag, job, panelValues, modelName, saving, saveError, optimizing,
    refresh, pick, optimize, train, save,
  }
}

type TrainingWorkspace = ReturnType<typeof createTrainingWorkspace>
const workspaceKey: InjectionKey<() => TrainingWorkspace> = Symbol('training-workspace')

/** 每个应用一份，按需创建；导入新数据集时整体丢弃，避免串用旧参数和结果。 */
export function provideTrainingWorkspace(): void {
  let scope: EffectScope | null = null
  let workspace: TrainingWorkspace | null = null
  const clear = () => {
    scope?.stop()
    scope = null
    workspace = null
  }
  provide(workspaceKey, () => {
    if (!workspace) {
      scope = effectScope(true)
      workspace = scope.run(createTrainingWorkspace)!
    }
    return workspace
  })
  watch(useDataset().version, clear, { flush: 'sync' })
  onScopeDispose(clear)
}

export function useTrainingWorkspace(): TrainingWorkspace {
  // 独立挂载页面时使用本地作用域；正常应用由 App 提供跨路由工作区。
  return inject(workspaceKey, null)?.() ?? createTrainingWorkspace()
}
