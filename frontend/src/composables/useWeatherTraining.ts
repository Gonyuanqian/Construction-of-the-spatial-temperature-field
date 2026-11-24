import { computed, effectScope, inject, onScopeDispose, provide, reactive, ref, watch, type EffectScope, type InjectionKey } from 'vue'
import { ApiError } from '../api/client'
import { gTrainingApi, type GInfo, type GJob } from '../api/weatherTraining'
import { useDataset } from './useDataset'

function createWorkspace() {
  const info = ref<GInfo | null>(null), job = ref<GJob | null>(null)
  const loading = ref(false), submitting = ref(false), error = ref('')
  const target = ref<'independent' | 'f' | 'g'>('independent')
  const form = reactive({ name: '气象映射模型 G', external_schema: 'full' as 'two' | 'full', algorithm: 'extra_trees' as 'extra_trees' | 'ridge', validation_fraction: .2, n_estimators: 120, max_depth: 12, min_samples_leaf: 2, alpha: 10, seed: 42 })
  const busy = computed(() => submitting.value || job.value?.state === 'running')
  let disposed = false, seq = 0, timer: ReturnType<typeof setTimeout> | undefined
  let pending: {body: string; key: string} | null = null
  const publicationKeys = new Map<string, string>()
  function publicationKey(jobId: string, name: string, fieldId: number) {
    const scope = JSON.stringify([jobId, name, fieldId])
    if (!publicationKeys.has(scope)) publicationKeys.set(scope, crypto.randomUUID())
    return publicationKeys.get(scope)!
  }
  function accept(latest: GJob) {
    job.value = latest
    if (info.value?.dataset_id === latest.dataset_id) info.value.jobs = [latest, ...info.value.jobs.filter(item => item.id !== latest.id)].slice(0, 20)
  }
  function stop() { if (timer) clearTimeout(timer); timer = undefined }
  function poll() {
    stop()
    if (disposed || job.value?.state !== 'running') return
    timer = setTimeout(async () => {
      const id = job.value?.id
      if (!id || disposed) return
      try {
        const latest = await gTrainingApi.get(id)
        if (disposed || job.value?.id !== id) return
        accept(latest); error.value = ''
      } catch(e) { if (!disposed) error.value = e instanceof Error ? e.message : 'G 任务状态读取失败' }
      finally { if (!disposed) poll() }
    }, 1500)
  }
  async function load() {
    const mine = ++seq
    loading.value = true; error.value = ''
    try {
      const result = await gTrainingApi.info()
      if (disposed || mine !== seq) return
      info.value = result
      if (!job.value || job.value.state !== 'running') {
        const selected = result.jobs.find(item => item.id === job.value?.id)
        const matching=result.jobs.find(item=>(item.options.spatial_protocol==='independent_house_section_v2')===(target.value==='independent'))
        job.value = result.active_job ?? selected ?? matching ?? result.jobs[0] ?? null
      }
      poll()
    } catch(e) { if (!disposed && mine === seq) error.value = e instanceof Error ? e.message : 'G 训练信息读取失败' }
    finally { if (!disposed && mine === seq) loading.value = false }
  }
  async function submit(spatial_protocol: 'legacy_multi_house_v1' | 'independent_house_section_v2') {
    if (disposed || busy.value || loading.value || !info.value?.dataset.ready) return
    const config={...form,spatial_protocol}
    const body = JSON.stringify(config)
    if (pending?.body !== body) pending = {body, key: crypto.randomUUID()}
    submitting.value = true; error.value = ''; ++seq
    try {
      const result = await gTrainingApi.start(config, pending.key)
      if (disposed) return
      pending = null; accept(result); poll()
    } catch(e) {
      if (!disposed) error.value = e instanceof Error ? e.message : 'G 训练提交失败'
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) pending = null
    } finally { if (!disposed) submitting.value = false }
  }
  const start=()=>submit('legacy_multi_house_v1')
  const startCorrected=()=>submit('independent_house_section_v2')
  async function cancel() {
    const id = job.value?.id
    if (!id || job.value?.state !== 'running' || job.value.cancel_requested) return
    try { const latest = await gTrainingApi.cancel(id); if (!disposed && job.value?.id === id) {job.value = latest; poll()} }
    catch(e) { if (!disposed) error.value = e instanceof Error ? e.message : '取消失败' }
  }
  async function view(id: string) {
    if (busy.value) return
    try { const latest = await gTrainingApi.get(id); if (!disposed) {job.value = latest; poll()} }
    catch(e) { if (!disposed) error.value = e instanceof Error ? e.message : '读取失败' }
  }
  onScopeDispose(() => { disposed = true; ++seq; stop() })
  return { info, job, loading, submitting, error, form, busy, target, load, start, startCorrected, cancel, view, publicationKey }
}
type Workspace = ReturnType<typeof createWorkspace>
const key: InjectionKey<() => Workspace> = Symbol('weather-training')
export function provideWeatherTraining() {
  let scope: EffectScope | null = null, workspace: Workspace | null = null
  function clear() { scope?.stop(); scope = null; workspace = null }
  provide(key, () => {
    if (!workspace) { scope = effectScope(true); workspace = scope.run(createWorkspace)! }
    return workspace
  })
  watch(useDataset().version, clear, {flush: 'sync'})
  onScopeDispose(clear)
}
export function useWeatherTraining() { return inject(key, null)?.() ?? createWorkspace() }
