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
      // `/` 与认不出的路径都落回页①：演示时最怕的是白屏，
      // 一个回到起点的跳转至少还看得见东西。
      { path: '/', redirect: '/data' },
      { path: '/:rest(.*)*', redirect: '/data' },
    ],
  })
}

export default createAppRouter()
