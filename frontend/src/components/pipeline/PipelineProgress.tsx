'use client';

import { ToolIcon } from './ToolIcon';
import { getTool } from '@/lib/toolDefinitions';
import styles from './PipelineProgress.module.css';

interface StepStatus {
  stepIndex: number;
  toolId: string;
  name?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  moderationStatus?: 'pending' | 'approved' | 'rejected' | 'needs_rework';
}

interface PipelineProgressProps {
  steps: StepStatus[];
  currentStepIndex?: number;
  onStepClick?: (stepIndex: number) => void;
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#666',
  running: '#3B82F6',
  completed: '#10B981',
  failed: '#EF4444',
  skipped: '#888',
};

const MODERATION_ICONS: Record<string, string> = {
  pending: '⏳',
  approved: '✅',
  rejected: '❌',
  needs_rework: '🔄',
};

export function PipelineProgress({ steps, currentStepIndex, onStepClick }: PipelineProgressProps) {
  return (
    <div className={styles.container}>
      <div className={styles.progressLine}>
        {steps.map((step, idx) => {
          const tool = getTool(step.toolId);
          const isActive = idx === currentStepIndex;
          const statusColor = STATUS_COLORS[step.status] || '#666';

          return (
            <div
              key={step.stepIndex}
              className={`${styles.step} ${isActive ? styles.active : ''}`}
              onClick={() => onStepClick?.(step.stepIndex)}
            >
              <div
                className={styles.stepIcon}
                style={{
                  backgroundColor: step.status === 'completed' ? statusColor : 'transparent',
                  borderColor: statusColor,
                }}
              >
                {tool ? (
                  <ToolIcon
                    icon={tool.icon}
                    size={16}
                    color={step.status === 'completed' ? '#fff' : statusColor}
                  />
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              {idx < steps.length - 1 && (
                <div
                  className={styles.connector}
                  style={{
                    backgroundColor: step.status === 'completed' ? STATUS_COLORS.completed : '#333',
                  }}
                />
              )}

              <div className={styles.stepLabel}>
                <span className={styles.stepName}>{step.name || tool?.name || step.toolId}</span>
                {step.moderationStatus && (
                  <span className={styles.moderationIcon}>
                    {MODERATION_ICONS[step.moderationStatus]}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default PipelineProgress;
