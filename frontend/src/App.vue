<template>
  <n-config-provider :theme="appStore.darkMode ? darkTheme : null">
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <ErrorHandlerBridge />
          <router-view />
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { defineComponent, onMounted } from 'vue'
import { darkTheme, useMessage } from 'naive-ui'
import { useAuthStore } from './stores/auth'
import { useAppStore } from './stores/app'
import { setGlobalErrorHandler } from './api'

const authStore = useAuthStore()
const appStore = useAppStore()

/**
 * 把 axios 的全局错误接到 naive-ui 的 message 上。
 * 必须活在 n-message-provider 内部才能调用 useMessage，所以用无渲染子组件桥接。
 * （此前 setGlobalErrorHandler 从未被调用——接口错误只进控制台，用户看不到。）
 */
const ErrorHandlerBridge = defineComponent({
  name: 'ErrorHandlerBridge',
  setup() {
    const message = useMessage()
    onMounted(() => {
      setGlobalErrorHandler((text, type) => {
        message[type](text, { duration: 3600, closable: true })
      })
    })
    return () => null
  },
})

onMounted(() => {
  appStore.init()
  authStore.initFromStorage()
})
</script>
