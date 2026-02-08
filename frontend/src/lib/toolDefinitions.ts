/**
 * Tool definitions for pipeline UI
 */

export type ToolCategory = 'input' | 'analysis' | 'video' | 'audio' | 'text' | 'output';

export interface ParamOption {
  value: string | number;
  label: string;
}

export interface ParamField {
  name: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'slider' | 'textarea' | 'file' | 'color';
  default?: unknown;
  options?: ParamOption[];
  min?: number;
  max?: number;
  step?: number;
  description?: string;
}

// Support both old JSON Schema format and new fields format
export type ParamSchema = 
  | { fields: ParamField[] }
  | { type: 'object'; properties: Record<string, unknown> };

export interface ToolDefinition {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: ToolCategory;
  color: string;
  order: number;
  supportsPreview: boolean;
  supportsRetry: boolean;
  supportsManualEdit: boolean;
  inputs: string[];
  outputs: string[];
  defaultParams: Record<string, unknown>;
  paramSchema: ParamSchema;
}

export const CATEGORY_COLORS: Record<ToolCategory, string> = {
  input: '#3B82F6',    // blue
  analysis: '#8B5CF6', // purple
  video: '#10B981',    // green
  audio: '#F59E0B',    // amber
  text: '#EC4899',     // pink
  output: '#6366F1',   // indigo
};

export const CATEGORY_LABELS: Record<ToolCategory, string> = {
  input: 'Ввод',
  analysis: 'Анализ',
  video: 'Видео',
  audio: 'Аудио',
  text: 'Текст',
  output: 'Вывод',
};

export const TOOLS: Record<string, ToolDefinition> = {
  T01_DOWNLOAD: {
    id: 'T01_DOWNLOAD',
    name: 'Загрузка видео',
    description: 'Скачивание исходного видео с платформы',
    icon: 'Download',
    category: 'input',
    color: CATEGORY_COLORS.input,
    order: 1,
    supportsPreview: false,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['url'],
    outputs: ['raw_video'],
    defaultParams: { max_retries: 3, timeout: 300, quality: 'best' },
    paramSchema: {
      type: 'object',
      properties: {
        max_retries: { type: 'number', title: 'Макс. попыток', default: 3, minimum: 1, maximum: 10 },
        timeout: { type: 'number', title: 'Таймаут (сек)', default: 300, minimum: 60, maximum: 600 },
        quality: { type: 'select', title: 'Качество', default: 'best', enum: ['best', '1080p', '720p', '480p'] },
      },
    },
  },
  T02_PROBE: {
    id: 'T02_PROBE',
    name: 'Анализ метаданных',
    description: 'Детальный анализ видео: кодек, разрешение, FPS',
    icon: 'FileSearch',
    category: 'analysis',
    color: CATEGORY_COLORS.analysis,
    order: 2,
    supportsPreview: false,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['raw_video'],
    outputs: ['probe_data'],
    defaultParams: { analyze_audio: true, detect_scenes: false },
    paramSchema: {
      type: 'object',
      properties: {
        analyze_audio: { type: 'boolean', title: 'Анализ аудио', default: true },
        detect_scenes: { type: 'boolean', title: 'Детекция сцен', default: false },
      },
    },
  },
  T03_NORMALIZE: {
    id: 'T03_NORMALIZE',
    name: 'Нормализация',
    description: 'Приведение видео к стандартному формату',
    icon: 'Settings',
    category: 'video',
    color: CATEGORY_COLORS.video,
    order: 3,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['raw_video', 'probe_data'],
    outputs: ['normalized_video'],
    defaultParams: { target_fps: 30, codec: 'h264', crf: 23 },
    paramSchema: {
      type: 'object',
      properties: {
        target_fps: { type: 'select', title: 'FPS', default: 30, enum: [24, 30, 60] },
        codec: { type: 'select', title: 'Кодек', default: 'h264', enum: ['h264', 'h265'] },
        crf: { type: 'number', title: 'CRF (качество)', default: 23, minimum: 18, maximum: 28 },
      },
    },
  },
  T04_CROP_RESIZE: {
    id: 'T04_CROP_RESIZE',
    name: 'Smart Crop',
    description: 'Умная обрезка с детекцией лиц',
    icon: 'Crop',
    category: 'video',
    color: CATEGORY_COLORS.video,
    order: 4,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['normalized_video'],
    outputs: ['cropped_video'],
    defaultParams: { aspect_ratio: '9:16', mode: 'face', width: 1080, height: 1920 },
    paramSchema: {
      type: 'object',
      properties: {
        aspect_ratio: { type: 'select', title: 'Соотношение сторон', default: '9:16', enum: ['9:16', '1:1', '4:5', '16:9'] },
        mode: { type: 'select', title: 'Режим кропа', default: 'face', enum: ['center', 'face', 'content'] },
        width: { type: 'number', title: 'Ширина', default: 1080, minimum: 480, maximum: 2160 },
        height: { type: 'number', title: 'Высота', default: 1920, minimum: 480, maximum: 3840 },
      },
    },
  },
  T05_THUMBNAIL: {
    id: 'T05_THUMBNAIL',
    name: 'Превью/Thumbnail',
    description: 'Генерация превью и миниатюр',
    icon: 'Image',
    category: 'output',
    color: CATEGORY_COLORS.output,
    order: 5,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['cropped_video'],
    outputs: ['thumbnail', 'preview_gif'],
    defaultParams: { count: 1, format: 'jpg', quality: 90 },
    paramSchema: {
      type: 'object',
      properties: {
        count: { type: 'number', title: 'Количество', default: 1, minimum: 1, maximum: 10 },
        format: { type: 'select', title: 'Формат', default: 'jpg', enum: ['jpg', 'png', 'webp'] },
        quality: { type: 'number', title: 'Качество', default: 90, minimum: 50, maximum: 100 },
      },
    },
  },
  T06_BG_MUSIC: {
    id: 'T06_BG_MUSIC',
    name: 'Фоновая музыка',
    description: 'Добавление фоновой музыки из библиотеки',
    icon: 'Music',
    category: 'audio',
    color: CATEGORY_COLORS.audio,
    order: 6,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['cropped_video'],
    outputs: ['video_with_music'],
    defaultParams: { volume: 0.3, fade_in: 2, fade_out: 2, mood: 'auto' },
    paramSchema: {
      type: 'object',
      properties: {
        mood: { type: 'select', title: 'Настроение', default: 'auto', enum: ['auto', 'energetic', 'calm', 'dramatic', 'happy'] },
        volume: { type: 'number', title: 'Громкость', default: 0.3, minimum: 0, maximum: 1 },
        fade_in: { type: 'number', title: 'Fade in (сек)', default: 2, minimum: 0, maximum: 10 },
        fade_out: { type: 'number', title: 'Fade out (сек)', default: 2, minimum: 0, maximum: 10 },
      },
    },
  },
  T07_EXTRACT_AUDIO: {
    id: 'T07_EXTRACT_AUDIO',
    name: 'Извлечение аудио',
    description: 'Извлечение аудиодорожки из видео',
    icon: 'AudioLines',
    category: 'audio',
    color: CATEGORY_COLORS.audio,
    order: 7,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['cropped_video'],
    outputs: ['audio_track'],
    defaultParams: { format: 'wav', sample_rate: 44100 },
    paramSchema: {
      type: 'object',
      properties: {
        format: { type: 'select', title: 'Формат', default: 'wav', enum: ['wav', 'mp3', 'aac'] },
        sample_rate: { type: 'select', title: 'Sample Rate', default: 44100, enum: [22050, 44100, 48000] },
      },
    },
  },
  T08_SPEECH_TO_TEXT: {
    id: 'T08_SPEECH_TO_TEXT',
    name: 'Распознавание речи',
    description: 'Транскрибация с Whisper',
    icon: 'MessageSquare',
    category: 'audio',
    color: CATEGORY_COLORS.audio,
    order: 8,
    supportsPreview: false,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['audio_track'],
    outputs: ['transcript', 'word_timestamps'],
    defaultParams: { model: 'large-v3', language: 'auto' },
    paramSchema: {
      type: 'object',
      properties: {
        model: { type: 'select', title: 'Модель', default: 'large-v3', enum: ['tiny', 'base', 'small', 'medium', 'large-v3'] },
        language: { type: 'string', title: 'Язык (auto)', default: 'auto' },
      },
    },
  },
  T09_TRANSLATE: {
    id: 'T09_TRANSLATE',
    name: 'Перевод текста',
    description: 'Перевод транскрипта',
    icon: 'Languages',
    category: 'text',
    color: CATEGORY_COLORS.text,
    order: 9,
    supportsPreview: false,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['transcript'],
    outputs: ['translated_text'],
    defaultParams: { target_language: 'ru', style: 'casual' },
    paramSchema: {
      type: 'object',
      properties: {
        target_language: { type: 'select', title: 'Целевой язык', default: 'ru', enum: ['ru', 'en', 'es', 'de', 'fr', 'zh'] },
        style: { type: 'select', title: 'Стиль', default: 'casual', enum: ['formal', 'casual', 'preserve'] },
        provider: { type: 'select', title: 'Провайдер', default: 'gpt4', enum: ['gpt4', 'claude', 'deepl'] },
      },
    },
  },
  T10_VOICE_CONVERT: {
    id: 'T10_VOICE_CONVERT',
    name: 'Клонирование голоса',
    description: 'Синтез речи с RVC/ElevenLabs',
    icon: 'Mic',
    category: 'audio',
    color: CATEGORY_COLORS.audio,
    order: 10,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['translated_text', 'audio_track'],
    outputs: ['converted_voice'],
    defaultParams: { provider: 'rvc', voice_id: 'default' },
    paramSchema: {
      type: 'object',
      properties: {
        provider: { type: 'select', title: 'Провайдер', default: 'rvc', enum: ['rvc', 'elevenlabs'] },
        voice_id: { type: 'string', title: 'ID голоса', default: 'default' },
        pitch_shift: { type: 'number', title: 'Сдвиг тона', default: 0, minimum: -12, maximum: 12 },
        speed: { type: 'number', title: 'Скорость', default: 1.0, minimum: 0.5, maximum: 2.0 },
      },
    },
  },
  T11_AUDIO_MIX: {
    id: 'T11_AUDIO_MIX',
    name: 'Сведение аудио',
    description: 'Микширование с LUFS нормализацией',
    icon: 'Sliders',
    category: 'audio',
    color: CATEGORY_COLORS.audio,
    order: 11,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['converted_voice', 'video_with_music'],
    outputs: ['mixed_audio'],
    defaultParams: { target_lufs: -14, voice_volume: 1.0, music_ducking: true },
    paramSchema: {
      type: 'object',
      properties: {
        target_lufs: { type: 'number', title: 'Target LUFS', default: -14, minimum: -24, maximum: -8 },
        voice_volume: { type: 'number', title: 'Громкость голоса', default: 1.0, minimum: 0.5, maximum: 2.0 },
        music_ducking: { type: 'boolean', title: 'Ducking музыки', default: true },
      },
    },
  },
  T12_REPLACE_AUDIO: {
    id: 'T12_REPLACE_AUDIO',
    name: 'Замена аудио',
    description: 'Замена оригинальной аудиодорожки',
    icon: 'RefreshCw',
    category: 'audio',
    color: CATEGORY_COLORS.audio,
    order: 12,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['cropped_video', 'mixed_audio'],
    outputs: ['video_new_audio'],
    defaultParams: { sync_method: 'auto', keep_original: false },
    paramSchema: {
      type: 'object',
      properties: {
        sync_method: { type: 'select', title: 'Синхронизация', default: 'auto', enum: ['auto', 'force', 'stretch'] },
        keep_original: { type: 'boolean', title: 'Сохранить оригинал', default: false },
      },
    },
  },
  T13_BUILD_CAPTIONS: {
    id: 'T13_BUILD_CAPTIONS',
    name: 'Генерация субтитров',
    description: 'ASS субтитры с пословной разметкой',
    icon: 'Subtitles',
    category: 'text',
    color: CATEGORY_COLORS.text,
    order: 13,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['word_timestamps', 'translated_text'],
    outputs: ['captions_ass'],
    defaultParams: { style: 'tiktok', max_words_per_line: 5, highlight_mode: 'word' },
    paramSchema: {
      type: 'object',
      properties: {
        style: { type: 'select', title: 'Стиль', default: 'tiktok', enum: ['tiktok', 'youtube', 'minimal', 'karaoke'] },
        max_words_per_line: { type: 'number', title: 'Макс. слов в строке', default: 5, minimum: 2, maximum: 10 },
        highlight_mode: { type: 'select', title: 'Подсветка', default: 'word', enum: ['word', 'line', 'none'] },
        font_size: { type: 'number', title: 'Размер шрифта', default: 60, minimum: 24, maximum: 120 },
        primary_color: { type: 'color', title: 'Основной цвет', default: '#FFFFFF' },
        highlight_color: { type: 'color', title: 'Цвет подсветки', default: '#FFFF00' },
      },
    },
  },
  T14_BURN_CAPTIONS: {
    id: 'T14_BURN_CAPTIONS',
    name: 'Вшивание субтитров',
    description: 'Наложение субтитров на видео',
    icon: 'Type',
    category: 'video',
    color: CATEGORY_COLORS.video,
    order: 14,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['video_new_audio', 'captions_ass'],
    outputs: ['video_with_captions'],
    defaultParams: { position: 'center', margin_bottom: 150, animation: 'pop' },
    paramSchema: {
      type: 'object',
      properties: {
        position: { type: 'select', title: 'Позиция', default: 'center', enum: ['top', 'center', 'bottom'] },
        margin_bottom: { type: 'number', title: 'Отступ снизу', default: 150, minimum: 0, maximum: 500 },
        animation: { type: 'select', title: 'Анимация', default: 'pop', enum: ['none', 'fade', 'pop', 'slide'] },
      },
    },
  },
  T15_EFFECTS: {
    id: 'T15_EFFECTS',
    name: 'Визуальные эффекты',
    description: 'Уникализация: mirror, zoom, grain',
    icon: 'Sparkles',
    category: 'video',
    color: CATEGORY_COLORS.video,
    order: 15,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['video_with_captions'],
    outputs: ['video_effects'],
    defaultParams: { mirror: false, zoom_max: 1.05, color_shift: 0, grain: 0 },
    paramSchema: {
      type: 'object',
      properties: {
        mirror: { type: 'boolean', title: 'Зеркальное отражение', default: false },
        zoom_max: { type: 'number', title: 'Zoom макс', default: 1.05, minimum: 1.0, maximum: 1.2 },
        color_shift: { type: 'number', title: 'Сдвиг цвета', default: 0, minimum: -30, maximum: 30 },
        grain: { type: 'number', title: 'Зернистость', default: 0, minimum: 0, maximum: 0.5 },
        strip_metadata: { type: 'boolean', title: 'Удалить метаданные', default: true },
      },
    },
  },
  T16_WATERMARK: {
    id: 'T16_WATERMARK',
    name: 'Водяной знак',
    description: 'Текстовый или графический водяной знак',
    icon: 'Stamp',
    category: 'video',
    color: CATEGORY_COLORS.video,
    order: 16,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['video_effects'],
    outputs: ['video_watermarked'],
    defaultParams: { type: 'text', text: '@channel', position: 'bottom_right', opacity: 0.7 },
    paramSchema: {
      type: 'object',
      properties: {
        type: { type: 'select', title: 'Тип', default: 'text', enum: ['text', 'image'] },
        text: { type: 'string', title: 'Текст', default: '@channel' },
        position: { type: 'select', title: 'Позиция', default: 'bottom_right', enum: ['top_left', 'top_right', 'bottom_left', 'bottom_right', 'center'] },
        opacity: { type: 'number', title: 'Прозрачность', default: 0.7, minimum: 0.1, maximum: 1.0 },
        size: { type: 'number', title: 'Размер', default: 24, minimum: 12, maximum: 72 },
      },
    },
  },
  T17_PACKAGE: {
    id: 'T17_PACKAGE',
    name: 'Финальная сборка',
    description: 'Финальная сборка с оптимизацией битрейта',
    icon: 'Package',
    category: 'output',
    color: CATEGORY_COLORS.output,
    order: 17,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['video_watermarked'],
    outputs: ['final_video'],
    defaultParams: { codec: 'h264', preset: 'slow', crf: 20 },
    paramSchema: {
      type: 'object',
      properties: {
        codec: { type: 'select', title: 'Кодек', default: 'h264', enum: ['h264', 'h265'] },
        preset: { type: 'select', title: 'Пресет', default: 'slow', enum: ['ultrafast', 'fast', 'medium', 'slow', 'veryslow'] },
        crf: { type: 'number', title: 'CRF', default: 20, minimum: 15, maximum: 28 },
        audio_bitrate: { type: 'select', title: 'Битрейт аудио', default: '192k', enum: ['128k', '192k', '256k', '320k'] },
      },
    },
  },
  T18_QC: {
    id: 'T18_QC',
    name: 'Контроль качества',
    description: 'Финальная проверка качества',
    icon: 'CheckCircle',
    category: 'output',
    color: CATEGORY_COLORS.output,
    order: 18,
    supportsPreview: false,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['final_video'],
    outputs: ['qc_report', 'ready_video'],
    defaultParams: { min_bitrate: '2M', check_audio_levels: true },
    paramSchema: {
      type: 'object',
      properties: {
        min_bitrate: { type: 'string', title: 'Мин. битрейт', default: '2M' },
        check_audio_levels: { type: 'boolean', title: 'Проверять аудио', default: true },
        min_lufs: { type: 'number', title: 'Мин. LUFS', default: -18, minimum: -24, maximum: -8 },
        fail_on_warning: { type: 'boolean', title: 'Fail при warnings', default: false },
      },
    },
  },
  T20_SPEED: {
    id: 'T20_SPEED',
    name: 'Изменение скорости',
    description: 'Ускорение или замедление видео',
    icon: 'Gauge',
    category: 'video',
    color: CATEGORY_COLORS.video,
    order: 20,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['video'],
    outputs: ['speed_video'],
    defaultParams: { speed: 1.0 },
    paramSchema: {
      type: 'object',
      properties: {
        speed: { type: 'number', title: 'Скорость', default: 1.0, minimum: 0.5, maximum: 2.0 },
      },
    },
  },
  T21_TRIM: {
    id: 'T21_TRIM',
    name: 'Обрезка видео',
    description: 'Обрезка начала/конца видео',
    icon: 'Scissors',
    category: 'video',
    color: CATEGORY_COLORS.video,
    order: 21,
    supportsPreview: true,
    supportsRetry: true,
    supportsManualEdit: true,
    inputs: ['video'],
    outputs: ['trimmed_video'],
    defaultParams: { start: 0, duration: null, end: null },
    paramSchema: {
      type: 'object',
      properties: {
        start: { type: 'number', title: 'Начало (сек)', default: 0, minimum: 0 },
        duration: { type: 'number', title: 'Длительность (сек)', default: null },
        end: { type: 'number', title: 'Конец (сек)', default: null },
      },
    },
  },
  T30_COPY_READY: {
    id: 'T30_COPY_READY',
    name: 'Копирование в ready',
    description: 'Копирование финального видео без перекодировки',
    icon: 'Copy',
    category: 'output',
    color: CATEGORY_COLORS.output,
    order: 30,
    supportsPreview: false,
    supportsRetry: true,
    supportsManualEdit: false,
    inputs: ['video'],
    outputs: ['ready_video'],
    defaultParams: {},
    paramSchema: {
      type: 'object',
      properties: {},
    },
  },
};

export const TOOLS_LIST = Object.values(TOOLS).sort((a, b) => a.order - b.order);

export const getToolsByCategory = (category: ToolCategory): ToolDefinition[] => {
  return TOOLS_LIST.filter(t => t.category === category);
};

export const getTool = (toolId: string): ToolDefinition | undefined => {
  return TOOLS[toolId];
};
