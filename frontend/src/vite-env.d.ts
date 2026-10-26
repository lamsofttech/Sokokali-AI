/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Sokokali API. Empty (default) = same origin, via the Vite dev proxy. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
