import { createApp } from 'vue'

import App from './App.vue'
import { SYSTEM_TITLE } from './design/copy'
import router from './router'

import './design/tokens.css'
import './design/base.css'

// 运行时把标题写进 document.title，来源就是 copy.ts 那一个常量。
// index.html 里的 <title> 是同一句话的静态副本（它 import 不了 TS），
// 有一条测试盯着两者一致。
document.title = SYSTEM_TITLE

createApp(App).use(router).mount('#app')
