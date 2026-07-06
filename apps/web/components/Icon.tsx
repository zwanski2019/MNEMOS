import {
  ArrowUp,
  Bot,
  Braces,
  Building2,
  Calendar,
  CalendarDays,
  ChartPie,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Circle,
  CircleCheck,
  CirclePlay,
  Cloud,
  Code,
  CornerDownRight,
  CreditCard,
  Database,
  Download,
  FileText,
  Globe,
  Hexagon,
  History,
  Info,
  LayoutDashboard,
  Lightbulb,
  List,
  ListFilter,
  Lock,
  MemoryStick,
  Network,
  Orbit,
  Pause,
  Plus,
  RadioTower,
  RefreshCw,
  Regex,
  Save,
  ScrollText,
  Search,
  SearchCheck,
  Server,
  Settings,
  Shield,
  ShieldCheck,
  ShieldX,
  SquarePen,
  SquarePlus,
  Tag,
  Target,
  Terminal,
  Trash2,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";

// Material Symbol name -> Lucide component. The keys are the icon strings the
// pages already pass around (from Stitch exports), so call sites migrate by
// swapping <span className="material-symbols-outlined">name</span> for
// <Icon name="name" />. Add a row here when a new icon name is introduced.
const ICONS: Record<string, LucideIcon> = {
  add: Plus,
  add_box: SquarePlus,
  arrow_upward: ArrowUp,
  calendar_today: Calendar,
  check: Check,
  check_circle: CircleCheck,
  chevron_left: ChevronLeft,
  chevron_right: ChevronRight,
  close: X,
  cloud: Cloud,
  code: Code,
  dashboard: LayoutDashboard,
  data_object: Braces,
  database: Database,
  delete: Trash2,
  description: FileText,
  dns: Server,
  domain: Building2,
  download: Download,
  edit_note: SquarePen,
  event: CalendarDays,
  expand_less: ChevronUp,
  expand_more: ChevronDown,
  filter_list: ListFilter,
  gpp_bad: ShieldX,
  history: History,
  history_edu: ScrollText,
  info: Info,
  lan: Network,
  label: Tag,
  lightbulb: Lightbulb,
  list_alt: List,
  memory: MemoryStick,
  pause: Pause,
  payments: CreditCard,
  pie_chart: ChartPie,
  play_circle: CirclePlay,
  policy: Shield,
  public: Globe,
  regular_expression: Regex,
  save: Save,
  search: Search,
  search_check: SearchCheck,
  security: ShieldCheck,
  sensors: RadioTower,
  settings: Settings,
  smart_toy: Bot,
  subdirectory_arrow_right: CornerDownRight,
  sync: RefreshCw,
  tag: Tag,
  target: Target,
  terminal: Terminal,
  token: Hexagon,
  trip_origin: Orbit,
  vpn_lock: Lock,
  warning: TriangleAlert,
};

export type IconName = keyof typeof ICONS;

type IconProps = {
  name: string;
  className?: string;
  /** Solid fill for active/selected states (mirrors the old `.fill` variant). */
  filled?: boolean;
  strokeWidth?: number;
  /** Set when the icon is the only content of an interactive element. */
  title?: string;
};

/**
 * Renders a Lucide SVG sized to the current font-size (1em), so existing
 * `text-sm` / `text-[28px]` sizing classes keep controlling icon size and
 * `text-*` color classes keep controlling color via `currentColor`.
 * Decorative by default (aria-hidden); pass `title` for standalone icons.
 */
export function Icon({ name, className, filled, strokeWidth, title }: IconProps) {
  const Glyph = ICONS[name] ?? Circle;
  if (process.env.NODE_ENV !== "production" && !ICONS[name]) {
    console.warn(`[Icon] no mapping for "${name}" — add it to components/Icon.tsx`);
  }
  return (
    <Glyph
      className={className}
      style={{ width: "1em", height: "1em" }}
      strokeWidth={strokeWidth ?? 2}
      fill={filled ? "currentColor" : "none"}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      role={title ? "img" : undefined}
      focusable={false}
    />
  );
}
