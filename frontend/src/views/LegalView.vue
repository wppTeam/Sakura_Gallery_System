<template>
  <main class="legal-page">
    <div class="wrap legal-shell">
      <nav class="legal-crumb" aria-label="面包屑">
        <RouterLink to="/">首页</RouterLink>
        <span aria-hidden="true">/</span>
        <span class="crumb-current">{{ page.title }}</span>
      </nav>

      <header class="legal-head">
        <p class="legal-eyebrow">{{ page.eyebrow }}</p>
        <h1 class="legal-title">{{ page.title }}</h1>
        <p class="legal-meta">
          最后更新 <time datetime="2026-11-25">2026-11-25</time>
          <span aria-hidden="true">·</span>
          本页为当前生效文本
        </p>
      </header>

      <div class="legal-grid">
        <nav class="legal-toc" aria-label="章节导航">
          <p class="toc-title">目录</p>
          <a
            v-for="section in page.sections"
            :key="section.id"
            class="toc-link"
            :href="`#${section.id}`"
            @click.prevent="jumpTo(section.id)"
          >
            {{ section.title }}
          </a>
          <p class="toc-cross">
            <RouterLink :to="crossLink.to">{{ crossLink.label }}</RouterLink>
          </p>
        </nav>

        <article class="legal-body">
          <section
            v-for="section in page.sections"
            :id="section.id"
            :key="section.id"
            class="legal-section"
          >
            <h2 class="section-title">{{ section.title }}</h2>
            <p v-for="(paragraph, index) in section.paragraphs" :key="index" class="section-p">
              {{ paragraph }}
            </p>
            <p v-if="section.contact" class="section-p section-contact">
              联系方式：<a href="mailto:hello@buct-sakura.cn">hello@buct-sakura.cn</a>
            </p>
          </section>

          <footer class="legal-foot">
            <p>
              如对本页内容有疑问，或需要行使你的权利，请联系
              <a href="mailto:hello@buct-sakura.cn">hello@buct-sakura.cn</a>。
            </p>
            <div class="legal-foot-actions">
              <RouterLink :to="crossLink.to" class="foot-cross">{{ crossLink.label }} →</RouterLink>
              <button type="button" class="foot-top" @click="backToTop">回到顶部 ↑</button>
            </div>
          </footer>
        </article>
      </div>
    </div>

    <Transition name="backtop">
      <button
        v-if="showBackTop"
        type="button"
        class="back-to-top"
        aria-label="回到顶部"
        @click="backToTop"
      >
        <n-icon :component="ArrowUpOutline" :size="20" />
      </button>
    </Transition>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ArrowUpOutline } from '@vicons/ionicons5'

interface LegalSection {
  id: string
  title: string
  paragraphs: string[]
  contact?: boolean
}

interface LegalPage {
  eyebrow: string
  title: string
  sections: LegalSection[]
}

const TERMS: LegalPage = {
  eyebrow: 'TERMS OF SERVICE',
  title: '服务条款',
  sections: [
    {
      id: 'platform',
      title: '平台性质',
      paragraphs: [
        '视觉百花 Sakura Gallery 是北化学生自建、非商业的开源创作资源共享平台，仅提供信息存储空间与展示服务；作品由用户上传，上传者对其内容负责。',
      ],
    },
    {
      id: 'account',
      title: '账号',
      paragraphs: [
        '注册需使用真实可用的邮箱并完成邮箱验证；请勿转让账号或批量注册；可随时申请注销。',
      ],
    },
    {
      id: 'content-license',
      title: '内容与授权',
      paragraphs: [
        '上传者须拥有作品著作权或合法授权；未获被摄者同意的人像作品不得公开，涉人像内容默认按站点规则脱敏展示；用户授予平台非独占、免费、可转授权的展示与分发许可（用于站内展示、分享卡、缩略图与缓存），删除作品后该许可终止（已分发或已缓存的部分除外）。',
      ],
    },
    {
      id: 'aigc',
      title: 'AI 生成内容',
      paragraphs: [
        '必须如实声明；平台依法添加显式与隐式标识；图生图、换脸等须获得被摄者书面同意；违法违规或侵权内容将被下架。',
      ],
    },
    {
      id: 'forbidden',
      title: '禁止内容',
      paragraphs: ['违反法律法规、侵犯他人权利、虚假信息、垃圾广告、恶意程序等。'],
    },
    {
      id: 'complaints',
      title: '侵权投诉',
      paragraphs: [
        '可在作品/专题页通过「举报 / 侵权投诉」提交；平台按「通知—删除」规则处理，必要时要求补充权属证明；恶意投诉将承担相应责任。',
      ],
    },
    {
      id: 'disclaimer',
      title: '免责',
      paragraphs: [
        '平台按现状提供；因不可抗力或第三方服务（对象存储、CDN、邮件、AI 服务）故障造成的损失不承担赔偿责任。',
      ],
    },
    {
      id: 'changes',
      title: '变更与终止',
      paragraphs: ['条款变更将在本页公示后生效；严重违规可限制或封禁账号。'],
    },
    {
      id: 'contact',
      title: '联系方式',
      paragraphs: [],
      contact: true,
    },
  ],
}

const PRIVACY: LegalPage = {
  eyebrow: 'PRIVACY POLICY',
  title: '隐私政策',
  sections: [
    {
      id: 'collection',
      title: '我们收集',
      paragraphs: [
        '账号信息（学号/用户名/邮箱、密码哈希）、发布内容与元数据（EXIF 入库前剥离 GPS 与个人信息，仅保留相机与曝光等展示参数）、互动数据（收藏、聚合浏览计数）、安全日志（IP、UA、登录时间，用于风控、审计与故障排查）。',
      ],
    },
    {
      id: 'purpose',
      title: '使用目的',
      paragraphs: [
        '提供登录、发布、检索、审核与分享功能；保障账号与站点安全；AI 辅助审核与打标（待审图片会发送至第三方 AI 模型服务用于内容安全判定与标签生成，不会公开你的私有元数据）。',
      ],
    },
    {
      id: 'portrait',
      title: '人像与敏感内容',
      paragraphs: [
        '默认不进入公共列表，对外仅展示脱敏版本；原图与下载仅作者本人与审核员可见。',
      ],
    },
    {
      id: 'retention',
      title: '存储与保留',
      paragraphs: [
        '作品媒体存储于腾讯云 COS（中国境内）；审核与审计日志保留 180 天；注销后 30 天内删除账号与内容（法律法规要求保留的除外）。',
      ],
    },
    {
      id: 'third-party',
      title: '第三方服务',
      paragraphs: [
        '腾讯云 COS（媒体存储）、Cloudflare（CDN 与隧道）、Resend（邮件发送）、AI 模型服务（审核/打标/搜索理解）。',
      ],
    },
    {
      id: 'cookies',
      title: 'Cookie 与本地存储',
      paragraphs: ['仅保存登录态与界面偏好（如搜索历史、人像开关），不做广告追踪。'],
    },
    {
      id: 'rights',
      title: '你的权利',
      paragraphs: ['访问、更正、删除个人数据与注销账号；通过 hello@buct-sakura.cn 联系我们。'],
    },
    {
      id: 'minors',
      title: '未成年人',
      paragraphs: [
        '请在监护人同意后使用；涉及未成年人的肖像内容同样适用人像规则。',
      ],
    },
    {
      id: 'changes',
      title: '变更',
      paragraphs: ['政策更新将在本页公示。'],
    },
  ],
}

const route = useRoute()
const kind = computed<'terms' | 'privacy'>(() =>
  route.path.startsWith('/privacy') ? 'privacy' : 'terms',
)
const page = computed<LegalPage>(() => (kind.value === 'privacy' ? PRIVACY : TERMS))
const crossLink = computed(() =>
  kind.value === 'privacy'
    ? { to: '/terms', label: '服务条款' }
    : { to: '/privacy', label: '隐私政策' },
)

const showBackTop = ref(false)

function updateBackTop() {
  showBackTop.value = window.scrollY > window.innerHeight * 1.6
}

function scrollBehavior(): ScrollBehavior {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

function jumpTo(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: scrollBehavior(), block: 'start' })
}

function backToTop() {
  window.scrollTo({ top: 0, behavior: scrollBehavior() })
}

watch(
  () => route.path,
  () => {
    window.scrollTo({ top: 0, behavior: 'auto' })
    showBackTop.value = false
  },
)

onMounted(() => {
  window.addEventListener('scroll', updateBackTop, { passive: true })
  updateBackTop()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateBackTop)
})
</script>

<style scoped>
.legal-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 7vw, 96px);
  background:
    radial-gradient(900px 420px at 92% -6%, var(--sakura-wash), transparent 62%),
    var(--ground);
}

.legal-shell {
  max-width: calc(var(--maxw) + var(--margin) * 2);
}

.legal-crumb {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12.5px;
  color: var(--faint);
}

.legal-crumb a {
  color: var(--muted);
}

.legal-crumb a:hover {
  color: var(--sakura-deep);
}

.crumb-current {
  color: var(--ink-soft);
}

.legal-head {
  padding: clamp(18px, 3vw, 32px) 0 clamp(26px, 3.4vw, 40px);
  border-bottom: 1px solid var(--line);
}

.legal-eyebrow {
  margin: 0 0 10px;
  font-size: 11px;
  letter-spacing: 0.16em;
  font-weight: 600;
  color: var(--sakura-deep);
}

.legal-title {
  margin: 0;
  font-family: var(--display);
  font-size: clamp(40px, 5vw, 64px);
  font-weight: 400;
  line-height: var(--lh-tight);
  letter-spacing: 0.02em;
  color: var(--ink);
}

.legal-meta {
  margin: 12px 0 0;
  font-size: 12.5px;
  color: var(--faint);
}

.legal-meta span {
  margin: 0 8px;
}

.legal-grid {
  display: grid;
  grid-template-columns: minmax(0, 200px) minmax(0, 72em);
  gap: clamp(26px, 4vw, 64px);
  align-items: start;
  padding-top: clamp(26px, 3.4vw, 44px);
}

.legal-toc {
  position: sticky;
  top: calc(var(--nav-h) + 24px);
  display: grid;
  gap: 2px;
  align-content: start;
}

.toc-title {
  margin: 0 0 10px;
  font-size: 11px;
  letter-spacing: 0.14em;
  font-weight: 600;
  color: var(--faint);
}

.toc-link {
  display: block;
  padding: 6px 10px;
  border-left: 2px solid transparent;
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted);
}

.toc-link:hover {
  color: var(--sakura-deep);
  background: var(--sakura-wash);
  border-left-color: var(--sakura);
}

.toc-link:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.38));
  outline-offset: 2px;
}

.toc-cross {
  margin: 18px 0 0;
  padding-top: 14px;
  border-top: 1px dashed var(--line-strong);
  font-size: 12.5px;
}

.toc-cross a {
  color: var(--sakura-deep);
}

.legal-body {
  max-width: 72em;
  color: var(--ink);
  font-size: 15px;
  line-height: var(--lh-body);
}

.legal-section {
  scroll-margin-top: calc(var(--nav-h) + 24px);
  padding-bottom: clamp(20px, 2.6vw, 30px);
  margin-bottom: clamp(20px, 2.6vw, 30px);
  border-bottom: 1px solid var(--line);
}

.legal-section:last-of-type {
  border-bottom: 0;
}

.section-title {
  margin: 0 0 10px;
  font-family: var(--font);
  font-size: 20px;
  font-weight: 700;
  line-height: 1.4;
  color: var(--ink);
}

.section-p {
  margin: 0 0 12px;
  max-width: 36em;
  color: var(--ink-soft);
}

.section-p:last-child {
  margin-bottom: 0;
}

.section-contact a,
.legal-foot a {
  color: var(--sakura-deep);
  text-decoration: underline;
  text-underline-offset: 0.18em;
}

.legal-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 28px;
  justify-content: space-between;
  align-items: center;
  padding-top: 22px;
  border-top: 1px dashed var(--line-strong);
  font-size: 13px;
  color: var(--muted);
}

.legal-foot p {
  margin: 0;
  max-width: 34em;
  line-height: 1.8;
}

.legal-foot-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}

.foot-cross {
  color: var(--sakura-deep);
  font-weight: 600;
}

.foot-top {
  border: 0;
  background: none;
  padding: 6px 8px;
  border-radius: var(--r-pill);
  color: var(--sakura-deep);
  font-size: 13px;
  cursor: pointer;
}

.foot-top:hover {
  background: var(--sakura-wash);
}

.foot-top:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.38));
  outline-offset: 2px;
}

.back-to-top {
  position: fixed;
  right: 22px;
  bottom: 26px;
  z-index: var(--z-sticky, 30);
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  background: var(--surface);
  color: var(--sakura-deep);
  box-shadow: var(--shadow-soft);
  cursor: pointer;
}

.back-to-top:hover {
  background: var(--sakura-pale);
}

.back-to-top:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.38));
  outline-offset: 3px;
}

.backtop-enter-active,
.backtop-leave-active {
  transition: opacity var(--dur) var(--ease-out), transform var(--dur) var(--ease-out);
}

.backtop-enter-from,
.backtop-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 900px) {
  .legal-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 22px;
  }

  .legal-toc {
    position: static;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }

  .toc-title {
    width: 100%;
    margin-bottom: 2px;
  }

  .toc-link {
    border: 1px solid var(--line);
    border-radius: var(--r-pill);
    padding: 5px 11px;
    background: var(--surface);
  }

  .toc-cross {
    width: 100%;
    margin-top: 6px;
    padding-top: 8px;
  }
}

@media (max-width: 560px) {
  .legal-title {
    font-size: clamp(34px, 9vw, 44px);
  }

  .legal-body {
    font-size: 14.5px;
  }

  .back-to-top {
    right: 14px;
    bottom: 18px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .backtop-enter-active,
  .backtop-leave-active {
    transition: none;
  }
}
</style>
