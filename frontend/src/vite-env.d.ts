/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "true" enables the bundled demo auto-login. Off unless a build opts in. */
  readonly VITE_AUTO_DEMO_LOGIN?: string;
  /** Demo credentials, injected at build time — never literals in the source. */
  readonly VITE_DEMO_EMAIL?: string;
  readonly VITE_DEMO_PASSWORD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
