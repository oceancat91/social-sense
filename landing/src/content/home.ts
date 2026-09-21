import {
  ArrowLeftRight,
  BadgeCheck,
  Briefcase,
  ChartColumn,
  ChartLine,
  ChartPie,
  Funnel,
  Gauge,
  Globe,
  Lightbulb,
  Megaphone,
  Merge,
} from "lucide";

export const PRODUCT_URL = "https://socialsense.cn/app/";

export const CTA_CLASS =
  "cta-glass inline-flex items-center gap-2 rounded-md px-5 py-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export const NAV = [
  { href: "#method", label: "处理管线" },
  { href: "#capabilities", label: "能力" },
  { href: "#insights", label: "真实洞察" },
  { href: "#roles", label: "适用角色" },
  { href: "#faq", label: "常见问题" },
];

export const PLATFORMS = ["微博", "抖音", "B站", "小红书", "知乎", "快手"];

export const PIPELINE = [
  {
    icon: Globe,
    title: "采集",
    desc: "微博、抖音、B站、小红书、知乎、快手，六大平台的公开讨论一次接全。",
  },
  {
    icon: Funnel,
    title: "清洗",
    desc: "刷屏与机器噪声清干净，只留下真正有人在说的内容。",
  },
  {
    icon: ChartColumn,
    title: "画像",
    desc: "每条讨论的情绪与立场逐条读懂，每个平台都有独立画像。",
  },
  {
    icon: ArrowLeftRight,
    title: "对齐",
    desc: "把六个平台的节奏拉到同一根时间轴上，谁在共振一眼看清。",
  },
  {
    icon: BadgeCheck,
    title: "校准",
    desc: "输出前先过硬校验，没有证据支撑的判断不会出现在结果里。",
  },
];

export const CAPABILITIES = [
  {
    icon: Merge,
    title: "跨平台对齐与共振",
    desc: "各平台的计数方式天差地别，直接相加只会得到噪音。归一到同一把尺子后，声量与情绪才真正可比。",
    note: "谁在共振、谁在错峰，一眼可辨。",
  },
  {
    icon: ChartPie,
    title: "立场与情绪画像",
    desc: "每条讨论的情绪倾向与支持、反对、中立立场自动标注，每个平台都有一份清晰的画像。",
    note: "口径透明，结论随时可复算。",
  },
  {
    icon: Gauge,
    title: "回声室指数",
    desc: "把立场分歧、情绪分歧与声量失振合成一个数字，信息茧房到底有多厚，不用再靠感觉猜。",
    note: "只有过硬校验的读数，才会呈现在这里。",
  },
];

export const TOPICS = [
  "国潮与传统文化复兴",
  "房价下跌与楼市",
  "学历贬值与就业难",
  "AI艺人与活人感之争",
  "AI漫剧爆发",
  "青少年心理健康",
  "消费降级与反向消费",
  "极端天气与气候",
  "中美关税战",
  "戒网瘾双胞胎事件",
  "2026美加墨世界杯",
  "人形机器人商业化",
];

export const INSIGHTS = [
  { topic: "AI艺人与活人感之争", points: 3298, resonance: 0.24, echo: 0.28 },
  { topic: "人形机器人商业化", points: 3183, resonance: 0.21, echo: 0.26 },
  { topic: "消费降级与反向消费", points: 2923, resonance: 0.13, echo: 0.29 },
  { topic: "国潮与传统文化复兴", points: 2866, resonance: 0.05, echo: 0.32 },
];

export const ROLES = [
  {
    icon: Briefcase,
    title: "社区运营",
    desc: "更早发现危机拐点，处理时机不再滞后。",
  },
  {
    icon: Lightbulb,
    title: "产品经理",
    desc: "听见被单一平台淹没的真实呼声。",
  },
  {
    icon: ChartLine,
    title: "数据与增长分析师",
    desc: "口径一致的时间序列，拿来就能建模。",
  },
  {
    icon: Megaphone,
    title: "市场团队",
    desc: "用真实读数校准叙事与投放节奏。",
  },
];

export const GATES = [
  {
    name: "覆盖足够",
    desc: "单一平台不下跨平台结论。没有第二个平台佐证，就不做跨平台判断。",
  },
  {
    name: "分歧诚实",
    desc: "茧房该多厚就多厚，不夸大也不隐瞒，断言与读数必须一致。",
  },
  {
    name: "不编造平台",
    desc: "结论只会引用真实存在的平台数据，绝不凭空引用。",
  },
  {
    name: "句句有据",
    desc: "每条判断都绑定真实证据，点开就能看到出处。",
  },
  {
    name: "空白就留白",
    desc: "没有观测到的时间窗如实留空，绝不用估算值填补。",
  },
];

export const FAQS = [
  {
    q: "覆盖哪些平台？",
    a: "微博、抖音、B站、小红书、知乎、快手。六大平台的公开讨论一次接全，不用来回切换后台。",
  },
  {
    q: "不同平台的数据怎么比？",
    a: "先把各平台口径拉齐，再放到同一根时间轴上。这样得出的跨平台结果，才真正经得起比较。",
  },
  {
    q: "结论可信吗？",
    a: "每条结论都要先过硬校验。没有证据支撑的判断不会输出，缺失的时间窗如实留空。",
  },
  {
    q: "覆盖哪些领域？",
    a: "十二个领域热点持续追踪：文化历史、财经商业、教育科研、影视娱乐、游戏动漫、医疗健康、生活消费、自然环境、时政、社会事件、体育竞技、科技工业。",
  },
];
