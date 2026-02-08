"use client";

import { getTool } from "@/lib/toolDefinitions";
import styles from "./ToolParamsForm.module.css";

type ParamFieldNormalized = {
  name: string;
  label: string;
  type: string;
  default?: unknown;
  options?: { value: string | number; label: string }[];
  min?: number;
  max?: number;
  step?: number;
};

type ToolParamsFormProps = {
  toolId: string;
  params: Record<string, unknown>;
  onChange: (params: Record<string, unknown>) => void;
  disabled?: boolean;
  paramSchema?: unknown;
};

function normalizeSchema(schema: unknown): ParamFieldNormalized[] {
  if (!schema) return [];
  
  const s = schema as Record<string, unknown>;
  
  // New format: { fields: [...] }
  if (Array.isArray(s.fields)) {
    return s.fields as ParamFieldNormalized[];
  }
  
  // Old format: { type: 'object', properties: {...} }
  if (s.properties && typeof s.properties === 'object') {
    const props = s.properties as Record<string, Record<string, unknown>>;
    return Object.entries(props).map(([name, prop]) => ({
      name,
      label: (prop.title as string) || name,
      type: (prop.type as string) || 'string',
      default: prop.default,
      options: prop.enum ? (prop.enum as (string | number)[]).map(v => ({ value: v, label: String(v) })) : undefined,
      min: prop.minimum as number | undefined,
      max: prop.maximum as number | undefined,
      step: prop.step as number | undefined,
    }));
  }
  
  return [];
}

export function ToolParamsForm({ toolId, params, onChange, disabled = false, paramSchema }: ToolParamsFormProps) {
  const tool = getTool(toolId);
  
  const fields = normalizeSchema(paramSchema ?? tool?.paramSchema);
  
  if (!fields.length) {
    return <div className={styles.empty}>Нет настраиваемых параметров</div>;
  }
  
  const handleChange = (fieldName: string, value: unknown) => {
    onChange({ ...params, [fieldName]: value });
  };
  
  return (
    <div className={styles.form}>
      {fields.map((field) => (
        <FieldInput
          key={field.name}
          field={field}
          value={params[field.name] ?? field.default}
          onChange={(v) => handleChange(field.name, v)}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

type FieldInputProps = {
  field: ParamFieldNormalized;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled: boolean;
};

function FieldInput({ field, value, onChange, disabled }: FieldInputProps) {
  const { name, label, type, options, min, max, step } = field;
  
  const renderInput = () => {
    switch (type) {
      case "select":
        return (
          <select
            className={styles.select}
            value={String(value ?? "")}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
          >
            {options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        );
      
      case "number":
        return (
          <input
            type="number"
            className={styles.input}
            value={value as number ?? 0}
            onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
            min={min}
            max={max}
            step={step ?? 1}
            disabled={disabled}
          />
        );
      
      case "boolean":
        return (
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => onChange(e.target.checked)}
              disabled={disabled}
            />
            <span>Включено</span>
          </label>
        );
      
      case "slider":
        return (
          <div className={styles.sliderWrapper}>
            <input
              type="range"
              className={styles.slider}
              value={value as number ?? min ?? 0}
              onChange={(e) => onChange(parseFloat(e.target.value))}
              min={min ?? 0}
              max={max ?? 100}
              step={step ?? 1}
              disabled={disabled}
            />
            <span className={styles.sliderValue}>{value as number ?? min ?? 0}</span>
          </div>
        );
      
      case "textarea":
        return (
          <textarea
            className={styles.textarea}
            value={String(value ?? "")}
            onChange={(e) => onChange(e.target.value)}
            rows={3}
            disabled={disabled}
          />
        );
      
      case "file":
        return (
          <div className={styles.fileWrapper}>
            <input
              type="text"
              className={styles.input}
              value={String(value ?? "")}
              onChange={(e) => onChange(e.target.value)}
              placeholder="Путь к файлу..."
              disabled={disabled}
            />
          </div>
        );
      
      case "string":
      default:
        return (
          <input
            type="text"
            className={styles.input}
            value={String(value ?? "")}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
          />
        );
    }
  };
  
  return (
    <div className={styles.field}>
      <label className={styles.label}>{label || name}</label>
      {renderInput()}
    </div>
  );
}

export default ToolParamsForm;
