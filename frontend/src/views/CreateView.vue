<template>
  <main class="create-page">
    <div class="wrap">
      <!-- 面包屑 -->
      <div class="cr">
        <RouterLink class="cr-back" to="/" aria-label="返回首页">
          <n-icon :component="ArrowBackOutline" />
        </RouterLink>
        <nav aria-label="面包屑">
          <RouterLink to="/">首页</RouterLink>
          <span aria-hidden="true">/</span>
          <span aria-current="page">AI 创作台</span>
        </nav>
      </div>

      <!-- 页头 -->
      <header class="create-head">
        <div class="create-head-copy">
          <p class="eyebrow">AI STUDIO · 站内生成</p>
          <h1 class="create-title">AI 创作台</h1>
          <p class="create-lead">
            写下一句你想要的画面，AI 会为你生成一张草稿图。满意的话，可以把它发布为「AI 生成」作品。
          </p>
        </div>
        <dl class="create-meta">
          <div>
            <dt>生成模型</dt>
            <dd>{{ config?.model || 'qwen-image-3.0-pro' }}</dd>
          </div>
          <div>
            <dt>今日额度</dt>
            <dd class="quota" :class="{ 'is-used': quotaLeft <= 0 }">
              {{ dailyUsed }} / {{ dailyLimit }}
            </dd>
          </div>
        </dl>
      </header>

      <n-alert v-if="config && !config.enabled" type="warning" class="create-disabled" :bordered="false">
        AI 创作台暂未开启，稍后再来看看。
      </n-alert>
      <n-alert v-else-if="configError" type="error" class="create-disabled" :bordered="false">
        {{ configError }}
        <n-button text type="primary" class="inline-retry" @click="loadConfig">重新加载</n-button>
      </n-alert>

      <!-- 主区 -->
      <div class="create-grid">
        <!-- 左：创作表单 -->
        <section class="form-card" aria-labelledby="prompt-label">
          <div class="form-card-head">
            <h2 id="prompt-label" class="form-title">描述你的画面</h2>
            <span class="form-hint">{{ prompt.length }} / {{ promptMax }}</span>
          </div>
          <n-input
            v-model:value="prompt"
            type="textarea"
            class="prompt-input"
            :autosize="{ minRows: 5, maxRows: 8 }"
            :maxlength="promptMax"
            show-count
            :disabled="!canGenerate"
            placeholder="例如：黄昏校园里的樱花与红砖教学楼，柔和的粉紫色天空，胶片质感，细节丰富"
            @keydown.ctrl.enter.prevent="startGenerate"
            @keydown.meta.enter.prevent="startGenerate"
          />

          <div class="examples" aria-label="示例主题">
            <button
              v-for="example in EXAMPLES"
              :key="example"
              type="button"
              class="example-chip"
              :disabled="!canGenerate"
              @click="useExample(example)"
            >
              {{ example }}
            </button>
          </div>

          <div class="size-field">
            <span class="size-label">画面尺寸</span>
            <div class="size-options" role="radiogroup" aria-label="画面尺寸">
              <button
                v-for="size in sizes"
                :key="size.key"
                type="button"
                role="radio"
                class="size-card"
                :class="{ 'is-active': selectedSize === size.key }"
                :aria-checked="selectedSize === size.key"
                :disabled="!canGenerate"
                @click="selectedSize = size.key"
              >
                <span class="size-shape" :class="`shape-${size.key}`" aria-hidden="true"></span>
                <span class="size-copy">
                  <b>{{ size.label }}</b>
                  <small>{{ size.ratio }} · {{ size.width }}×{{ size.height }}</small>
                </span>
              </button>
            </div>
          </div>

          <div class="form-actions">
            <n-button
              type="primary"
              size="large"
              class="generate-btn"
              :loading="submitting"
              :disabled="!canGenerate || !prompt.trim() || quotaLeft <= 0"
              @click="startGenerate"
            >
              <template #icon>
                <n-icon :component="SparklesOutline" />
              </template>
              {{ generating ? '生成中…' : '开始生成' }}
            </n-button>
            <p class="quota-note">
              <template v-if="quotaLeft > 0">今日还可生成 {{ quotaLeft }} 张 · 每张约 {{ estSeconds }} 秒</template>
              <template v-else>今天的生成次数已用完，明天再来试试</template>
            </p>
          </div>
        </section>

        <!-- 右：结果舞台 -->
        <section class="stage-card" aria-live="polite" aria-busy="generating">
          <!-- 空态 -->
          <div v-if="stage === 'idle'" class="stage-empty">
            <span class="stage-empty-icon" aria-hidden="true">
              <n-icon :component="ImageOutline" size="40" />
            </span>
            <h2>你的下一张作品</h2>
            <p>在左侧写下画面描述并开始生成。生成通常需要 50–60 秒，请保持页面打开。</p>
            <ul class="stage-tips">
              <li>描述光线、时间与主体，比堆砌形容词更有效</li>
              <li>生成结果会标注为「AI 生成」，发布后进入人工审核</li>
              <li>草稿图只对你可见，删除后不会保留</li>
            </ul>
          </div>

          <!-- 排队 / 生成中 -->
          <div v-else-if="stage === 'loading'" class="stage-progress">
            <div class="progress-orb" aria-hidden="true">
              <span></span><span></span><span></span>
            </div>
            <h2>{{ generation?.status === 'running' ? '正在生成画面' : '已提交，正在排队' }}</h2>
            <p class="progress-time"><n-icon :component="TimeOutline" /> 已用 {{ elapsed }} 秒 · 通常 {{ estSeconds }} 秒左右</p>
            <div class="progress-track" role="progressbar" aria-label="生成进度" aria-valuetext="生成中">
              <span class="progress-bar"></span>
            </div>
            <p class="progress-hint">模型正在画，请先别关闭页面。可以切到别的标签页，但别刷新。</p>
            <n-button text type="primary" class="progress-cancel" @click="cancelToIdle">
              <n-icon :component="CloseCircleOutline" /> 收起等待，稍后在下方记录查看
            </n-button>
          </div>

          <!-- 成功 -->
          <div v-else-if="stage === 'succeeded'" class="stage-result">
            <figure class="result-figure">
              <img v-if="imageUrl" :src="imageUrl" :alt="`AI 生成草稿：${prompt}`" class="result-img" />
              <span v-else class="result-img-placeholder">草稿图加载中…</span>
              <figcaption class="result-caption">
                <span class="result-badge">AI 生成</span>
                <span>{{ generation?.width }}×{{ generation?.height }} · 用时 {{ latencyText }}</span>
              </figcaption>
            </figure>
            <div class="result-actions">
              <n-button type="primary" size="large" :loading="publishing" @click="openPublish">
                <template #icon><n-icon :component="CloudUploadOutline" /></template>
                发布为作品
              </n-button>
              <n-button size="large" :disabled="publishing" @click="startGenerate">
                <template #icon><n-icon :component="RefreshOutline" /></template>
                重新生成
              </n-button>
              <n-button size="large" quaternary type="error" :disabled="publishing" @click="removeCurrent">
                <template #icon><n-icon :component="TrashOutline" /></template>
                删除
              </n-button>
            </div>
            <p class="result-note">发布时会自动带上 AI 声明与生成参数；作品将进入人工审核。</p>
          </div>

          <!-- 失败 -->
          <div v-else-if="stage === 'failed'" class="stage-failed">
            <span class="stage-failed-icon" aria-hidden="true">
              <n-icon :component="CloseCircleOutline" size="40" />
            </span>
            <h2>这次没有画出来</h2>
            <p class="failed-msg">{{ errorText || generation?.error || '生成失败，请稍后再试。' }}</p>
            <div class="result-actions">
              <n-button type="primary" size="large" @click="startGenerate">再试一次</n-button>
              <n-button size="large" quaternary type="error" @click="removeCurrent">删除记录</n-button>
            </div>
          </div>
        </section>
      </div>

      <!-- 历史记录 -->
      <section class="history" aria-labelledby="history-title">
        <div class="history-head">
          <h2 id="history-title" class="history-title">最近生成</h2>
          <span class="history-sub">只保存在你自己的账号下 · 点开可预览</span>
        </div>
        <div v-if="historyLoading" class="history-grid">
          <span v-for="n in 4" :key="n" class="history-skeleton" aria-hidden="true"></span>
        </div>
        <p v-else-if="!history.length" class="history-empty">还没有生成记录，写下第一句描述吧。</p>
        <ul v-else class="history-grid">
          <li v-for="item in history" :key="item.id" class="history-item">
            <button
              type="button"
              class="history-btn"
              :class="{ 'is-disabled': item.status !== 'succeeded' }"
              :disabled="item.status !== 'succeeded'"
              :aria-label="`查看生成记录：${item.prompt.slice(0, 40)}`"
              @click="previewHistory(item)"
            >
              <img
                v-if="historyThumbs[item.id]"
                :src="historyThumbs[item.id]"
                :alt="`AI 生成草稿：${item.prompt.slice(0, 30)}`"
                class="history-thumb"
                loading="lazy"
              />
              <span v-else class="history-thumb history-thumb--empty" aria-hidden="true">
                <n-icon :component="ImageOutline" size="22" />
              </span>
              <n-tag :type="statusTagType(item.status)" size="small" class="history-tag">
                {{ statusLabel(item.status) }}
              </n-tag>
            </button>
            <button
              type="button"
              class="history-del"
              :aria-label="`删除这条记录：${item.prompt.slice(0, 30)}`"
              @click.stop="removeHistory(item.id)"
            >
              <n-icon :component="CloseOutline" size="14" />
            </button>
          </li>
        </ul>
      </section>
    </div>

    <!-- 发布对话框 -->
    <n-modal
      v-model:show="publishOpen"
      preset="card"
      class="publish-modal"
      :title="'发布为 AI 生成作品'"
      :bordered="false"
      :mask-closable="!publishing"
      :close-on-esc="!publishing"
    >
      <div class="publish-body">
        <label class="publish-label" for="publish-title">作品标题</label>
        <n-input
          id="publish-title"
          v-model:value="publishTitle"
          maxlength="80"
          show-count
          placeholder="给这张作品起个名字"
          :disabled="publishing"
        />
        <label class="publish-check">
          <n-checkbox v-model:checked="publishPromptPublic" :disabled="publishing" />
          <span>公开生成提示词（其他人能看到你写的描述）</span>
        </label>
        <n-alert type="info" :bordered="false" class="publish-note">
          发布后将显示「AI 生成」角标，下载副本会写入隐式标识；作品需人工审核后才能公开展示。
        </n-alert>
      </div>
      <template #footer>
        <div class="publish-footer">
          <n-button :disabled="publishing" @click="publishOpen = false">取消</n-button>
          <n-button type="primary" :loading="publishing" :disabled="!publishTitle.trim()" @click="submitPublish">
            发布并进入审核
          </n-button>
        </div>
      </template>
    </n-modal>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  ArrowBackOutline,
  CloseCircleOutline,
  CloseOutline,
  CloudUploadOutline,
  ImageOutline,
  RefreshOutline,
  SparklesOutline,
  TimeOutline,
  TrashOutline,
} from '@vicons/ionicons5'
import {
  createAigcGeneration,
  deleteAigcGeneration,
  fetchAigcImageBlob,
  getAigcConfig,
  getAigcGeneration,
  listAigcGenerations,
  publishAigcDraft,
  type AigcConfig,
  type AigcGeneration,
  type AigcGenerationStatus,
  type AigcSize,
} from '../api/aigc'

const router = useRouter()
const message = useMessage()

const EXAMPLES = ['黄昏校园里的樱花与红砖', '雨后的教学楼，玻璃反射着灯光', '深夜图书馆，暖黄台灯与书页', '春天的玉兰花，柔焦奶油色调']
const LAST_KEY = 'sakura:aigc-last-generation'
const PROMPT_MAX_FALLBACK = 300

const config = ref<AigcConfig | null>(null)
const configError = ref('')
const prompt = ref('')
const selectedSize = ref<string>('square')
const promptMax = computed(() => config.value?.promptMax || PROMPT_MAX_FALLBACK)
const estSeconds = computed(() => config.value?.estSeconds || 60)

const sizes = computed<AigcSize[]>(() => {
  if (config.value?.sizes?.length) return config.value.sizes
  return [
    { key: 'square', label: '方图', width: 1328, height: 1328, ratio: '1:1' },
    { key: 'landscape', label: '横图', width: 1664, height: 928, ratio: '16:9' },
    { key: 'portrait', label: '竖图', width: 928, height: 1664, ratio: '9:16' },
  ]
})

const dailyUsed = ref(0)
const dailyLimit = computed(() => config.value?.dailyLimit || 5)
const quotaLeft = computed(() => Math.max(0, dailyLimit.value - dailyUsed.value))

const stage = ref<'idle' | 'loading' | 'succeeded' | 'failed'>('idle')
const submitting = ref(false)
const generation = ref<AigcGeneration | null>(null)
const errorText = ref('')
const imageBlob = ref<Blob | null>(null)
const imageUrl = ref('')
const startedAt = ref(0)
const elapsed = ref(0)
const latencyText = computed(() => {
  const ms = generation.value?.latencyMs
  if (!ms) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} 秒` : `${Math.round(ms)} 毫秒`
})

const generating = computed(() => stage.value === 'loading' && !!generation.value)
const canGenerate = computed(() => !!config.value?.enabled && quotaLeft.value > 0 && !submitting.value)

const history = ref<AigcGeneration[]>([])
const historyLoading = ref(false)
const historyThumbs = ref<Record<string, string>>({})
const historyUrls = new Map<string, string>()

const publishOpen = ref(false)
const publishTitle = ref('')
const publishPromptPublic = ref(true)
const publishing = ref(false)

let pollTimer: number | undefined
let elapsedTimer: number | undefined
let pollGenerationId = ''

/* --------------------------- 工具函数 --------------------------- */

const STATUS_LABEL: Record<AigcGenerationStatus, string> = {
  queued: '排队中',
  running: '生成中',
  succeeded: '已完成',
  failed: '失败',
}

function statusLabel(status: AigcGenerationStatus): string {
  return STATUS_LABEL[status] || status
}

function statusTagType(status: AigcGenerationStatus): 'default' | 'info' | 'success' | 'error' | 'warning' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running') return 'info'
  return 'warning'
}

function describeError(error: unknown, fallback: string): string {
  const anyError = error as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }
  const status = anyError?.response?.status
  const detail = anyError?.response?.data?.detail
  let text = ''
  if (typeof detail === 'string') text = detail
  else if (Array.isArray(detail)) {
    text = detail
      .map((item) => (typeof item === 'string' ? item : (item as { msg?: string })?.msg || ''))
      .filter(Boolean)
      .join('；')
  }
  if (status === 401) return '登录状态已失效，请重新登录后再试。'
  if (status === 403) return '没有权限访问这条记录。'
  if (status === 409) return text || '当前状态不允许这个操作。'
  if (status === 422) return text || '提交的内容不符合要求，请检查后重试。'
  if (status === 429) {
    if (/额度|次数|limit|daily/i.test(text)) return '今天的生成次数已用完，明天再来试试。'
    return '请求过于频繁，请稍后再试。'
  }
  if (status === 503) return 'AI 创作台暂未开启，请稍后再来。'
  if (text) return text
  return anyError?.message || fallback
}

function stopPolling() {
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    pollTimer = undefined
  }
  pollGenerationId = ''
}

function stopElapsed() {
  if (elapsedTimer) {
    window.clearInterval(elapsedTimer)
    elapsedTimer = undefined
  }
}

function startElapsedTimer() {
  stopElapsed()
  startedAt.value = Date.now()
  elapsed.value = 0
  elapsedTimer = window.setInterval(() => {
    if (!startedAt.value) return
    elapsed.value = Math.max(0, Math.round((Date.now() - startedAt.value) / 1000))
  }, 1000)
}

function revokeImageUrl() {
  if (imageUrl.value) {
    URL.revokeObjectURL(imageUrl.value)
    imageUrl.value = ''
  }
  imageBlob.value = null
}

function revokeHistoryUrls() {
  for (const url of historyUrls.values()) URL.revokeObjectURL(url)
  historyUrls.clear()
  historyThumbs.value = {}
}

function setThumb(id: string, url: string) {
  const old = historyUrls.get(id)
  if (old) URL.revokeObjectURL(old)
  historyUrls.set(id, url)
  historyThumbs.value = { ...historyThumbs.value, [id]: url }
}

async function loadThumbFor(item: AigcGeneration) {
  if (item.status !== 'succeeded' || historyThumbs.value[item.id]) return
  try {
    const blob = await fetchAigcImageBlob(item.id)
    if (!historyUrls.has(item.id)) setThumb(item.id, URL.createObjectURL(blob))
  } catch {
    /* 缩略图失败静默，不影响主流程 */
  }
}

function rememberLastId(id: string | null) {
  try {
    if (id) localStorage.setItem(LAST_KEY, id)
    else localStorage.removeItem(LAST_KEY)
  } catch {
    /* 隐私模式忽略 */
  }
}

/* --------------------------- 数据加载 --------------------------- */

async function loadConfig() {
  configError.value = ''
  try {
    config.value = await getAigcConfig()
    if (!selectedSize.value && config.value.sizes[0]) selectedSize.value = config.value.sizes[0].key
    if (!config.value.sizes.some((size) => size.key === selectedSize.value) && config.value.sizes[0]) {
      selectedSize.value = config.value.sizes[0].key
    }
  } catch (error) {
    config.value = null
    configError.value = describeError(error, '创作台配置加载失败，请稍后重试。')
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const data = await listAigcGenerations(12)
    dailyUsed.value = data.dailyUsed
    history.value = data.items
    for (const item of data.items) void loadThumbFor(item)
  } catch {
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

/* --------------------------- 生成流程 --------------------------- */

function useExample(text: string) {
  prompt.value = text
}

function clearGenerationState() {
  stopPolling()
  stopElapsed()
  revokeImageUrl()
  generation.value = null
  errorText.value = ''
  elapsed.value = 0
  startedAt.value = 0
  stage.value = 'idle'
  rememberLastId(null)
}

async function loadImageFor(generationId: string) {
  revokeImageUrl()
  try {
    const blob = await fetchAigcImageBlob(generationId)
    imageBlob.value = blob
    imageUrl.value = URL.createObjectURL(blob)
    if (historyUrls.has(generationId)) setThumb(generationId, imageUrl.value)
  } catch (error) {
    errorText.value = describeError(error, '草稿图加载失败，可以稍后在记录里重新打开。')
  }
}

function applyGeneration(next: AigcGeneration) {
  generation.value = next
  if (next.status === 'succeeded') {
    stopElapsed()
    stage.value = 'succeeded'
    void loadImageFor(next.id)
    void loadHistory()
  } else if (next.status === 'failed') {
    stopElapsed()
    stage.value = 'failed'
    errorText.value = next.error || '生成失败，请稍后再试。'
    void loadHistory()
  } else {
    stage.value = 'loading'
    if (!startedAt.value) {
      const startMs = next.createdAt ? new Date(next.createdAt).getTime() : Date.now()
      startedAt.value = Number.isFinite(startMs) ? startMs : Date.now()
    }
    startElapsedTimer()
  }
}

async function pollOnce(generationId: string) {
  pollGenerationId = generationId
  try {
    const next = await getAigcGeneration(generationId)
    if (pollGenerationId !== generationId) return
    if (!next) return
    applyGeneration(next)
    if (next.status === 'queued' || next.status === 'running') schedulePoll(generationId)
  } catch (error) {
    if (pollGenerationId !== generationId) return
    const text = describeError(error, '轮询生成状态失败')
    // 401/403 直接停，其他错误多给一次机会后停止
    if (/登录|权限/.test(text)) {
      stopPolling()
      stopElapsed()
      stage.value = 'failed'
      errorText.value = text
    } else {
      errorText.value = text
      schedulePoll(generationId, 5000)
    }
  }
}

function schedulePoll(generationId: string, delay = 3000) {
  stopPolling()
  pollGenerationId = generationId
  pollTimer = window.setTimeout(() => {
    if (pollGenerationId === generationId) void pollOnce(generationId)
  }, delay)
}

async function startGenerate() {
  if (!config.value?.enabled) return
  if (quotaLeft.value <= 0) {
    message.warning('今天的生成次数已用完，明天再来试试')
    return
  }
  const text = prompt.value.trim()
  if (!text) {
    message.warning('先写一句你想要的画面')
    return
  }
  if (text.length > promptMax.value) {
    message.warning(`描述不能超过 ${promptMax.value} 字`)
    return
  }
  submitting.value = true
  errorText.value = ''
  try {
    revokeImageUrl()
    const created = await createAigcGeneration(text, selectedSize.value)
    generation.value = created
    stage.value = 'loading'
    startedAt.value = Date.now()
    elapsed.value = 0
    startElapsedTimer()
    rememberLastId(created.id)
    dailyUsed.value = Math.min(dailyLimit.value, dailyUsed.value + 1)
    schedulePoll(created.id, 3000)
  } catch (error) {
    stage.value = 'failed'
    errorText.value = describeError(error, '提交生成任务失败，请稍后再试。')
  } finally {
    submitting.value = false
  }
}

function cancelToIdle() {
  stopPolling()
  stopElapsed()
  stage.value = 'idle'
}

async function previewHistory(item: AigcGeneration) {
  if (item.status !== 'succeeded') return
  cancelToIdleForHistory()
  generation.value = item
  prompt.value = item.prompt
  selectedSize.value = item.size
  startedAt.value = 0
  stage.value = 'succeeded'
  await loadImageFor(item.id)
  rememberLastId(item.id)
}

function cancelToIdleForHistory() {
  stopPolling()
  stopElapsed()
  revokeImageUrl()
  errorText.value = ''
}

async function removeHistory(historyId: string) {
  if (!historyId) return
  try {
    await deleteAigcGeneration(historyId)
    history.value = history.value.filter((item) => item.id !== historyId)
    const url = historyUrls.get(historyId)
    if (url) {
      URL.revokeObjectURL(url)
      historyUrls.delete(historyId)
      const nextThumbs = { ...historyThumbs.value }
      delete nextThumbs[historyId]
      historyThumbs.value = nextThumbs
    }
    if (generation.value?.id === historyId) clearGenerationState()
    message.success('记录已删除')
  } catch (error) {
    message.error(describeError(error, '删除失败，请稍后再试'))
  }
}

async function removeCurrent() {
  const currentId = generation.value?.id
  if (!currentId) {
    clearGenerationState()
    return
  }
  await removeHistory(currentId)
}

/* --------------------------- 发布流程 --------------------------- */

function openPublish() {
  if (!generation.value || !imageBlob.value) {
    message.warning('草稿图还没准备好，请稍等')
    return
  }
  publishTitle.value = prompt.value.trim().slice(0, 30) || 'AI 生成作品'
  publishPromptPublic.value = true
  publishOpen.value = true
}

async function submitPublish() {
  if (!generation.value || !imageBlob.value) return
  const title = publishTitle.value.trim()
  if (!title) {
    message.warning('给作品起个标题再发布')
    return
  }
  publishing.value = true
  try {
    const result = await publishAigcDraft({
      blob: imageBlob.value,
      title,
      prompt: prompt.value.trim(),
      model: generation.value.model,
      provider: '阿里云百炼',
      promptPublic: publishPromptPublic.value,
    })
    publishOpen.value = false
    message.success('已提交，正在进入审核')
    rememberLastId(null)
    await router.push(`/photo/${result.id}`)
  } catch (error) {
    message.error(describeError(error, '发布失败，请稍后再试'))
  } finally {
    publishing.value = false
  }
}

/* --------------------------- 恢复 / 清理 --------------------------- */

async function restoreLastGeneration() {
  let lastId: string | null = null
  try {
    lastId = localStorage.getItem(LAST_KEY)
  } catch {
    lastId = null
  }
  if (!lastId) return
  try {
    const restored = await getAigcGeneration(lastId)
    if (!restored) {
      rememberLastId(null)
      return
    }
    if (restored.status === 'queued' || restored.status === 'running') {
      generation.value = restored
      prompt.value = restored.prompt
      selectedSize.value = restored.size
      stage.value = 'loading'
      startedAt.value = restored.createdAt ? new Date(restored.createdAt).getTime() : Date.now()
      startElapsedTimer()
      schedulePoll(restored.id, 1000)
    } else if (restored.status === 'succeeded') {
      generation.value = restored
      prompt.value = restored.prompt
      selectedSize.value = restored.size
      stage.value = 'succeeded'
      await loadImageFor(restored.id)
    } else {
      rememberLastId(null)
    }
  } catch {
    rememberLastId(null)
  }
}

onMounted(async () => {
  await loadConfig()
  await Promise.all([loadHistory(), restoreLastGeneration()])
})

onBeforeUnmount(() => {
  stopPolling()
  stopElapsed()
  revokeImageUrl()
  revokeHistoryUrls()
})
</script>

<style scoped>
.create-page {
  padding: clamp(20px, 3vw, 36px) 0 clamp(56px, 7vw, 96px);
  background:
    radial-gradient(1100px 480px at 12% -8%, var(--sakura-wash, #ffe9f0) 0%, transparent 70%),
    radial-gradient(900px 420px at 96% 0%, var(--winter-pale, #d6e8f7) 0%, transparent 62%);
}

.wrap {
  width: min(var(--maxw, 1320px), 100%);
  margin-inline: auto;
  padding-inline: var(--margin, 24px);
}

.cr {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  font-size: var(--fs-sm, 14px);
  color: var(--muted, #63474f);
}

.cr-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
  color: var(--ink, #4a2b35);
}

.cr-back:hover {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.cr nav {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cr nav a {
  color: inherit;
}

.cr nav span[aria-hidden] {
  color: var(--faint, rgba(99, 71, 79, 0.5));
}

.create-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.16em;
  color: var(--sakura-deep, #c93a63);
}

.create-title {
  margin: 0;
  font-family: var(--display, 'ZCOOL QingKe HuangYou'), var(--font, 'Noto Sans SC'), sans-serif;
  font-size: clamp(40px, 4.6vw, 58px);
  line-height: 1.06;
  letter-spacing: 0.02em;
  color: var(--ink, #4a2b35);
}

.create-lead {
  margin: 10px 0 0;
  max-width: 46em;
  font-size: var(--fs-16, 16px);
  line-height: 1.8;
  color: var(--muted, #63474f);
}

.create-meta {
  display: flex;
  gap: 26px;
  margin: 0;
  flex-shrink: 0;
}

.create-meta div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.create-meta dt {
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--faint, rgba(99, 71, 79, 0.6));
}

.create-meta dd {
  margin: 0;
  font-size: var(--fs-14, 14px);
  font-weight: 600;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.create-meta .quota.is-used {
  color: var(--autumn, #b5703c);
}

.create-disabled {
  margin-bottom: 16px;
}

.create-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr);
  gap: var(--gap, 20px);
  align-items: start;
}

.form-card,
.stage-card {
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
  padding: clamp(18px, 2.2vw, 26px);
}

.form-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.form-title {
  margin: 0;
  font-size: var(--fs-22, 22px);
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.form-hint {
  font-size: 12px;
  color: var(--faint, rgba(99, 71, 79, 0.6));
  font-variant-numeric: tabular-nums;
}

.prompt-input :deep(.n-input__textarea-el) {
  font-size: var(--fs-16, 16px);
  line-height: 1.75;
}

.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.example-chip {
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--line-strong, #e8cdd6);
  background: var(--surface-soft, #fff8fb);
  color: var(--ink-soft, #5b3a45);
  font-size: 13px;
  cursor: pointer;
  min-height: 36px;
}

.example-chip:hover {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.example-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.size-field {
  margin-top: 20px;
}

.size-label {
  display: block;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-soft, #5b3a45);
}

.size-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.size-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: var(--r-sm, 10px);
  border: 1px solid var(--line-strong, #e8cdd6);
  background: var(--surface, #fff);
  cursor: pointer;
  text-align: left;
  min-height: 44px;
}

.size-card.is-active {
  border-color: var(--sakura-deep, #c93a63);
  background: var(--sakura-wash, #fff0f5);
  box-shadow: 0 0 0 1px var(--sakura-deep, #c93a63) inset;
}

.size-card:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.size-shape {
  display: block;
  width: 100%;
  border-radius: 6px;
  border: 1.5px dashed var(--sakura, #e8628c);
  background: var(--sakura-pale, #ffe9f0);
}

.shape-square {
  aspect-ratio: 1 / 1;
}

.shape-landscape {
  aspect-ratio: 16 / 9;
}

.shape-portrait {
  aspect-ratio: 9 / 16;
  max-width: 44px;
  margin-inline: auto;
}

.size-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.size-copy b {
  font-size: 13px;
  color: var(--ink, #4a2b35);
}

.size-copy small {
  font-size: 11px;
  color: var(--faint, rgba(99, 71, 79, 0.65));
  font-variant-numeric: tabular-nums;
}

.form-actions {
  margin-top: 22px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.generate-btn {
  width: 100%;
  height: 48px;
  border-radius: 999px;
  font-size: var(--fs-16, 16px);
}

.quota-note {
  margin: 0;
  font-size: 12px;
  color: var(--faint, rgba(99, 71, 79, 0.65));
  text-align: center;
}

.stage-card {
  min-height: 460px;
  display: flex;
  flex-direction: column;
}

.stage-empty,
.stage-progress,
.stage-failed {
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 12px;
  padding: 20px;
  max-width: 34em;
}

.stage-empty-icon,
.stage-failed-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 76px;
  height: 76px;
  border-radius: 50%;
  background: var(--sakura-wash, #fff0f5);
  color: var(--sakura-deep, #c93a63);
}

.stage-failed-icon {
  background: var(--autumn-pale, #ffdfd6);
  color: var(--autumn, #b5703c);
}

.stage-empty h2,
.stage-progress h2,
.stage-failed h2 {
  margin: 0;
  font-family: var(--display, 'ZCOOL QingKe HuangYou'), var(--font, 'Noto Sans SC'), sans-serif;
  font-size: 28px;
  letter-spacing: 0.02em;
  color: var(--ink, #4a2b35);
}

.stage-empty p,
.stage-progress p,
.stage-failed p {
  margin: 0;
  font-size: 14px;
  line-height: 1.8;
  color: var(--muted, #63474f);
}

.stage-tips {
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--faint, rgba(99, 71, 79, 0.7));
}

.progress-orb {
  position: relative;
  width: 74px;
  height: 74px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.progress-orb span {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid var(--sakura, #e8628c);
  opacity: 0;
  animation: orb-pulse 2.4s ease-out infinite;
}

.progress-orb span:nth-child(2) {
  animation-delay: 0.8s;
}

.progress-orb span:nth-child(3) {
  animation-delay: 1.6s;
}

.progress-orb::after {
  content: 'AI';
  font-family: var(--display, 'ZCOOL QingKe HuangYou'), var(--font, 'Noto Sans SC'), sans-serif;
  font-size: 22px;
  color: var(--sakura-deep, #c93a63);
}

@keyframes orb-pulse {
  0% {
    transform: scale(0.6);
    opacity: 0.75;
  }
  100% {
    transform: scale(1.25);
    opacity: 0;
  }
}

.progress-time {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
  color: var(--ink-soft, #5b3a45) !important;
}

.progress-track {
  width: min(320px, 100%);
  height: 6px;
  border-radius: 999px;
  background: var(--sakura-pale, #ffe9f0);
  overflow: hidden;
}

.progress-bar {
  display: block;
  width: 40%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--sakura, #e8628c), var(--sakura-deep, #c93a63));
  animation: bar-slide 1.6s ease-in-out infinite;
}

@keyframes bar-slide {
  0% {
    transform: translateX(-30%);
  }
  100% {
    transform: translateX(260%);
  }
}

.progress-hint {
  font-size: 12px !important;
  color: var(--faint, rgba(99, 71, 79, 0.6)) !important;
}

.progress-cancel {
  margin-top: 4px;
}

.stage-result {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.result-figure {
  margin: 0;
  background: var(--ground, #fff6f9);
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  padding: 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.result-img,
.result-img-placeholder {
  display: block;
  width: 100%;
  max-height: 62vh;
  object-fit: contain;
  border-radius: var(--r-photo, 16px);
  background: var(--sakura-wash, #fff0f5);
}

.result-img-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  color: var(--faint, rgba(99, 71, 79, 0.6));
  font-size: 13px;
}

.result-caption {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--faint, rgba(99, 71, 79, 0.7));
  font-variant-numeric: tabular-nums;
}

.result-badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--ink, #4a2b35);
  color: var(--on-accent, #fff);
  font-size: 11px;
  letter-spacing: 0.04em;
}

.result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.result-actions :deep(.n-button) {
  border-radius: 999px;
}

.result-note {
  margin: 0;
  font-size: 12px;
  color: var(--faint, rgba(99, 71, 79, 0.7));
}

.failed-msg {
  max-width: 30em;
  word-break: break-word;
}

.history {
  margin-top: clamp(28px, 4vw, 44px);
}

.history-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.history-title {
  margin: 0;
  font-size: var(--fs-22, 22px);
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.history-sub {
  font-size: 12px;
  color: var(--faint, rgba(99, 71, 79, 0.6));
}

.history-empty {
  margin: 0;
  padding: 26px 16px;
  border: 1px dashed var(--line-strong, #e8cdd6);
  border-radius: var(--r-card, 20px);
  text-align: center;
  font-size: 13px;
  color: var(--faint, rgba(99, 71, 79, 0.65));
}

.history-grid {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--gap-sm, 12px);
}

.history-skeleton {
  display: block;
  aspect-ratio: 1 / 1;
  border-radius: var(--r-sm, 10px);
  background: linear-gradient(90deg, var(--sakura-wash, #fff0f5) 25%, var(--surface-soft, #fff8fb) 37%, var(--sakura-wash, #fff0f5) 63%);
  background-size: 300% 100%;
  animation: shimmer 1.4s ease infinite;
}

@keyframes shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: 0 0;
  }
}

.history-item {
  position: relative;
}

.history-btn {
  position: relative;
  display: block;
  width: 100%;
  padding: 0;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-sm, 10px);
  overflow: hidden;
  background: var(--surface, #fff);
  cursor: pointer;
  min-height: 44px;
}

.history-btn:hover .history-thumb,
.history-btn:focus-visible .history-thumb {
  transform: scale(1.03);
}

.history-btn.is-disabled {
  cursor: default;
}

.history-btn.is-disabled:hover .history-thumb {
  transform: none;
}

.history-thumb {
  display: block;
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: contain;
  background: var(--ground, #fff6f9);
  transition: transform 180ms ease;
}

.history-thumb--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--faint, rgba(99, 71, 79, 0.5));
}

.history-tag {
  position: absolute;
  left: 6px;
  bottom: 6px;
}

.history-del {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 44px;
  height: 44px;
  transform: translate(10px, -10px) scale(0.6);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid var(--line-strong, #e8cdd6);
  background: var(--surface, #fff);
  color: var(--muted, #63474f);
  opacity: 0;
  transition: opacity 160ms ease, transform 160ms ease;
  cursor: pointer;
}

@media (pointer: coarse) {
  .history-del {
    opacity: 1;
    transform: none;
    width: 44px;
    height: 44px;
  }
}

.history-item:hover .history-del,
.history-del:focus-visible {
  opacity: 1;
  transform: none;
}

.history-del:hover {
  color: var(--sakura-deep, #c93a63);
  border-color: var(--sakura, #e8628c);
}

.publish-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.publish-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-soft, #5b3a45);
}

.publish-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted, #63474f);
  cursor: pointer;
}

.publish-note {
  margin-top: 2px;
}

.publish-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.publish-footer :deep(.n-button) {
  border-radius: 999px;
}

:global(.publish-modal) {
  width: min(92vw, 520px);
}

:global(.publish-modal .n-card-header__main) {
  font-family: var(--display, 'ZCOOL QingKe HuangYou'), var(--font, 'Noto Sans SC'), sans-serif;
  font-size: 22px;
  color: var(--ink, #4a2b35);
}

.create-page :deep(.n-button--primary-type) {
  --n-color: var(--sakura-deep, #c93a63) !important;
  --n-color-hover: var(--sakura-deep-hover, #a82c50) !important;
  --n-color-pressed: var(--sakura-deep-hover, #a82c50) !important;
  --n-border: 1px solid var(--sakura-deep, #c93a63) !important;
  --n-border-hover: 1px solid var(--sakura-deep-hover, #a82c50) !important;
  --n-border-pressed: 1px solid var(--sakura-deep-hover, #a82c50) !important;
  --n-text-color: var(--on-accent, #fff) !important;
  --n-text-color-hover: var(--on-accent, #fff) !important;
  --n-text-color-pressed: var(--on-accent, #fff) !important;
}

.create-page :deep(.n-input),
.create-page :deep(.n-base-selection) {
  --n-border-radius: 10px;
}

.create-page :deep(.n-input__border),
.create-page :deep(.n-input__state-border) {
  border-radius: 10px;
}

.create-page :focus-visible {
  outline: 3px solid color-mix(in srgb, var(--sakura-deep, #c93a63) 55%, transparent);
  outline-offset: 2px;
}

@media (max-width: 1100px) {
  .create-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .create-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .create-meta {
    gap: 20px;
  }

  .stage-card {
    min-height: 380px;
  }
}

@media (max-width: 640px) {
  .create-page {
    padding-top: 14px;
  }

  .create-title {
    font-size: 40px;
  }

  .size-options {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
  }

  .size-card {
    padding: 10px;
    gap: 8px;
  }

  .size-copy small {
    font-size: 10px;
  }

  .example-chip {
    font-size: 12px;
    padding: 8px 12px;
  }

  .form-actions :deep(.n-button) {
    width: 100%;
  }

  .result-actions {
    flex-direction: column;
  }

  .result-actions :deep(.n-button) {
    width: 100%;
  }

  .history-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  .progress-bar,
  .progress-orb span,
  .history-skeleton {
    animation: none !important;
  }

  .history-thumb {
    transition: none;
  }
}
</style>
