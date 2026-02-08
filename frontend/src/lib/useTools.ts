"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import {
  TOOLS,
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  type ToolDefinition,
  type ToolCategory,
  type ParamSchema,
} from "./toolDefinitions";

/** Shape returned by GET /api/tools */
interface ApiTool {
  tool_id: string;
  name: string;
  category: string | null;
  inputs: string[] | null;
  outputs: string[] | null;
  default_params: Record<string, unknown> | null;
  is_active: boolean;
  description: string | null;
  icon: string | null;
  param_schema: Record<string, unknown> | null;
  ui_component: string | null;
  supports_preview: boolean;
  supports_retry: boolean;
  supports_manual_edit: boolean;
  order_index: number;
}

/** Convert API tool to ToolDefinition, using local TOOLS as fallback for missing fields */
function apiToolToDefinition(api: ApiTool): ToolDefinition {
  const local = TOOLS[api.tool_id];
  const category = (api.category || local?.category || "video") as ToolCategory;

  return {
    id: api.tool_id,
    name: api.name || local?.name || api.tool_id,
    description: api.description || local?.description || "",
    icon: api.icon || local?.icon || "HelpCircle",
    category,
    color: CATEGORY_COLORS[category] || "#888",
    order: api.order_index || local?.order || 0,
    supportsPreview: api.supports_preview ?? local?.supportsPreview ?? false,
    supportsRetry: api.supports_retry ?? local?.supportsRetry ?? true,
    supportsManualEdit: api.supports_manual_edit ?? local?.supportsManualEdit ?? false,
    inputs: api.inputs || local?.inputs || [],
    outputs: api.outputs || local?.outputs || [],
    defaultParams: api.default_params || local?.defaultParams || {},
    paramSchema: (api.param_schema as ParamSchema) || local?.paramSchema || { type: "object", properties: {} },
  };
}

export function useTools() {
  const [apiTools, setApiTools] = useState<ToolDefinition[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTools = useCallback(async () => {
    try {
      const res = await fetch("/api/tools");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ApiTool[] = await res.json();
      setApiTools(data.map(apiToolToDefinition));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tools");
      // fallback: use local definitions
      setApiTools(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTools();
  }, [fetchTools]);

  /** Sorted tools list — API if available, local fallback otherwise */
  const toolsList = useMemo(() => {
    if (apiTools) return [...apiTools].sort((a, b) => a.order - b.order);
    return Object.values(TOOLS).sort((a, b) => a.order - b.order);
  }, [apiTools]);

  /** Tools indexed by id */
  const toolsMap = useMemo(() => {
    const map: Record<string, ToolDefinition> = {};
    for (const t of toolsList) map[t.id] = t;
    return map;
  }, [toolsList]);

  /** Get tool by id — API first, then local fallback */
  const getTool = useCallback(
    (toolId: string): ToolDefinition | undefined => {
      return toolsMap[toolId] || TOOLS[toolId];
    },
    [toolsMap],
  );

  /** Tools grouped by category */
  const toolsByCategory = useMemo(() => {
    const groups: Partial<Record<ToolCategory, ToolDefinition[]>> = {};
    for (const t of toolsList) {
      if (!groups[t.category]) groups[t.category] = [];
      groups[t.category]!.push(t);
    }
    return groups;
  }, [toolsList]);

  return {
    tools: toolsMap,
    toolsList,
    toolsByCategory,
    getTool,
    loading,
    error,
    refetch: fetchTools,
    categoryLabels: CATEGORY_LABELS,
    categoryColors: CATEGORY_COLORS,
  };
}
