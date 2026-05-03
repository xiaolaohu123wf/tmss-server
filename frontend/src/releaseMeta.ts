import pkg from '../package.json'

interface PkgJsonShape {
  version: string
}

const { version: semver } = pkg as PkgJsonShape

/** package.json version，发布时请与仓库 Git tag（如 v1.1.3）同步 bump */
export const APP_SEMVER_VERSION = semver

/** 展示用 tag，前缀 v */
export const APP_VERSION_TAG = `v${semver}`
