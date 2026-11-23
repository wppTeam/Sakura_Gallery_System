<template>
  <section class="rules-panel">
    <header class="panel-head">
      <div class="panel-heading">
        <span class="panel-index">①</span>
        <div>
          <h3 class="panel-title">规则前置</h3>
          <p class="panel-sub">本地校验，不消耗模型额度</p>
        </div>
      </div>
      <n-tag
        v-if="rules"
        size="small"
        :type="rules.blocked ? 'error' : rules.checked ? 'success' : 'default'"
        :bordered="false"
      >
        {{ rules.blocked ? '硬拦' : rules.checked ? '已校验' : '未校验' }}
      </n-tag>
    </header>

    <p v-if="!rules" class="panel-note">无规则校验记录。</p>

    <template v-else>
      <dl class="rule-facts">
        <div v-if="rules.imageFormat">
          <dt>格式</dt>
          <dd>{{ rules.imageFormat.toUpperCase() }}</dd>
        </div>
        <div v-if="rules.width && rules.height">
          <dt>尺寸</dt>
          <dd>{{ rules.width }} × {{ rules.height }}</dd>
        </div>
        <div v-if="rules.fileSize">
          <dt>文件大小</dt>
          <dd>{{ formatFileSize(rules.fileSize) }}</dd>
        </div>
        <div v-if="rules.dhash">
          <dt>感知哈希</dt>
          <dd class="mono" :title="rules.dhash">{{ shortHash }}</dd>
        </div>
        <div v-if="rules.maxSeverity">
          <dt>最高等级</dt>
          <dd>
            <n-tag size="tiny" :type="severityTagType(rules.maxSeverity)" :bordered="false">
              {{ severityLabel(rules.maxSeverity) }}
            </n-tag>
          </dd>
        </div>
      </dl>

      <div v-if="declaration" class="aigc-evidence">
        <p class="aigc-evidence-head">
          <span class="aigc-evidence-title">AIGC 声明证据</span>
          <n-tag size="tiny" :type="declarationTagType" :bordered="false">
            {{ declaration.declared ? '已声明 AI 生成' : '未声明 AIGC' }}
          </n-tag>
          <n-tag
            v-if="declaration.declared && (declaration.faceSwap || declaration.sourceWorkId)"
            size="tiny"
            type="error"
            :bordered="false"
          >
            图生图 / 换脸 · 强制 L2
          </n-tag>
        </p>
        <dl class="aigc-evidence-facts">
          <div v-if="declaration.label">
            <dt>显式标识</dt>
            <dd>{{ declaration.label }}</dd>
          </div>
          <div v-if="declaration.model">
            <dt>生成模型</dt>
            <dd>{{ declaration.model }}</dd>
          </div>
          <div v-if="declaration.provider">
            <dt>服务提供方</dt>
            <dd>{{ declaration.provider }}</dd>
          </div>
          <div v-if="declaration.sourceWorkId">
            <dt>图生图源作品</dt>
            <dd class="mono" :title="declaration.sourceWorkId">{{ shortSourceWork }}</dd>
          </div>
          <div>
            <dt>人脸替换</dt>
            <dd>{{ declaration.faceSwap ? '是' : '否' }}</dd>
          </div>
          <div>
            <dt>被摄者同意</dt>
            <dd :class="declaration.consentConfirmed ? 'is-ok' : consentApplies ? 'is-warn' : ''">
              {{ declaration.consentConfirmed ? '已确认' : consentApplies ? '未确认' : '不适用' }}
            </dd>
          </div>
          <div>
            <dt>提示词公开</dt>
            <dd>{{ declaration.promptPublic ? '是' : '否' }}</dd>
          </div>
        </dl>
        <p v-if="consentMissing" class="aigc-evidence-warning">
          图生图 / 换脸但未确认被摄者同意：应驳回或挂起，要求补充授权材料。
        </p>
        <p v-else-if="declaration.declared" class="aigc-evidence-note">
          下载原图会写入 XMP 隐式标识；请确认详情页显式角标与申报信息一致。
        </p>
      </div>

      <div v-if="rules.hits.length" class="rule-hits">
        <p class="rule-hits-title">命中 {{ rules.hits.length }} 条规则</p>
        <ul class="rule-hit-list">
          <li v-for="(hit, index) in rules.hits" :key="`${hit.code}-${index}`" class="rule-hit">
            <span class="rule-hit-icon" :class="`is-${hit.severity}`">
              <n-icon :size="13">
                <CloseCircleOutline v-if="hit.severity === 'block'" />
                <AlertCircleOutline v-else-if="hit.severity === 'warn'" />
                <InformationCircleOutline v-else />
              </n-icon>
            </span>
            <div class="rule-hit-main">
              <p class="rule-hit-name">
                {{ ruleLabel(hit.code) }}
                <span class="rule-hit-severity">{{ severityLabel(hit.severity) }}</span>
              </p>
              <p v-if="hit.detail" class="rule-hit-detail">{{ hit.detail }}</p>
            </div>
          </li>
        </ul>
      </div>

      <p v-else class="rule-pass">
        <n-icon :size="14" color="var(--summer, #3b9c80)"><CheckmarkCircleOutline /></n-icon>
        未命中风险规则
      </p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertCircleOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline,
  InformationCircleOutline,
} from '@vicons/ionicons5'
import type { RuleResult } from '../../api/moderation'
import { formatFileSize } from '../../utils/format'
import {
  aigcConsentMissing,
  aigcDeclarationTagType,
  ruleLabel,
  severityLabel,
  severityTagType,
} from './reviewDisplay'

const props = defineProps<{
  rules: RuleResult | null
}>()

const shortHash = computed(() => {
  const hash = props.rules?.dhash || ''
  return hash.length > 18 ? `${hash.slice(0, 18)}…` : hash
})

const declaration = computed(() => props.rules?.aigcDeclaration ?? null)
const declarationTagType = computed(() => aigcDeclarationTagType(declaration.value))
const consentApplies = computed(
  () => Boolean(declaration.value?.faceSwap || declaration.value?.sourceWorkId),
)
const consentMissing = computed(() => aigcConsentMissing(declaration.value))
const shortSourceWork = computed(() => {
  const id = declaration.value?.sourceWorkId || ''
  return id.length > 18 ? `${id.slice(0, 18)}…` : id
})
</script>

<style scoped>
.rules-panel {
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-md, 14px);
  background: var(--surface, #fff);
  padding: 13px 14px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.panel-heading {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.panel-index {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--sakura-deep, #c93a63);
  background: var(--sakura-pale, #ffe9f0);
  font-variant-numeric: tabular-nums;
}

.panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink, #4a2b35);
  line-height: 1.4;
}

.panel-sub {
  margin: 1px 0 0;
  font-size: 11px;
  color: var(--faint, #97808a);
}

.panel-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--faint, #97808a);
}

.rule-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin: 11px 0 0;
}

.rule-facts > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rule-facts dt {
  font-size: 10.5px;
  color: var(--faint, #97808a);
}

.rule-facts dd {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.mono {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 11px;
  font-weight: 500;
}

.rule-hits {
  margin-top: 12px;
}

.rule-hits-title {
  margin: 0 0 6px;
  font-size: 11px;
  color: var(--faint, #97808a);
}

.rule-hit-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.rule-hit {
  display: flex;
  gap: 7px;
  padding: 7px 9px;
  border-radius: var(--r-sm, 10px);
  background: var(--ground, #fff6f9);
}

.rule-hit-icon {
  flex: none;
  margin-top: 1px;
}

.rule-hit-icon.is-block { color: var(--sakura-deep, #c93a63); }
.rule-hit-icon.is-warn { color: var(--autumn, #b5703c); }
.rule-hit-icon.is-info { color: var(--winter, #5692c8); }

.rule-hit-main {
  min-width: 0;
}

.rule-hit-name {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.rule-hit-severity {
  font-size: 10px;
  font-weight: 500;
  color: var(--faint, #97808a);
}

.rule-hit-detail {
  margin: 2px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--muted, #63474f);
  word-break: break-word;
}

.rule-pass {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 11px 0 0;
  font-size: 12px;
  color: var(--summer, #3b9c80);
  font-weight: 600;
}
.aigc-evidence {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: var(--r-sm, 10px);
  border: 1px dashed var(--sakura, #e8628c);
  background: var(--sakura-wash, #fff0f5);
}

.aigc-evidence-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
}

.aigc-evidence-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--sakura-deep, #c93a63);
  letter-spacing: 0.02em;
}

.aigc-evidence-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin: 0;
}

.aigc-evidence-facts > div {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.aigc-evidence-facts dt {
  font-size: 10.5px;
  color: var(--faint, #97808a);
}

.aigc-evidence-facts dd {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.aigc-evidence-facts dd.is-warn {
  color: var(--autumn, #b5703c);
}

.aigc-evidence-facts dd.is-ok {
  color: var(--summer, #3b9c80);
}

.aigc-evidence-warning {
  margin: 8px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: #d03050;
}

.aigc-evidence-note {
  margin: 8px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--muted, #63474f);
}
</style>
