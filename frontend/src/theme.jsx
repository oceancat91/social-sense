/**
 * 主题模块：跟随系统深浅色（prefers-color-scheme），不提供手动切换。
 *
 * - 深浅色由操作系统决定，实时监听系统变化自动切换；
 * - antd ConfigProvider 的 dark/light algorithm 与图表组件均通过
 *   ThemeContext 读取当前 mode；
 * - CSS 变量由 global.css 基于 @media (prefers-color-scheme) 提供，
 *   与 landing 营销页共用同一套中性冷灰 + 克制深蓝语义。
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { ConfigProvider, theme as antdTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'

/** 克制深蓝强调色（全站唯一 accent；浅色深蓝、深色亮蓝保证对比） */
export const ACCENT = {
  light: '#2563EB',
  dark: '#3B82F6',
}

// 语义色（两端主题），供 antd token 与图表/标签复用
export const SEMANTIC = {
  success: { light: '#15803D', dark: '#3ECF8E' },
  warning: { light: '#D97706', dark: '#F0A63F' },
  danger: { light: '#B91C1C', dark: '#F26B5E' },
  info: { light: '#2563EB', dark: '#7DA7F5' },
}

const pick = (obj, dark) => obj[dark ? 'dark' : 'light']

function getSystemDark() {
  if (typeof window === 'undefined') return true
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true
}

function buildToken(dark) {
  const accent = pick(ACCENT, dark)
  return {
    colorPrimary: accent,
    colorInfo: accent,
    colorLink: accent,
    colorLinkHover: dark ? '#60A5FA' : '#1E40AF',
    // 按钮文字色：浅色蓝底白字；深色亮蓝底用深字保证 WCAG 对比
    colorTextLightSolid: dark ? '#0B0F18' : '#FFFFFF',
    colorSuccess: pick(SEMANTIC.success, dark),
    colorWarning: pick(SEMANTIC.warning, dark),
    colorError: pick(SEMANTIC.danger, dark),
    // 圆角分档：控件/输入/标签 6px（landing rounded-md），大卡 12px 见 Card 组件覆盖
    borderRadius: 6,
    borderRadiusSM: 6,
    borderRadiusLG: 12,
    fontSize: 14,
    fontFamily:
      "Inter Variable, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
    fontFamilyCode:
      "JetBrains Mono Variable, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    colorBgLayout: dark ? '#0A0D13' : '#F5F6F8',
    colorBgContainer: dark ? '#12161F' : '#FDFDFE',
    colorBgElevated: dark ? '#1A2030' : '#FFFFFF',
    colorBorder: dark ? '#222A3A' : '#E6E9EE',
    colorBorderSecondary: dark ? '#1B2130' : '#EEF0F4',
    colorText: dark ? '#EDF0F5' : '#191D25',
    colorTextSecondary: dark ? '#A8B1C0' : '#4C5665',
    colorTextTertiary: dark ? '#7E8899' : '#5B6675',
    colorTextQuaternary: dark ? '#566174' : '#A9B3C2',
    colorFillQuaternary: dark ? '#12161F' : '#F7F8FA',
    colorFillTertiary: dark ? '#1A2030' : '#F0F2F5',
    colorFillSecondary: dark ? '#222A3A' : '#E8EBF0',
    colorFill: dark ? '#2A3446' : '#DEE2EA',
    colorBgTextHover: dark ? '#1A2030' : '#F0F2F5',
  }
}

/** 供组件读取当前系统深浅状态 */
export const ThemeContext = createContext({ dark: true, mode: 'dark' })
export const useDarkMode = () => useContext(ThemeContext).dark
export const useTheme = () => useContext(ThemeContext)

/** 主题外壳：跟随系统深浅，自动切换 antd algorithm */
export function ThemeGate({ children }) {
  const [dark, setDark] = useState(getSystemDark)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e) => setDark(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  }, [dark])

  const mode = dark ? 'dark' : 'light'
  const value = useMemo(() => ({ dark, mode }), [dark, mode])
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
              borderRadiusLG: 12,
            },
            Layout: {
              headerBg: dark ? '#0A0D13' : '#F5F6F8',
              headerHeight: 64,
              headerPadding: '0 24px',
            },
            Table: {
              headerBg: dark ? '#1A2030' : '#F0F2F5',
              rowHoverBg: dark ? '#1B2130' : '#F5F6F8',
              headerColor: dark ? '#A8B1C0' : '#5B6675',
            },
            Menu: {
              darkItemBg: 'transparent',
              darkItemSelectedBg: dark ? 'rgba(59,130,246,0.14)' : 'rgba(37,99,235,0.10)',
              darkItemSelectedColor: dark ? '#3B82F6' : '#1E40AF',
              darkItemHoverColor: dark ? '#60A5FA' : '#1E40AF',
              darkItemColor: dark ? '#A8B1C0' : '#5B6675',
              itemSelectedBg: 'rgba(37,99,235,0.10)',
              itemSelectedColor: '#1E40AF',
              itemBorderRadius: 6,
              itemHeight: 40,
            },
            Tooltip: {
              colorBgSpotlight: dark ? '#1A2030' : '#33383F',
            },
            Segmented: {
              itemSelectedBg: dark ? '#1A2030' : '#FFFFFF',
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
