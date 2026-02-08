'use client';

import { ToolIcon } from './ToolIcon';
import { ToolDefinition, CATEGORY_LABELS } from '@/lib/toolDefinitions';
import styles from './ToolCard.module.css';

interface ToolCardProps {
  tool: ToolDefinition;
  stepNumber?: number;
  enabled?: boolean;
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  onToggle?: () => void;
  onConfigure?: () => void;
  onRemove?: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  compact?: boolean;
  draggable?: boolean;
}

const STATUS_ICONS: Record<string, string> = {
  pending: '⏳',
  running: '🔄',
  completed: '✅',
  failed: '❌',
  skipped: '⏭️',
};

export function ToolCard({
  tool,
  stepNumber,
  enabled = true,
  status,
  onToggle,
  onConfigure,
  onRemove,
  onMoveUp,
  onMoveDown,
  compact = false,
  draggable = false,
}: ToolCardProps) {
  return (
    <div
      className={`${styles.card} ${!enabled ? styles.disabled : ''} ${compact ? styles.compact : ''}`}
      style={{ borderLeftColor: tool.color }}
      draggable={draggable}
    >
      <div className={styles.header}>
        <div className={styles.iconWrapper} style={{ backgroundColor: `${tool.color}20` }}>
          <ToolIcon icon={tool.icon} size={compact ? 16 : 20} color={tool.color} />
        </div>
        
        <div className={styles.info}>
          <div className={styles.titleRow}>
            {stepNumber !== undefined && (
              <span className={styles.stepNumber}>{stepNumber}.</span>
            )}
            <span className={styles.name}>{tool.name}</span>
            {status && <span className={styles.status}>{STATUS_ICONS[status]}</span>}
          </div>
          {!compact && (
            <div className={styles.meta}>
              <span className={styles.category} style={{ color: tool.color }}>
                {CATEGORY_LABELS[tool.category]}
              </span>
              {tool.supportsPreview && <span className={styles.badge}>👁 превью</span>}
              {tool.supportsManualEdit && <span className={styles.badge}>✏️ редакт.</span>}
            </div>
          )}
        </div>

        <div className={styles.actions}>
          {onToggle && (
            <button
              className={`${styles.actionBtn} ${styles.toggleBtn}`}
              onClick={onToggle}
              title={enabled ? 'Отключить' : 'Включить'}
            >
              {enabled ? '✓' : '○'}
            </button>
          )}
          {onConfigure && (
            <button className={styles.actionBtn} onClick={onConfigure} title="Настроить">
              ⚙️
            </button>
          )}
          {onMoveUp && (
            <button className={styles.actionBtn} onClick={onMoveUp} title="Вверх">
              ↑
            </button>
          )}
          {onMoveDown && (
            <button className={styles.actionBtn} onClick={onMoveDown} title="Вниз">
              ↓
            </button>
          )}
          {onRemove && (
            <button className={`${styles.actionBtn} ${styles.removeBtn}`} onClick={onRemove} title="Удалить">
              ✕
            </button>
          )}
        </div>
      </div>

      {!compact && (
        <div className={styles.description}>{tool.description}</div>
      )}
    </div>
  );
}

export default ToolCard;
