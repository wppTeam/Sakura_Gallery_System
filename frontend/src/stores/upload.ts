import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { uploadPhoto } from '../api/photo'
import type { AigcUploadDeclaration } from '../types/photo'

/** 投稿时的 AIGC 声明（法定要求，未选不允许提交） */
export interface AigcDeclarationState {
    /** null = 尚未选择，禁止提交 */
    declared: boolean | null
    model: string
    provider: string
    prompt: string
    promptPublic: boolean
    sourceWorkId: string
    faceSwap: boolean
    consentConfirmed: boolean
}

function createAigcState(): AigcDeclarationState {
    return {
        declared: null,
        model: '',
        provider: '',
        prompt: '',
        promptPublic: false,
        sourceWorkId: '',
        faceSwap: false,
        consentConfirmed: false,
    }
}


export interface FileItem {
    file: File
    preview: string | null
    status: 'pending' | 'uploading' | 'success' | 'error'
    progress: number
    errorMsg?: string
    // UUID for tracking identity if needed
    id: string
}

export const useUploadStore = defineStore('upload', () => {
    // State
    const fileList = ref<FileItem[]>([])
    const uploading = ref(false)
    const metadata = ref({
        season: null as string | null,
        category: null as string | null,
        campus: null as string | null,
        classifications: {} as Record<string, number | number[]>,
        description: null as string | null,
    })
    const aigc = ref<AigcDeclarationState>(createAigcState())

    // Getters
    const pendingCount = computed(() => {
        return fileList.value.filter(item => item.status === 'pending').length
    })

    const successCount = computed(() => {
        return fileList.value.filter(item => item.status === 'success').length
    })

    const errorCount = computed(() => {
        return fileList.value.filter(item => item.status === 'error').length
    })

    /** 图生图 / 换脸类：必须确认已获得被摄者书面同意（后端 400 校验） */
    const aigcConsentRequired = computed(() => {
        return aigc.value.declared === true && (aigc.value.faceSwap || aigc.value.sourceWorkId.trim() !== '')
    })

    /** 是否已满足 AIGC 法定声明要求，可用于提交 */
    const aigcDeclared = computed(() => aigc.value.declared !== null)
    const aigcReady = computed(() => {
        if (aigc.value.declared !== true) return aigc.value.declared === false
        return !aigcConsentRequired.value || aigc.value.consentConfirmed
    })

    const canUpload = computed(() => {
        return pendingCount.value > 0 && !uploading.value && aigcReady.value
    })

    // Actions
    function addFiles(files: File[]) {
        files.forEach(file => {
            // Create preview
            const reader = new FileReader()
            reader.onload = (e) => {
                const preview = e.target?.result as string
                fileList.value.push({
                    id: Math.random().toString(36).substr(2, 9),
                    file,
                    preview,
                    status: 'pending',
                    progress: 0,
                })
            }
            reader.readAsDataURL(file)
        })
    }

    function removeFile(index: number) {
        fileList.value.splice(index, 1)
    }

    function clearAll() {
        // Revoke object URLs if we used URL.createObjectURL (here we used dataURL so strict cleanup isn't as critical but good memory hygiene to reset)
        fileList.value = []
        metadata.value = {
            season: null,
            category: null,
            campus: null,
            classifications: {},
            description: null,
        }
        aigc.value = createAigcState()
        uploading.value = false
    }

    async function startUpload(messageApi: any) {
        if (uploading.value) return
        uploading.value = true

        const pendingFiles = fileList.value.filter(item => item.status === 'pending')

        // Upload one by one to avoid overwhelming server/browser
        // Also allows better progress tracking
        for (const item of pendingFiles) {
            // Check if we should stop? (optional feature for later)
            await uploadSingleFile(item)
        }

        uploading.value = false

        if (successCount.value === fileList.value.length) {
            if (messageApi) messageApi.success('全部上传成功！')
        } else {
            if (messageApi) messageApi.warning(`上传完成，成功 ${successCount.value} 张，失败 ${fileList.value.length - successCount.value} 张`)
        }
    }

    /** 组装上传用 AIGC 声明（选「否」时只发 declared=false，不夹带 AI 字段） */
    function toAigcPayload(): AigcUploadDeclaration {
        const state = aigc.value
        if (state.declared !== true) {
            return { declared: false }
        }
        return {
            declared: true,
            model: state.model.trim() || undefined,
            provider: state.provider.trim() || undefined,
            prompt: state.prompt.trim() || undefined,
            promptPublic: state.promptPublic,
            sourceWorkId: state.sourceWorkId.trim() || undefined,
            faceSwap: state.faceSwap,
            consentConfirmed: state.consentConfirmed,
        }
    }

    // 取消「是」或取消图生图/换脸时，清掉不再需要的同意勾选，避免误提交
    watch(
        () => [aigc.value.declared, aigc.value.faceSwap, aigc.value.sourceWorkId],
        () => {
            if (aigc.value.declared !== true || !(aigc.value.faceSwap || aigc.value.sourceWorkId.trim())) {
                if (!aigcConsentRequired.value) aigc.value.consentConfirmed = false
            }
        },
    )

    async function uploadSingleFile(item: FileItem) {
        item.status = 'uploading'
        item.progress = 0

        try {
            const metadataToSend: any = {}
            if (metadata.value.season) metadataToSend.season = metadata.value.season
            if (metadata.value.category) metadataToSend.category = metadata.value.category
            if (metadata.value.campus) metadataToSend.campus = metadata.value.campus
            if (Object.keys(metadata.value.classifications).length) {
                metadataToSend.classifications = metadata.value.classifications
            }
            if (metadata.value.description) metadataToSend.description = metadata.value.description
            metadataToSend.aigc = toAigcPayload()

            // Pass progress callback
            await uploadPhoto(item.file, metadataToSend, (progressEvent: any) => {
                if (progressEvent.total) {
                    const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total)
                    item.progress = percentCompleted
                }
            })

            item.progress = 100
            item.status = 'success'
        } catch (error: any) {
            item.status = 'error'
            item.progress = 0
            item.errorMsg = error?.response?.data?.detail || '上传失败'
        }
    }

    async function retryUpload(index: number) {
        const item = fileList.value[index]
        if (item && item.status === 'error') {
            item.status = 'pending'
            item.errorMsg = undefined
            // If we are not currently global uploading, just upload this one
            if (!uploading.value) {
                uploading.value = true
                await uploadSingleFile(item)
                uploading.value = false
            } else {
                // If already uploading loop, just mark as pending and the loop (if implemented to pick up new pending) or next start will pick it up
                // Since our loop only picked "pendingFiles" at start, we might need to manually trigger this one.
                // Simple approach: just upload it now.
                await uploadSingleFile(item)
            }
        }
    }

    return {
        fileList,
        uploading,
        metadata,
        aigc,
        aigcDeclared,
        aigcReady,
        aigcConsentRequired,
        pendingCount,
        successCount,
        errorCount,
        canUpload,
        addFiles,
        removeFile,
        clearAll,
        startUpload,
        retryUpload
    }
})
