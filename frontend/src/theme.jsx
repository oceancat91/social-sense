/**
 * 主题模块：界面按钮手动切换深浅色，不跟随系统。
 *
 * - 用户选择记忆在 localStorage（key: ss-theme），默认深色（情报中枢默认态）。
 * - CSS 变量由 global.css 基于 <html data-theme="dark|light"> 提供；
 * - antd ConfigProvider 通过 ThemeContext 同步 dark/light，注入统一语义色 token。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { ConfigProvider, theme as antdTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'

const STORAGE_KEY = 'ss-theme'

/** 琥珀强调色（情报中枢主色；深色高饱和、浅色深琥珀保证对比） */
export const ACCENT = {
  light: '#B45309',
  dark: '#E7A23D',
}

// 语义色（两端主题），供 antd token 与图表/标签复用
export const SEMANTIC = {
  success: { light: '#15803D', dark: '#3ECF8E' },
  warning: { light: '#B45309', dark: '#E7A23D' },
  danger: { light: '#B91C1C', dark: '#F26B5E' },
  info: { light: '#1D4ED8', dark: '#7DA7F5' },
}

const pick = (obj, dark) => obj[dark ? 'dark' : 'light']

function buildToken(dark) {
  const accent = pick(ACCENT, dark)
  return {
    colorPrimary: accent,
    colorInfo: accent,
    colorLink: accent,
    colorLinkHover: dark ? '#F0B45A' : '#92400E',
    // 主按钮文字色：浅色用白、深色琥珀按钮用近黑保证对比
    colorTextLightSolid: dark ? '#211505' : '#FFFFFF',
    colorSuccess: pick(SEMANTIC.success, dark),
    colorWarning: pick(SEMANTIC.warning, dark),
    colorError: pick(SEMANTIC.danger, dark),
    borderRadius: 6,
    borderRadiusSM: 4,
    fontSize: 14,
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
    colorBgLayout: dark ? '#0A0C0E' : '#EFEDE7',
    colorBgContainer: dark ? '#12151A' : '#FFFFFF',
    colorBgElevated: dark ? '#171B21' : '#FFFFFF',
    colorBorder: dark ? '#262D34' : '#E0DDD5',
    colorBorderSecondary: dark ? '#1A2026' : '#ECEAE3',
    colorText: dark ? '#E9EBEC' : '#1B1E22',
    colorTextSecondary: dark ? '#A5ACB3' : '#5B6269',
    colorTextTertiary: dark ? '#707983' : '#8A9097',
    colorTextQuaternary: dark ? '#4A515A' : '#B4B8BC',
    colorFillQuaternary: dark ? '#0F1216' : '#F7F5F1',
    colorFillTertiary: dark ? '#151A1F' : '#F0EEE8',
    colorFillSecondary: dark ? '#1C222A' : '#E9E6DF',
    colorFill: dark ? '#232A33' : '#DFDCD4',
    colorBgTextHover: dark ? '#1A2027' : '#EFEDE7',
  }
}

/** 同步 data-theme + colorScheme 到 html 根元素 */
function applyRootTheme(mode) {
  const root = document.documentElement
  root.setAttribute('data-theme', mode)
  root.style.colorScheme = mode
}

function readInitial() {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark') return v
  } catch {
    /* ignore */
  }
  return 'dark'
}

/** 供组件读取当前主题状态与切换函数 */
export const ThemeContext = createContext({ dark: true, mode: 'dark', toggle: () => {} })
export const useDarkMode = () => useContext(ThemeContext).dark
export const useTheme = () => useContext(ThemeContext)

/** 主题外壳：默认深色；手动切换并记忆 */
export function ThemeGate({ children }) {
  const [mode, setMode] = useState(readInitial)
  const dark = mode === 'dark'

  useEffect(() => {
    applyRootTheme(mode)
  }, [mode])

  const toggle = useCallback(() => {
    setMode((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark'
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  const value = useMemo(() => ({ dark, mode, toggle }), [dark, mode, toggle])
  const token = buildToken(dark)

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
          token,
          components: {
            Card: {
              headerFontSize: 14,
              headerBg: 'transparent',
              headerHeight: 48,
            },
            Layout: {
              headerBg: dark ? '#0A0C0E' : '#EFEDE7',
              headerHeight: 56,
              headerPadding: '0 24px',
            },
            Table: {
              headerBg: dark ? '#151A1F' : '#F4F2ED',
              rowHoverBg: dark ? '#191F26' : '#F5F3EE',
              headerColor: dark ? '#9AA3AB' : '#5B6269',
            },
            Menu: {
              darkItemBg: 'transparent',
              darkItemSelectedBg: dark ? 'rgba(231,162,61,0.12)' : 'rgba(180,83,9,0.10)',
              darkItemSelectedColor: dark ? '#E7A23D' : '#B45309',
              darkItemHoverColor: dark ? '#E7A23D' : '#B45309',
              darkItemColor: dark ? '#9AA3AB' : '#5B6269',
              itemSelectedBg: 'rgba(180,83,9,0.10)',
              itemSelectedColor: '#B45309',
              itemBorderRadius: 6,
              itemHeight: 40,
            },
            Tooltip: {
              colorBgSpotlight: dark ? '#1C222A' : '#33383F',
            },
            Segmented: {
              itemSelectedBg: dark ? '#1C222A' : '#FFFFFF',
            },
          },
        }}
      >
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  )
}

export default ThemeGate
