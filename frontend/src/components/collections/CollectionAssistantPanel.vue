<template>
  <section class="asst-card" aria-labelledby="asst-title">
    <div class="asst-head">
      <span class="asst-seal" aria-hidden="true">
        <n-icon :component="SparklesOutline" :size="16" />
      </span>
      <div class="asst-head-copy">
        <h3 id="asst-title" class="asst-title">AI 策展助手</h3>
        <p class="asst-desc">写一个主题，我从你的作品里挑一组，确认后再写入专辑。</p>
      </div>
    </div>

    <label class="asst-label" for="asst-prompt">一句话主题</label>
    <n-input
      id="asst-prompt"
      v-model:value="prompt"
      type="textarea"
      :rows="2"
      maxlength="200"
      show-count
      :disabled="generating"
      placeholder="例如：黄昏的校园、雨天的北区…（2–200 字）"
      @keydown.ctrl.enter.prevent="generate"
      @keydown.meta.enter.prevent="generate"
    />

    <div class="asst-examples" role="group" aria-label="示例主题">
      <span class="asst-examples-label">试试</span>
      <button
        v-for="example in examples"
        :key="example"
        type="button"
        class="asst-example"
        :disabled="generating"
        @click="useExample(example)"
      >
        {{ example }}
      </button>
    </div>

    <div class="asst-actions">
      <n-button
        type="primary"
        size="small"
        :loading="generating"
        :disabled="!canGenerate"
        @click="generate"
      >
        <template #icon>
          <n-icon :component="generating ? ReloadOutline : SparklesOutline" />
        </template>
        {{ generating ? 'AI 正在挑选作品…' : proposal ? '重新生成' : '生成提案' }}
      </n-button>
      <span v-if="generating" class="asst-hint">预计 10 秒内，不要重复提交。</span>
      <span v-else class="asst-hint">AI 只出提案，不会自动保存或发布。</span>
    </div>

    <div v-if="generating" class="asst-loading" aria-busy="true" aria-label="AI 正在生成提案">
      <div class="asst-loading-strip">
        <span v-for="index in 5" :key="index" class="asst-loading-pick" />
      </div>
      <div class="asst-loading-line" />
      <div class="asst-loading-line is-short" />
    </div>

    <n-alert v-if="error" class="asst-error" type="error" :bordered="false" role="alert">
      {{ error }}
    </n-alert>

    <div v-if="proposal" class="asst-proposal">
      <div class="asst-proposal-head">
        <p class="asst-proposal-title">提案 · 将挑选 {{ proposal.picks.length }} 张作品</p>
        <p v-if="proposal.note" class="asst-note">{{ proposal.note }}</p>
      </div>

      <div class="asst-fields">
        <label class="asst-field" for="asst-proposal-title">
          <span class="asst-label">标题</span>
          <n-input id="asst-proposal-title" v-model:value="draftTitle" maxlength="60" show-count />
        </label>
        <label class="asst-field" for="asst-proposal-subtitle">
          <span class="asst-label">副标题</span>
          <n-input id="asst-proposal-subtitle" v-model:value="draftSubtitle" maxlength="100" show-count />
        </label>
        <label class="asst-field" for="asst-proposal-desc">
          <span class="asst-label">引言</span>
          <n-input
            id="asst-proposal-desc"
            v-model:value="draftDescription"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-count
          />
        </label>
      </div>

      <ul class="asst-strip" aria-label="提案作品，按观展顺序">
        <li v-for="(pick, index) in proposal.picks" :key="pick.photo.id" class="asst-pick">
          <div class="asst-pick-cover">
            <img
              :src="pick.photo.thumbUrl"
              :alt="photoAlt(pick.photo)"
              loading="lazy"
              decoding="async"
            />
            <span v-if="pick.photo.aigc" class="asst-pick-badge">AI 生成</span>
            <span class="asst-pick-index" aria-hidden="true">{{ index + 1 }}</span>
          </div>
          <p class="asst-pick-title" :title="displayTitle(pick.photo)">{{ displayTitle(pick.photo) }}</p>
          <p v-if="pick.reason" class="asst-pick-reason" :title="pick.reason">{{ pick.reason }}</p>
        </li>
      </ul>

      <div class="asst-proposal-actions">
        <n-button type="primary" size="small" @click="apply">
          <template #icon>
            <n-icon :component="CheckmarkOutline" />
          </template>
          应用到专辑
        </n-button>
        <n-button size="small" :loading="generating" @click="generate">重新生成</n-button>
        <button type="button" class="asst-cancel" @click="dismiss">取消</button>
      </div>
      <p class="asst-apply-hint">应用只写入表单与已选作品，仍需你手动「保存草稿」或「发布」。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckmarkOutline, ReloadOutline, SparklesOutline } from '@vicons/ionicons5'
import {
  generateCollectionAssistant,
  type CollectionAssistantApplyPayload,
  type CollectionAssistantProposal,
} from '../../api/collections'
import type { PublicPhoto } from '../../api/public'
import { displayPhotoTitle } from '../../utils/photoDisplay'

const emit = defineEmits<{ apply: [payload: CollectionAssistantApplyPayload] }>()

const examples = ['黄昏的校园', '雨天的北区']

const prompt = ref('')
const generating = ref(false)
const error = ref('')
const proposal = ref<CollectionAssistantProposal | null>(null)

const draftTitle = ref('')
const draftSubtitle = ref('')
const draftDescription = ref('')

const canGenerate = computed(() => {
  const text = prompt.value.trim()
  return text.length >= 2 && text.length <= 200 && !generating.value
})

function useExample(example: string) {
  prompt.value = example
  error.value = ''
}

function displayTitle(photo: PublicPhoto): string {
  return displayPhotoTitle(photo as never) || photo.title || '未命名作品'
}

function photoAlt(photo: PublicPhoto): string {
  const author = photo.author || ''
  return author ? `${displayTitle(photo)} · ${author}` : displayTitle(photo)
}

function describeError(e: unknown): string {
  const response = (e as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  const status = response?.status
  const detailRaw = response?.data?.detail
  const detail =
    typeof detailRaw === 'string'
      ? detailRaw
      : Array.isArray(detailRaw) && detailRaw[0] && typeof (detailRaw[0] as { msg?: unknown }).msg === 'string'
        ? (detailRaw[0] as { msg: string }).msg
        : ''
  if (status === 400) return detail || '还没有可以用来策展的作品，先发布几张再来试试。'
  if (status === 422) return detail || '主题需要 2–200 个字，请调整后再试。'
  if (status === 429) {
    const base = detail || '生成太频繁了'
    return /稍等|稍后|分钟/.test(base) ? base : `${base}，稍等一分钟再试。`
  }
  if (status === 503) return detail || 'AI 暂时不可用，请稍后再试。'
  if (status === 401) return '登录已过期，请重新登录后再试。'
  if (!status) return '网络连接失败，请检查网络后重试。'
  return detail || `生成失败（HTTP ${status}），请稍后重试。`
}

async function generate() {
  if (generating.value) return
  const text = prompt.value.trim()
  if (text.length < 2) {
    error.value = '先用一句话写个主题（至少 2 个字）。'
    return
  }
  generating.value = true
  error.value = ''
  proposal.value = null
  try {
    const result = await generateCollectionAssistant(text)
    if (!result.picks.length) {
      error.value = '这次没有挑出合适的作品，换个主题或再试一次。'
      return
    }
    proposal.value = result
    draftTitle.value = result.title
    draftSubtitle.value = result.subtitle
    draftDescription.value = result.description
  } catch (e) {
    error.value = describeError(e)
  } finally {
    generating.value = false
  }
}

function apply() {
  if (!proposal.value) return
  const photos = proposal.value.picks.map((pick) => pick.photo)
  emit('apply', {
    title: draftTitle.value.trim(),
    subtitle: draftSubtitle.value.trim(),
    description: draftDescription.value.trim(),
    photos,
  })
}

function dismiss() {
  proposal.value = null
  error.value = ''
}
</script>

<style scoped>
.asst-card {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: var(--r-md, 14px);
  background: linear-gradient(180deg, var(--sakura-wash, #fff3f7), var(--surface));
}

.asst-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
}

.asst-seal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 50%;
  background: var(--sakura-pale, #ffe9f0);
  color: var(--sakura-deep);
}

.asst-title {
  margin: 0 0 2px;
  color: var(--ink);
  font-family: var(--display);
  font-size: 20px;
  font-weight: 400;
  letter-spacing: 0.01em;
}

.asst-desc {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-xs, 12px);
  line-height: 1.6;
}

.asst-label {
  display: block;
  margin: 10px 0 6px;
  color: var(--ink);
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
}

.asst-examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.asst-examples-label {
  color: var(--faint);
  font-size: var(--fs-xs, 12px);
}

.asst-example {
  padding: 3px 12px;
  border: 1px solid var(--line-strong, #e9c6d3);
  border-radius: var(--r-pill, 999px);
  background: var(--surface);
  color: var(--muted);
  font-size: var(--fs-xs, 12px);
  cursor: pointer;
  transition:
    border-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out),
    background var(--dur-fast) var(--ease-out);
}

.asst-example:hover:not(:disabled) {
  border-color: var(--sakura);
  background: var(--sakura-wash, #fff3f7);
  color: var(--sakura-deep);
}

.asst-example:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 2px;
}

.asst-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.asst-hint {
  color: var(--faint);
  font-size: var(--fs-xs, 12px);
}

.asst-loading {
  margin-top: 12px;
}

.asst-loading-strip {
  display: flex;
  gap: 8px;
  overflow: hidden;
}

.asst-loading-pick {
  width: 96px;
  aspect-ratio: 4 / 3;
  flex: none;
  border-radius: var(--r-photo, 16px);
  background: linear-gradient(
    100deg,
    var(--sakura-wash, #fff3f7) 20%,
    var(--sakura-mist, #ffe1ea) 40%,
    var(--sakura-wash, #fff3f7) 60%
  );
  background-size: 220% 100%;
  animation: asst-shimmer 1.2s linear infinite;
}

.asst-loading-line {
  height: 10px;
  margin-top: 10px;
  border-radius: 6px;
  background: var(--sakura-wash, #fff3f7);
}

.asst-loading-line.is-short {
  width: 58%;
}

@keyframes asst-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}

.asst-error {
  margin-top: 12px;
}

.asst-proposal {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--line-strong, #e9c6d3);
}

.asst-proposal-title {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-sm, 14px);
  font-weight: 600;
}

.asst-note {
  margin: 6px 0 0;
  padding: 6px 10px;
  border-radius: var(--r-sm, 10px);
  background: var(--sakura-wash, #fff3f7);
  color: var(--sakura-deep);
  font-size: var(--fs-xs, 12px);
  line-height: 1.6;
}

.asst-fields {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.asst-field .asst-label {
  margin-top: 0;
}

.asst-strip {
  display: flex;
  gap: 10px;
  margin: 12px 0 0;
  padding: 0 0 4px;
  overflow-x: auto;
  list-style: none;
  scroll-snap-type: x proximity;
  scrollbar-width: thin;
}

.asst-pick {
  width: 122px;
  flex: none;
  scroll-snap-align: start;
}

.asst-pick-cover {
  position: relative;
  aspect-ratio: 4 / 3;
  border-radius: var(--r-sm, 10px);
  background: var(--sakura-wash, #fff3f7);
  overflow: hidden;
}

.asst-pick-cover img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.asst-pick-badge {
  position: absolute;
  top: 5px;
  left: 5px;
  padding: 1px 6px;
  border-radius: var(--r-pill, 999px);
  background: rgba(255, 255, 255, 0.92);
  color: var(--ink);
  font-size: 10px;
  font-weight: 600;
}

.asst-pick-index {
  position: absolute;
  right: 5px;
  bottom: 5px;
  min-width: 18px;
  padding: 0 4px;
  border-radius: var(--r-pill, 999px);
  background: rgba(74, 43, 53, 0.72);
  color: #fff;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  line-height: 16px;
  text-align: center;
}

.asst-pick-title {
  display: -webkit-box;
  margin: 6px 0 0;
  overflow: hidden;
  color: var(--ink);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.asst-pick-reason {
  display: -webkit-box;
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.asst-proposal-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.asst-cancel {
  border: 0;
  background: none;
  color: var(--muted);
  font-size: var(--fs-xs, 12px);
  text-decoration: underline;
  cursor: pointer;
}

.asst-cancel:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 2px;
}

.asst-apply-hint {
  margin: 8px 0 0;
  color: var(--faint);
  font-size: 11.5px;
  line-height: 1.6;
}

@media (max-width: 560px) {
  .asst-pick {
    width: 104px;
  }

  .asst-proposal-actions {
    gap: 8px;
  }

  .asst-proposal-actions :deep(.n-button) {
    flex: 1 1 auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .asst-loading-pick {
    animation: none;
  }
}
</style>
