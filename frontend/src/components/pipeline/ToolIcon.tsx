'use client';

import {
  Download,
  FileSearch,
  Settings,
  Crop,
  Image,
  Music,
  AudioLines,
  MessageSquare,
  Languages,
  Mic,
  Sliders,
  RefreshCw,
  Subtitles,
  Type,
  Sparkles,
  Stamp,
  Package,
  CheckCircle,
  HelpCircle,
  LucideIcon,
  Gauge,
  Scissors,
  Copy,
} from 'lucide-react';

const ICON_MAP: Record<string, LucideIcon> = {
  Download,
  FileSearch,
  Settings,
  Crop,
  Image,
  Music,
  AudioLines,
  MessageSquare,
  Languages,
  Mic,
  Sliders,
  RefreshCw,
  Subtitles,
  Type,
  Sparkles,
  Stamp,
  Package,
  CheckCircle,
  Gauge,
  Scissors,
  Copy,
};

interface ToolIconProps {
  icon: string;
  size?: number;
  color?: string;
  className?: string;
}

export function ToolIcon({ icon, size = 20, color, className }: ToolIconProps) {
  const IconComponent = ICON_MAP[icon] || HelpCircle;
  return <IconComponent size={size} color={color} className={className} />;
}

export default ToolIcon;
