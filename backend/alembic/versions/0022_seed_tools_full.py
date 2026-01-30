"""seed all 18 tools with full metadata

Revision ID: 0022_seed_tools_full
Revises: 0021_step_results_and_moderation
Create Date: 2026-01-29 16:00:00.000000
"""

from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa


revision: str = "0022_seed_tools_full"
down_revision: Union[str, None] = "0021_step_results_and_moderation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TOOLS = [
    {
        "tool_id": "T01_DOWNLOAD",
        "name": "Загрузка видео",
        "category": "input",
        "description": "Скачивание исходного видео с платформы (YouTube, TikTok, VK, Instagram)",
        "icon": "Download",
        "order_index": 1,
        "supports_preview": False,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["url"],
        "outputs": ["raw_video"],
        "default_params": {"max_retries": 3, "timeout": 300, "quality": "best"},
        "param_schema": {
            "type": "object",
            "properties": {
                "max_retries": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3, "title": "Макс. попыток"},
                "timeout": {"type": "integer", "minimum": 60, "maximum": 600, "default": 300, "title": "Таймаут (сек)"},
                "quality": {"type": "string", "enum": ["best", "1080p", "720p", "480p"], "default": "best", "title": "Качество"}
            }
        },
        "ui_component": "T01DownloadParams"
    },
    {
        "tool_id": "T02_PROBE",
        "name": "Анализ метаданных",
        "category": "analysis",
        "description": "Детальный анализ видео: кодек, разрешение, FPS, аудио потоки, HDR",
        "icon": "FileSearch",
        "order_index": 2,
        "supports_preview": False,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["raw_video"],
        "outputs": ["probe_data"],
        "default_params": {"analyze_audio": True, "detect_scenes": False},
        "param_schema": {
            "type": "object",
            "properties": {
                "analyze_audio": {"type": "boolean", "default": True, "title": "Анализ аудио"},
                "detect_scenes": {"type": "boolean", "default": False, "title": "Детекция сцен"}
            }
        },
        "ui_component": "T02ProbeParams"
    },
    {
        "tool_id": "T03_NORMALIZE",
        "name": "Нормализация",
        "category": "video",
        "description": "Приведение видео к стандартному формату: FPS, кодек, цветовое пространство",
        "icon": "Settings",
        "order_index": 3,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["raw_video", "probe_data"],
        "outputs": ["normalized_video"],
        "default_params": {"target_fps": 30, "codec": "h264", "color_space": "bt709"},
        "param_schema": {
            "type": "object",
            "properties": {
                "target_fps": {"type": "integer", "enum": [24, 30, 60], "default": 30, "title": "FPS"},
                "codec": {"type": "string", "enum": ["h264", "h265"], "default": "h264", "title": "Кодек"},
                "color_space": {"type": "string", "enum": ["bt709", "bt2020"], "default": "bt709", "title": "Цвет. пространство"},
                "crf": {"type": "integer", "minimum": 18, "maximum": 28, "default": 23, "title": "CRF (качество)"}
            }
        },
        "ui_component": "T03NormalizeParams"
    },
    {
        "tool_id": "T04_CROP_RESIZE",
        "name": "Smart Crop",
        "category": "video",
        "description": "Умная обрезка и масштабирование с детекцией лиц и контента",
        "icon": "Crop",
        "order_index": 4,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["normalized_video"],
        "outputs": ["cropped_video"],
        "default_params": {"aspect_ratio": "9:16", "mode": "face", "padding": 0},
        "param_schema": {
            "type": "object",
            "properties": {
                "aspect_ratio": {"type": "string", "enum": ["9:16", "1:1", "4:5", "16:9"], "default": "9:16", "title": "Соотношение сторон"},
                "mode": {"type": "string", "enum": ["center", "face", "content"], "default": "face", "title": "Режим кропа"},
                "padding": {"type": "integer", "minimum": 0, "maximum": 100, "default": 0, "title": "Отступ (px)"},
                "width": {"type": "integer", "minimum": 480, "maximum": 2160, "default": 1080, "title": "Ширина"},
                "height": {"type": "integer", "minimum": 480, "maximum": 3840, "default": 1920, "title": "Высота"}
            }
        },
        "ui_component": "T04CropParams"
    },
    {
        "tool_id": "T05_THUMBNAIL",
        "name": "Превью/Thumbnail",
        "category": "output",
        "description": "Генерация превью и миниатюр из лучших кадров",
        "icon": "Image",
        "order_index": 5,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["cropped_video"],
        "outputs": ["thumbnail", "preview_gif"],
        "default_params": {"count": 1, "format": "jpg", "quality": 90},
        "param_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1, "title": "Количество"},
                "format": {"type": "string", "enum": ["jpg", "png", "webp"], "default": "jpg", "title": "Формат"},
                "quality": {"type": "integer", "minimum": 50, "maximum": 100, "default": 90, "title": "Качество"},
                "width": {"type": "integer", "minimum": 320, "maximum": 1920, "default": 720, "title": "Ширина"},
                "generate_gif": {"type": "boolean", "default": False, "title": "GIF превью"}
            }
        },
        "ui_component": "T05ThumbnailParams"
    },
    {
        "tool_id": "T06_BG_MUSIC",
        "name": "Фоновая музыка",
        "category": "audio",
        "description": "Добавление фоновой музыки из библиотеки с автоматическим подбором",
        "icon": "Music",
        "order_index": 6,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["cropped_video"],
        "outputs": ["video_with_music"],
        "default_params": {"volume": 0.3, "fade_in": 2, "fade_out": 2, "mood": "auto"},
        "param_schema": {
            "type": "object",
            "properties": {
                "track_id": {"type": "string", "title": "ID трека (или авто)"},
                "mood": {"type": "string", "enum": ["auto", "energetic", "calm", "dramatic", "happy"], "default": "auto", "title": "Настроение"},
                "volume": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.3, "title": "Громкость"},
                "fade_in": {"type": "number", "minimum": 0, "maximum": 10, "default": 2, "title": "Fade in (сек)"},
                "fade_out": {"type": "number", "minimum": 0, "maximum": 10, "default": 2, "title": "Fade out (сек)"}
            }
        },
        "ui_component": "T06BgMusicParams"
    },
    {
        "tool_id": "T07_EXTRACT_AUDIO",
        "name": "Извлечение аудио",
        "category": "audio",
        "description": "Извлечение аудиодорожки из видео для обработки",
        "icon": "AudioLines",
        "order_index": 7,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["cropped_video"],
        "outputs": ["audio_track"],
        "default_params": {"format": "wav", "sample_rate": 44100},
        "param_schema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["wav", "mp3", "aac"], "default": "wav", "title": "Формат"},
                "sample_rate": {"type": "integer", "enum": [22050, 44100, 48000], "default": 44100, "title": "Sample Rate"},
                "channels": {"type": "integer", "enum": [1, 2], "default": 2, "title": "Каналы"}
            }
        },
        "ui_component": "T07ExtractAudioParams"
    },
    {
        "tool_id": "T08_SPEECH_TO_TEXT",
        "name": "Распознавание речи",
        "category": "audio",
        "description": "Транскрибация речи с помощью Whisper (word-level timestamps)",
        "icon": "MessageSquare",
        "order_index": 8,
        "supports_preview": False,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["audio_track"],
        "outputs": ["transcript", "word_timestamps"],
        "default_params": {"model": "large-v3", "language": "auto"},
        "param_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "enum": ["tiny", "base", "small", "medium", "large-v3"], "default": "large-v3", "title": "Модель Whisper"},
                "language": {"type": "string", "default": "auto", "title": "Язык (auto для определения)"},
                "word_timestamps": {"type": "boolean", "default": True, "title": "Пословные таймстампы"}
            }
        },
        "ui_component": "T08SpeechToTextParams"
    },
    {
        "tool_id": "T09_TRANSLATE",
        "name": "Перевод текста",
        "category": "text",
        "description": "Перевод транскрипта с сохранением стиля речи",
        "icon": "Languages",
        "order_index": 9,
        "supports_preview": False,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["transcript"],
        "outputs": ["translated_text"],
        "default_params": {"target_language": "ru", "style": "casual"},
        "param_schema": {
            "type": "object",
            "properties": {
                "target_language": {"type": "string", "enum": ["ru", "en", "es", "de", "fr", "zh"], "default": "ru", "title": "Целевой язык"},
                "style": {"type": "string", "enum": ["formal", "casual", "preserve"], "default": "casual", "title": "Стиль"},
                "provider": {"type": "string", "enum": ["gpt4", "claude", "deepl"], "default": "gpt4", "title": "Провайдер"}
            }
        },
        "ui_component": "T09TranslateParams"
    },
    {
        "tool_id": "T10_VOICE_CONVERT",
        "name": "Клонирование голоса",
        "category": "audio",
        "description": "Синтез речи с клонированием голоса (RVC/ElevenLabs)",
        "icon": "Mic",
        "order_index": 10,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["translated_text", "audio_track"],
        "outputs": ["converted_voice"],
        "default_params": {"provider": "rvc", "voice_id": "default"},
        "param_schema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "enum": ["rvc", "elevenlabs"], "default": "rvc", "title": "Провайдер"},
                "voice_id": {"type": "string", "default": "default", "title": "ID голоса"},
                "pitch_shift": {"type": "integer", "minimum": -12, "maximum": 12, "default": 0, "title": "Сдвиг тона"},
                "speed": {"type": "number", "minimum": 0.5, "maximum": 2.0, "default": 1.0, "title": "Скорость"}
            }
        },
        "ui_component": "T10VoiceConvertParams"
    },
    {
        "tool_id": "T11_AUDIO_MIX",
        "name": "Сведение аудио",
        "category": "audio",
        "description": "Микширование голоса и музыки с LUFS нормализацией",
        "icon": "Sliders",
        "order_index": 11,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["converted_voice", "video_with_music"],
        "outputs": ["mixed_audio"],
        "default_params": {"target_lufs": -14, "voice_volume": 1.0, "music_ducking": True},
        "param_schema": {
            "type": "object",
            "properties": {
                "target_lufs": {"type": "integer", "minimum": -24, "maximum": -8, "default": -14, "title": "Target LUFS"},
                "voice_volume": {"type": "number", "minimum": 0.5, "maximum": 2.0, "default": 1.0, "title": "Громкость голоса"},
                "music_ducking": {"type": "boolean", "default": True, "title": "Ducking музыки"},
                "ducking_amount": {"type": "number", "minimum": 0.1, "maximum": 0.9, "default": 0.5, "title": "Сила ducking"}
            }
        },
        "ui_component": "T11AudioMixParams"
    },
    {
        "tool_id": "T12_REPLACE_AUDIO",
        "name": "Замена аудио",
        "category": "audio",
        "description": "Замена оригинальной аудиодорожки на обработанную",
        "icon": "RefreshCw",
        "order_index": 12,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["cropped_video", "mixed_audio"],
        "outputs": ["video_new_audio"],
        "default_params": {"sync_method": "auto", "keep_original": False},
        "param_schema": {
            "type": "object",
            "properties": {
                "sync_method": {"type": "string", "enum": ["auto", "force", "stretch"], "default": "auto", "title": "Метод синхронизации"},
                "keep_original": {"type": "boolean", "default": False, "title": "Сохранить оригинал (вторая дорожка)"},
                "fade_transition": {"type": "number", "minimum": 0, "maximum": 2, "default": 0.1, "title": "Fade перехода (сек)"}
            }
        },
        "ui_component": "T12ReplaceAudioParams"
    },
    {
        "tool_id": "T13_BUILD_CAPTIONS",
        "name": "Генерация субтитров",
        "category": "text",
        "description": "Создание ASS субтитров с пословной разметкой и стилями",
        "icon": "Subtitles",
        "order_index": 13,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["word_timestamps", "translated_text"],
        "outputs": ["captions_ass"],
        "default_params": {"style": "tiktok", "max_words_per_line": 5, "highlight_mode": "word"},
        "param_schema": {
            "type": "object",
            "properties": {
                "style": {"type": "string", "enum": ["tiktok", "youtube", "minimal", "karaoke"], "default": "tiktok", "title": "Стиль"},
                "max_words_per_line": {"type": "integer", "minimum": 2, "maximum": 10, "default": 5, "title": "Макс. слов в строке"},
                "highlight_mode": {"type": "string", "enum": ["word", "line", "none"], "default": "word", "title": "Режим подсветки"},
                "font": {"type": "string", "default": "Montserrat Bold", "title": "Шрифт"},
                "font_size": {"type": "integer", "minimum": 24, "maximum": 120, "default": 60, "title": "Размер шрифта"},
                "primary_color": {"type": "string", "default": "#FFFFFF", "title": "Основной цвет"},
                "highlight_color": {"type": "string", "default": "#FFFF00", "title": "Цвет подсветки"}
            }
        },
        "ui_component": "T13BuildCaptionsParams"
    },
    {
        "tool_id": "T14_BURN_CAPTIONS",
        "name": "Вшивание субтитров",
        "category": "video",
        "description": "Наложение субтитров на видео с анимациями",
        "icon": "Type",
        "order_index": 14,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["video_new_audio", "captions_ass"],
        "outputs": ["video_with_captions"],
        "default_params": {"position": "center", "margin_bottom": 150},
        "param_schema": {
            "type": "object",
            "properties": {
                "position": {"type": "string", "enum": ["top", "center", "bottom"], "default": "center", "title": "Позиция"},
                "margin_bottom": {"type": "integer", "minimum": 0, "maximum": 500, "default": 150, "title": "Отступ снизу (px)"},
                "animation": {"type": "string", "enum": ["none", "fade", "pop", "slide"], "default": "pop", "title": "Анимация"}
            }
        },
        "ui_component": "T14BurnCaptionsParams"
    },
    {
        "tool_id": "T15_EFFECTS",
        "name": "Визуальные эффекты",
        "category": "video",
        "description": "Уникализация: mirror, zoom, color shift, grain, speed variation",
        "icon": "Sparkles",
        "order_index": 15,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["video_with_captions"],
        "outputs": ["video_effects"],
        "default_params": {"mirror": False, "zoom_range": [1.0, 1.05], "color_shift": 0, "grain": 0, "speed_var": 0},
        "param_schema": {
            "type": "object",
            "properties": {
                "mirror": {"type": "boolean", "default": False, "title": "Зеркальное отражение"},
                "zoom_min": {"type": "number", "minimum": 1.0, "maximum": 1.1, "default": 1.0, "title": "Zoom мин"},
                "zoom_max": {"type": "number", "minimum": 1.0, "maximum": 1.2, "default": 1.05, "title": "Zoom макс"},
                "color_shift": {"type": "integer", "minimum": -30, "maximum": 30, "default": 0, "title": "Сдвиг цвета"},
                "grain": {"type": "number", "minimum": 0, "maximum": 0.5, "default": 0, "title": "Зернистость"},
                "speed_variation": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0, "title": "Вариация скорости"},
                "strip_metadata": {"type": "boolean", "default": True, "title": "Удалить метаданные"}
            }
        },
        "ui_component": "T15EffectsParams"
    },
    {
        "tool_id": "T16_WATERMARK",
        "name": "Водяной знак",
        "category": "video",
        "description": "Наложение текстового или графического водяного знака",
        "icon": "Stamp",
        "order_index": 16,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": True,
        "inputs": ["video_effects"],
        "outputs": ["video_watermarked"],
        "default_params": {"type": "text", "position": "bottom_right", "opacity": 0.7},
        "param_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["text", "image"], "default": "text", "title": "Тип"},
                "text": {"type": "string", "default": "@channel", "title": "Текст"},
                "image_path": {"type": "string", "title": "Путь к изображению"},
                "position": {"type": "string", "enum": ["top_left", "top_right", "bottom_left", "bottom_right", "center"], "default": "bottom_right", "title": "Позиция"},
                "opacity": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.7, "title": "Прозрачность"},
                "size": {"type": "integer", "minimum": 12, "maximum": 72, "default": 24, "title": "Размер"},
                "margin": {"type": "integer", "minimum": 0, "maximum": 100, "default": 20, "title": "Отступ (px)"},
                "animation": {"type": "string", "enum": ["none", "fade_in", "fade_out", "fade_both"], "default": "none", "title": "Анимация"}
            }
        },
        "ui_component": "T16WatermarkParams"
    },
    {
        "tool_id": "T17_PACKAGE",
        "name": "Финальная сборка",
        "category": "output",
        "description": "Финальная сборка видео с оптимизацией битрейта",
        "icon": "Package",
        "order_index": 17,
        "supports_preview": True,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["video_watermarked"],
        "outputs": ["final_video"],
        "default_params": {"codec": "h264", "preset": "slow", "crf": 20},
        "param_schema": {
            "type": "object",
            "properties": {
                "codec": {"type": "string", "enum": ["h264", "h265"], "default": "h264", "title": "Кодек"},
                "preset": {"type": "string", "enum": ["ultrafast", "fast", "medium", "slow", "veryslow"], "default": "slow", "title": "Пресет кодирования"},
                "crf": {"type": "integer", "minimum": 15, "maximum": 28, "default": 20, "title": "CRF (качество)"},
                "max_bitrate": {"type": "string", "default": "8M", "title": "Макс. битрейт"},
                "audio_bitrate": {"type": "string", "enum": ["128k", "192k", "256k", "320k"], "default": "192k", "title": "Битрейт аудио"}
            }
        },
        "ui_component": "T17PackageParams"
    },
    {
        "tool_id": "T18_QC",
        "name": "Контроль качества",
        "category": "output",
        "description": "Финальная проверка качества: битрейт, разрешение, аудио уровни",
        "icon": "CheckCircle",
        "order_index": 18,
        "supports_preview": False,
        "supports_retry": True,
        "supports_manual_edit": False,
        "inputs": ["final_video"],
        "outputs": ["qc_report", "ready_video"],
        "default_params": {"min_bitrate": "2M", "check_audio_levels": True},
        "param_schema": {
            "type": "object",
            "properties": {
                "min_bitrate": {"type": "string", "default": "2M", "title": "Мин. битрейт"},
                "max_bitrate": {"type": "string", "default": "15M", "title": "Макс. битрейт"},
                "check_audio_levels": {"type": "boolean", "default": True, "title": "Проверять уровни аудио"},
                "min_lufs": {"type": "integer", "minimum": -24, "maximum": -8, "default": -18, "title": "Мин. LUFS"},
                "max_lufs": {"type": "integer", "minimum": -16, "maximum": 0, "default": -10, "title": "Макс. LUFS"},
                "check_resolution": {"type": "boolean", "default": True, "title": "Проверять разрешение"},
                "fail_on_warning": {"type": "boolean", "default": False, "title": "Fail при warnings"}
            }
        },
        "ui_component": "T18QCParams"
    }
]


def upgrade() -> None:
    conn = op.get_bind()
    
    for tool in TOOLS:
        # Check if tool exists
        result = conn.execute(
            sa.text("SELECT tool_id FROM tool_registry WHERE tool_id = :tid"),
            {"tid": tool["tool_id"]}
        )
        exists = result.fetchone() is not None
        
        if exists:
            # Update existing tool
            conn.execute(
                sa.text("""
                    UPDATE tool_registry SET
                        name = :name,
                        category = :category,
                        description = :description,
                        icon = :icon,
                        order_index = :order_index,
                        supports_preview = :supports_preview,
                        supports_retry = :supports_retry,
                        supports_manual_edit = :supports_manual_edit,
                        inputs = :inputs,
                        outputs = :outputs,
                        default_params = :default_params,
                        param_schema = :param_schema,
                        ui_component = :ui_component,
                        updated_at = NOW()
                    WHERE tool_id = :tool_id
                """),
                {
                    "tool_id": tool["tool_id"],
                    "name": tool["name"],
                    "category": tool["category"],
                    "description": tool["description"],
                    "icon": tool["icon"],
                    "order_index": tool["order_index"],
                    "supports_preview": tool["supports_preview"],
                    "supports_retry": tool["supports_retry"],
                    "supports_manual_edit": tool["supports_manual_edit"],
                    "inputs": json.dumps(tool["inputs"]),
                    "outputs": json.dumps(tool["outputs"]),
                    "default_params": json.dumps(tool["default_params"]),
                    "param_schema": json.dumps(tool["param_schema"]),
                    "ui_component": tool["ui_component"]
                }
            )
        else:
            # Insert new tool
            conn.execute(
                sa.text("""
                    INSERT INTO tool_registry (
                        tool_id, name, category, description, icon, order_index,
                        supports_preview, supports_retry, supports_manual_edit,
                        inputs, outputs, default_params, param_schema, ui_component,
                        is_active, created_at, updated_at
                    ) VALUES (
                        :tool_id, :name, :category, :description, :icon, :order_index,
                        :supports_preview, :supports_retry, :supports_manual_edit,
                        :inputs, :outputs, :default_params, :param_schema, :ui_component,
                        true, NOW(), NOW()
                    )
                """),
                {
                    "tool_id": tool["tool_id"],
                    "name": tool["name"],
                    "category": tool["category"],
                    "description": tool["description"],
                    "icon": tool["icon"],
                    "order_index": tool["order_index"],
                    "supports_preview": tool["supports_preview"],
                    "supports_retry": tool["supports_retry"],
                    "supports_manual_edit": tool["supports_manual_edit"],
                    "inputs": json.dumps(tool["inputs"]),
                    "outputs": json.dumps(tool["outputs"]),
                    "default_params": json.dumps(tool["default_params"]),
                    "param_schema": json.dumps(tool["param_schema"]),
                    "ui_component": tool["ui_component"]
                }
            )


def downgrade() -> None:
    # Keep tools but clear extended fields
    op.execute("""
        UPDATE tool_registry SET
            description = NULL,
            icon = NULL,
            param_schema = NULL,
            ui_component = NULL,
            supports_preview = false,
            supports_retry = true,
            supports_manual_edit = false,
            order_index = 0
    """)
