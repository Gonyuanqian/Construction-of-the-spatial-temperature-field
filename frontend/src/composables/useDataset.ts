/**
 * 「现在有没有在用数据集」——**全前端唯一一处**判断（规格书 §六、硬约束 3）。
 *
 * 为什么是模块级单例而不是每页各调一次：五个页面各判一遍就是五处判断，
 * 而它们一定会分家 —— 分家之后出现的是一种最难查的界面：
 * **四个页面说没数据、一个页面说有。**
 *
 * 为什么探测 `GET /api/dataset` 而不是新开一个 `/api/dataset/status`：
 * 那个接口本来就在，而且它答的正是这个问题（409 = 还没导入）。
 * 多一个接口就多一处必须跟着改的口径。
 */
import { ref, type Ref } from 'vue'

import { ApiError, getJson } from '../api/client'
import type { DatasetPayload } from '../api/types'

export type DatasetState = 'probing' | 'ok' | 'missing' | 'error'

const state = ref<DatasetState>('probing')
const version = ref(0)

async function probe(): Promise<void> {
  try {
    await getJson<DatasetPayload>('/api/dataset')
    state.value = 'ok'
  } catch (e) {
    // ⚠️ **只有 409 是空态。** 其它一切（500、连不上）都是「出错了」——
    // 把后者说成「你还没开始」，会让用户去导一份数据集来解决一个
    // 后端没起来的问题。这两种错必须分得开（规格书 §二.1）。
    state.value = e instanceof ApiError && e.status === 409 ? 'missing' : 'error'
  }
}

/**
 * 服务端的数据集换了（导入成功）：让当前挂着的那一页**当场重挂、当场重取**。
 *
 * `version` 绑在 `App.vue` 的 `<RouterView :key>` 上。Vue 的 key 变了就是
 * unmount + mount，没有中间态 —— 页面上任何一处 datum 都随组件一起被丢掉，
 * 所以**没有任何一个页面能留在旧数据上**。这是 §3.2 里那条完备性的全部内容。
 *
 * *为什么不是 `location.reload()`*：能过，但把「失效」实现成「重启」会顺手
 * 清掉别的状态（页② 上用户选的特征组），而那与换数据集无关。
 *
 * 状态直接置 `ok` 而不重新探测：导入刚刚成功，那个事实是确定的。
 */
function onImported(): void {
  state.value = 'ok'
  version.value += 1
}

/** 只给测试用：把单例打回起点。生产代码不许调它。 */
function reset(): void {
  state.value = 'probing'
  version.value = 0
}

export interface DatasetStatus {
  state: Ref<DatasetState>
  version: Ref<number>
  probe: () => Promise<void>
  onImported: () => void
  reset: () => void
}

export function useDataset(): DatasetStatus {
  return { state, version, probe, onImported, reset }
}
