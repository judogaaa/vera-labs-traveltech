import { readStorage, removeStorage, writeStorage, STORAGE_KEYS } from '../lib/storage'

export type AuthUser = {
  id: string
  name: string
  email: string
}

export type AuthSession = {
  user: AuthUser
  createdAt: string
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function getSession(): AuthSession | null {
  return readStorage<AuthSession | null>(STORAGE_KEYS.auth, null)
}

export async function login(email: string, password: string): Promise<AuthSession> {
  await delay(700)
  if (!email.includes('@') || password.length < 6) {
    throw new Error('Проверьте email и пароль')
  }
  const existing = getSession()
  const session: AuthSession = {
    user: {
      id: existing?.user.id ?? `user-${Date.now()}`,
      name: existing?.user.name ?? email.split('@')[0],
      email,
    },
    createdAt: new Date().toISOString(),
  }
  writeStorage(STORAGE_KEYS.auth, session)
  return session
}

export async function register(payload: {
  name: string
  email: string
  password: string
}): Promise<AuthSession> {
  await delay(800)
  if (!payload.name.trim() || !payload.email.includes('@') || payload.password.length < 6) {
    throw new Error('Проверьте данные регистрации')
  }
  const session: AuthSession = {
    user: {
      id: `user-${Date.now()}`,
      name: payload.name.trim(),
      email: payload.email.trim(),
    },
    createdAt: new Date().toISOString(),
  }
  writeStorage(STORAGE_KEYS.auth, session)
  return session
}

export async function requestPasswordReset(email: string): Promise<void> {
  await delay(600)
  if (!email.includes('@')) throw new Error('Укажите корректный email')
}

export function logout(): void {
  removeStorage(STORAGE_KEYS.auth)
}
