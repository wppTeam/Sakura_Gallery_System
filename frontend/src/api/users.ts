/**
 * 用户管理 API
 * 
 * 仅限管理员使用。
 */
import request from './index'
import { normalizeAigcQuota } from './aigc'
import type {
    User,
    UserListResponse,
    UserCreateRequest,
    UserUpdateRequest,
    UserRole
} from '../types/user'

const BASE_URL = '/api/v1/admin/users'

/** 用户排序方式（与后端 admin users 接口保持一致） */
export type AdminUserSort =
    | 'created_at_desc'
    | 'created_at_asc'
    | 'last_login_desc'
    | 'login_count_desc'
    | 'student_id_asc'

export interface AdminUserQuery {
    skip?: number
    limit?: number
    search?: string
    role?: UserRole
    is_active?: boolean
    email_verified?: boolean
    sort?: AdminUserSort
}

/**
 * 获取用户列表
 */
export async function getUsers(params?: AdminUserQuery): Promise<UserListResponse> {
    return request({
        url: BASE_URL,
        method: 'get',
        params
    })
}

/**
 * 获取单个用户
 */
export async function getUser(userId: string): Promise<User> {
    return request.get(`${BASE_URL}/${userId}`)
}

/**
 * 创建用户
 */
export async function createUser(data: UserCreateRequest): Promise<User> {
    return request.post(BASE_URL, data)
}

/**
 * 更新用户
 */
export async function updateUser(userId: string, data: UserUpdateRequest): Promise<User> {
    return request.put(`${BASE_URL}/${userId}`, data)
}

/**
 * 修改用户角色
 */
export async function updateUserRole(userId: string, role: UserRole): Promise<User> {
    return request.put(`${BASE_URL}/${userId}/role`, { role })
}

/**
 * 删除用户
 */
export async function deleteUser(userId: string): Promise<void> {
    return request.delete(`${BASE_URL}/${userId}`)
}

/**
 * 重置用户密码（管理员）
 */
export async function resetUserPassword(userId: string, newPassword: string): Promise<{ success?: boolean; message?: string }> {
    return request.put(`${BASE_URL}/${userId}/password`, { new_password: newPassword })
}

/**
 * 标记用户邮箱已验证
 */
export async function verifyUserEmail(userId: string): Promise<User> {
    return request.post(`${BASE_URL}/${userId}/verify-email`)
}

/** 用户概览统计（管理端仪表盘 / 用户管理页顶部） */
export interface AdminUserStats {
    total: number
    active: number
    inactive: number
    admins: number
    auditors: number
    pending_approval: number
    email_unverified: number
    new_last_7_days: number
    recent_logins: Array<{
        id: string
        username: string | null
        display_name: string | null
        role: UserRole
        last_login_at: string | null
        login_count?: number
    }>
}

/**
 * 获取用户概览统计
 */
export async function getUserStats(): Promise<AdminUserStats> {
    return request.get(`${BASE_URL}/stats`)
}

/** 用户详情抽屉聚合（作品 / 生图额度 / 申诉举报 / 审计） */
export interface AdminUserDetail {
    user: User
    photos: { total: number; approved: number; pending: number; rejected: number; views: number }
    recent_photos: Array<{ id: string; title: string | null; status: string; views: number; thumb_url: string }>
    aigc: {
        quota: import('./aigc').AigcQuota
        generation_total: number
        grant_count: number
    }
    collections_count: number
    appeals: { pending: number; total: number }
    reports_pending: number
    recent_audit: Array<{ id: string; action: string; detail: string | null; created_at: string }>
}

export async function getUserDetail(userId: string): Promise<AdminUserDetail> {
    const raw = await request.get<Record<string, unknown>>(`${BASE_URL}/${encodeURIComponent(userId)}/detail`)
    const aigc = (raw.aigc ?? {}) as Record<string, unknown>
    return {
        ...(raw as unknown as AdminUserDetail),
        aigc: {
            quota: normalizeAigcQuota(aigc.quota),
            generation_total: Number(aigc.generation_total ?? 0),
            grant_count: Number(aigc.grant_count ?? 0),
        },
    }
}
