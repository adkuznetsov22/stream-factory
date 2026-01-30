"""
Telegram notification service for pipeline events.
"""

import asyncio
import logging
from typing import Optional

import httpx

from ..settings import get_settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications to Telegram chat/channel."""
    
    def __init__(self):
        self.settings = get_settings()
        self.bot_token: str | None = getattr(self.settings, 'telegram_bot_token', None)
        self.chat_id: str | None = getattr(self.settings, 'telegram_chat_id', None)
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            logger.warning("Telegram notifier disabled: missing bot_token or chat_id")
    
    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a text message to configured chat."""
        if not self.enabled:
            logger.debug("Telegram notifier disabled, skipping message")
            return False
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Telegram message sent to {self.chat_id}")
                    return True
                else:
                    logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def notify_task_completed(
        self,
        task_id: int,
        project_name: str,
        platform: str,
        duration_sec: Optional[float] = None,
    ):
        """Notify when a task is successfully completed."""
        duration_str = f" ({duration_sec:.1f}s)" if duration_sec else ""
        text = (
            f"✅ <b>Задача завершена</b>\n\n"
            f"📋 Task #{task_id}\n"
            f"📁 {project_name}\n"
            f"📱 {platform}{duration_str}"
        )
        await self.send_message(text)
    
    async def notify_task_error(
        self,
        task_id: int,
        project_name: str,
        platform: str,
        error_message: Optional[str] = None,
    ):
        """Notify when a task fails with error."""
        error_str = f"\n\n<code>{error_message[:200]}</code>" if error_message else ""
        text = (
            f"❌ <b>Ошибка задачи</b>\n\n"
            f"📋 Task #{task_id}\n"
            f"📁 {project_name}\n"
            f"📱 {platform}{error_str}"
        )
        await self.send_message(text)
    
    async def notify_moderation_required(
        self,
        task_id: int,
        project_name: str,
        step_name: str,
        step_index: int,
    ):
        """Notify when manual moderation is required."""
        text = (
            f"👁 <b>Требуется модерация</b>\n\n"
            f"📋 Task #{task_id}\n"
            f"📁 {project_name}\n"
            f"🔧 Шаг {step_index + 1}: {step_name}"
        )
        await self.send_message(text)
    
    async def notify_daily_summary(
        self,
        total_tasks: int,
        completed: int,
        errors: int,
        pending_moderation: int,
    ):
        """Send daily summary notification."""
        success_rate = (completed / total_tasks * 100) if total_tasks > 0 else 0
        text = (
            f"📊 <b>Итоги дня</b>\n\n"
            f"📝 Всего задач: {total_tasks}\n"
            f"✅ Завершено: {completed}\n"
            f"❌ Ошибок: {errors}\n"
            f"👁 На модерации: {pending_moderation}\n"
            f"📈 Успешность: {success_rate:.1f}%"
        )
        await self.send_message(text)


# Global singleton
telegram_notifier = TelegramNotifier()


async def notify_task_completed(task_id: int, project_name: str, platform: str, duration_sec: Optional[float] = None):
    """Convenience function to notify task completion."""
    await telegram_notifier.notify_task_completed(task_id, project_name, platform, duration_sec)


async def notify_task_error(task_id: int, project_name: str, platform: str, error_message: Optional[str] = None):
    """Convenience function to notify task error."""
    await telegram_notifier.notify_task_error(task_id, project_name, platform, error_message)


async def notify_moderation_required(task_id: int, project_name: str, step_name: str, step_index: int):
    """Convenience function to notify moderation required."""
    await telegram_notifier.notify_moderation_required(task_id, project_name, step_name, step_index)
