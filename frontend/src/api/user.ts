/**
 * 当前登录用户相关 API（自助服务）
 *
 * 与 `users.ts`（管理员用户管理）区分：这里只操作「自己」的账号。
 */
import request from './index'

export interface DeleteAccountPayload {
  /** 当前密码，用于二次确认身份（绝不写入日志 / URL / localStorage） */
  password: string
  /** 确认词，必须精确为「注销」 */
  confirm: string
}

/**
 * 自助注销账号（不可恢复）。
 *
 * 成功返回 204 No Content；后端会在单个事务内删除账号及其全部内容，
 * 之后当前 token 立即失效。
 */
export async function deleteAccount(payload: DeleteAccountPayload): Promise<void> {
  await request.delete('/api/v1/user/account', {
    data: payload,
    // 删除涉及文件资产清理，给足超时
    timeout: 60000,
  })
}

/** 上传公开头像（multipart）。后端裁方缩到 512 WebP。 */
export async function uploadAvatar(file: File): Promise<{ avatar_path: string | null }> {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: '/api/v1/user/avatar',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30000,
  })
}

export async function deleteAvatar(): Promise<void> {
  await request.delete('/api/v1/user/avatar')
}

/** 公开头像 URL（无头像返回 null）。 */
export function avatarUrlOf(user: { id?: string; avatar_path?: string | null } | null | undefined): string | null {
  if (!user?.id || !user.avatar_path) return null
  return `/api/v1/user/avatar/${user.id}`
}
