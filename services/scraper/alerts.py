"""
Alert System for Scraper Failures

Sends WhatsApp alerts when critical failures occur.
Uses OpenClaw's message tool for delivery.
"""

import json
import logging
from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertManager:
    """
    Manages alerts for scraper failures and health issues.
    
    Alert triggers:
    - Circuit breaker opens (store down)
    - All tiers failed (no data source)
    - Product count below threshold (possible selector breakage)
    - Consecutive failures > N
    """
    
    # Alert recipients
    DEFAULT_RECIPIENTS = [
        "+359885997747",  # Martin
    ]
    
    def __init__(
        self,
        recipients: Optional[List[str]] = None,
        min_alert_interval: int = 300,  # 5 minutes between same alert
    ):
        self.recipients = recipients or self.DEFAULT_RECIPIENTS
        self.min_alert_interval = min_alert_interval
        self.last_alerts: Dict[str, datetime] = {}
        
        # Stats
        self.alerts_sent = 0
        self.alerts_suppressed = 0
    
    def _should_alert(self, alert_key: str) -> bool:
        """Check if we should send this alert (debounce)."""
        now = datetime.utcnow()
        
        if alert_key in self.last_alerts:
            elapsed = (now - self.last_alerts[alert_key]).total_seconds()
            if elapsed < self.min_alert_interval:
                self.alerts_suppressed += 1
                return False
        
        self.last_alerts[alert_key] = now
        return True
    
    def _send_whatsapp(self, message: str) -> bool:
        """
        Send WhatsApp message via OpenClaw.
        
        Note: This is a placeholder. In production, this would use
        the OpenClaw message tool or a direct API call.
        """
        # Log the alert
        logger.warning(f"ALERT: {message}")
        
        # In production, this would call:
        # message(action="send", target=recipient, message=message)
        
        # For now, just log that we would send
        for recipient in self.recipients:
            logger.info(f"Would send WhatsApp to {recipient}: {message[:50]}...")
        
        self.alerts_sent += 1
        return True
    
    def alert_circuit_open(self, store_id: str, store_name: str):
        """Alert when a store's circuit breaker opens."""
        alert_key = f"circuit_open_{store_id}"
        
        if not self._should_alert(alert_key):
            return
        
        message = (
            f"⚠️ PromoBG Alert\n\n"
            f"Circuit breaker OPEN for {store_name}\n"
            f"Store scraper is failing repeatedly.\n\n"
            f"Action: Will use Tier 2 fallback (broshura.bg)"
        )
        
        self._send_whatsapp(message)
    
    def alert_all_tiers_failed(self, store_id: str, store_name: str):
        """Alert when all tiers fail for a store."""
        alert_key = f"all_failed_{store_id}"
        
        if not self._should_alert(alert_key):
            return
        
        message = (
            f"🚨 PromoBG CRITICAL\n\n"
            f"ALL TIERS FAILED for {store_name}\n"
            f"No data source available!\n\n"
            f"Action: Using cached data (may be stale)"
        )
        
        self._send_whatsapp(message)
    
    def alert_low_product_count(
        self,
        store_id: str,
        store_name: str,
        actual: int,
        expected: int
    ):
        """Alert when product count is suspiciously low."""
        alert_key = f"low_count_{store_id}"
        
        if not self._should_alert(alert_key):
            return
        
        percent = (actual / expected * 100) if expected > 0 else 0
        
        message = (
            f"⚠️ PromoBG Alert\n\n"
            f"Low product count for {store_name}\n"
            f"Got: {actual} | Expected: ≥{expected}\n"
            f"({percent:.0f}% of normal)\n\n"
            f"Possible: Selector change or site issue"
        )
        
        self._send_whatsapp(message)
    
    def alert_scrape_success(self, summary: Dict):
        """Send daily success summary (optional)."""
        total = sum(s.get('count', 0) for s in summary.values())
        
        stores_summary = "\n".join([
            f"• {store}: {data.get('count', 0)} products"
            for store, data in summary.items()
        ])
        
        message = (
            f"✅ PromoBG Daily Update\n\n"
            f"Total products scraped: {total}\n\n"
            f"{stores_summary}"
        )
        
        self._send_whatsapp(message)
    
    def get_stats(self) -> Dict:
        """Get alert statistics."""
        return {
            'alerts_sent': self.alerts_sent,
            'alerts_suppressed': self.alerts_suppressed,
            'last_alerts': {
                k: v.isoformat() for k, v in self.last_alerts.items()
            },
        }


# Global instance
alert_manager = AlertManager()


def send_alert(level: AlertLevel, title: str, message: str, store_id: Optional[str] = None):
    """Convenience function to send an alert."""
    alert_key = f"{level.value}_{title}_{store_id or 'global'}"
    
    if not alert_manager._should_alert(alert_key):
        return
    
    emoji = {
        AlertLevel.INFO: "ℹ️",
        AlertLevel.WARNING: "⚠️",
        AlertLevel.CRITICAL: "🚨",
    }[level]
    
    full_message = f"{emoji} PromoBG {level.value.upper()}\n\n{title}\n\n{message}"
    alert_manager._send_whatsapp(full_message)
