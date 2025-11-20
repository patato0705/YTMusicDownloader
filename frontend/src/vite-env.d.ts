interface ImportMetaEnv {
  VITE_API_BASE: string
  readonly VITE_BACKEND_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
