import type { Component } from 'vue'
import {
  createRouter, createWebHistory, type Router, type RouterHistory,
} from 'vue-router'

import { NAV_ITEMS } from '../design/copy'
import DataView from '../views/DataView.vue'
import FieldView from '../views/FieldView.vue'
import TrainView from '../views/TrainView.vue'

/**
 * 视图表。**静态 import，不用动态 `import()`。**
 *
 * 想用 `() => import(`../views/${name}.vue`)` 的话：Vite 要求 import 的路径
 * **静态可分析**，模板字符串要么让打包器把整个 `views/` 塞进产物，
 * 要么加 `@vite-ignore` —— 而那会让它在运行时去取一个没被编译过的 `.vue`，
 * 构建能过、页面白屏。两页而已，直接引进来最省事。
 */
const VIEWS: Record<string, Component> = {
  data: DataView, train: TrainView, field: FieldView,
}

/**
 * 只注册导航里 enabled 的那些页。
 *
 * 未开放的页**不注册路由** —— 一个跳过去只有一句「本轮不做」的页面，
 * 比导航上一个禁用的按钮更难看（spec 2026-10-04 §二.4）。
 * 有一条测试拿 `NAV_ITEMS[i].enabled` 与路由表对账，所以这两处不会各说各话。
 */
export function createAppRouter(history?: RouterHistory): Router {
  const routes = NAV_ITEMS.filter((i) => i.enabled && i.key in VIEWS).map((i) => ({
    path: i.to,
    name: i.key,
    component: VIEWS[i.key],
  }))

  return createRouter({
    history: history ?? createWebHistory(),
    routes: [
      ...routes,
      // 实时模式**不进 `NAV_ITEMS`**：进了就会出现在左导航里，而这一屏要收起导航。
      // 它也不像上面那几页那样从 `NAV_ITEMS` 生成 —— 所以必须显式写一条，
      // 否则会被下面的兜底 `/:rest(.*)*` 吃掉，`/live` 直接落回页①。
      {
        path: '/live',
        name: 'live',
        // 懒加载：实时模式那一屏（含三维）不该进首屏。
        component: () => import('../views/LiveView.vue'),
        // 收起左侧导航（`App.vue` 按这个 meta 决定）。
        meta: { rail: false },
      },
      // `/` 与认不出的路径都落回页①：演示时最怕的是白屏，
      // 一个回到起点的跳转至少还看得见东西。
      { path: '/', redirect: '/data' },
      { path: '/:rest(.*)*', redirect: '/data' },
    ],
  })
}

export default createAppRouter()
