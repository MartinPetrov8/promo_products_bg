"""
Database Monitoring and Alerts

Tracks database size and health, alerts when thresholds exceeded.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass

from .db import Database, get_db

logger = logging.getLogger(__name__)


@dataclass
class DBThresholds:
    """Alert thresholds for database monitoring."""
    # Size thresholds (in MB)
    size_warning_mb: float = 100.0      # Warn at 100MB
    size_critical_mb: float = 500.0     # Critical at 500MB
    size_migrate_mb: float = 1000.0     # Recommend PostgreSQL at 1GB
    
    # Growth rate thresholds (MB per day)
    growth_rate_warning: float = 10.0   # Warn if growing >10MB/day
    growth_rate_critical: float = 50.0  # Critical if >50MB/day
    
    # Table-specific thresholds
    price_history_max_rows: int = 1_000_000    # Max rows before archiving
    scrape_runs_max_days: int = 90             # Keep 90 days of scrape logs


@dataclass
class DBHealthReport:
    """Database health status report."""
    timestamp: datetime
    db_size_mb: float
    growth_rate_mb_day: Optional[float]
    table_counts: Dict[str, int]
    status: str  # healthy, warning, critical, migrate_recommended
    alerts: List[str]
    recommendations: List[str]


class DatabaseMonitor:
    """
    Monitors database size, growth, and health.
    Alerts when thresholds are exceeded.
    """
    
    def __init__(
        self,
        db: Optional[Database] = None,
        thresholds: Optional[DBThresholds] = None,
        alert_callback: Optional[Callable[[str, str, Dict], None]] = None
    ):
        self.db = db or get_db()
        self.thresholds = thresholds or DBThresholds()
        self.alert_callback = alert_callback
    
    def check_health(self) -> DBHealthReport:
        """Run full health check and return report."""
        now = datetime.utcnow()
        alerts = []
        recommendations = []
        status = "healthy"
        
        # Get current size
        size_mb = self.db.get_size_mb()
        
        # Get table counts
        table_counts = self.db.get_table_counts()
        
        # Calculate growth rate from metrics history
        growth_rate = self._calculate_growth_rate()
        
        # Check size thresholds
        if size_mb >= self.thresholds.size_migrate_mb:
            status = "migrate_recommended"
            alerts.append(f"🚨 DB size {size_mb:.1f}MB exceeds migration threshold ({self.thresholds.size_migrate_mb}MB)")
            recommendations.append("URGENT: Migrate to PostgreSQL for better performance")
        elif size_mb >= self.thresholds.size_critical_mb:
            status = "critical"
            alerts.append(f"🔴 DB size {size_mb:.1f}MB exceeds critical threshold ({self.thresholds.size_critical_mb}MB)")
            recommendations.append("Consider archiving old price_history data")
            recommendations.append("Run VACUUM to reclaim space")
        elif size_mb >= self.thresholds.size_warning_mb:
            status = "warning"
            alerts.append(f"⚠️ DB size {size_mb:.1f}MB exceeds warning threshold ({self.thresholds.size_warning_mb}MB)")
        
        # Check growth rate
        if growth_rate:
            if growth_rate >= self.thresholds.growth_rate_critical:
                if status == "healthy":
                    status = "critical"
                alerts.append(f"🔴 DB growing at {growth_rate:.1f}MB/day (critical threshold: {self.thresholds.growth_rate_critical}MB/day)")
                recommendations.append("Review scraping frequency")
                recommendations.append("Consider deduplication of price_history")
            elif growth_rate >= self.thresholds.growth_rate_warning:
                if status == "healthy":
                    status = "warning"
                alerts.append(f"⚠️ DB growing at {growth_rate:.1f}MB/day")
        
        # Check price_history size
        history_count = table_counts.get('price_history', 0)
        if history_count >= self.thresholds.price_history_max_rows:
            alerts.append(f"⚠️ price_history has {history_count:,} rows (threshold: {self.thresholds.price_history_max_rows:,})")
            recommendations.append("Archive old price history to separate table or file")
        
        # Build report
        report = DBHealthReport(
            timestamp=now,
            db_size_mb=size_mb,
            growth_rate_mb_day=growth_rate,
            table_counts=table_counts,
            status=status,
            alerts=alerts,
            recommendations=recommendations
        )
        
        # Record metrics
        self.db.record_metrics()
        
        # Trigger alerts if callback configured
        if alerts and self.alert_callback:
            for alert in alerts:
                self.alert_callback(
                    "database",
                    status,
                    {"alert": alert, "size_mb": size_mb, "growth_rate": growth_rate}
                )
        
        return report
    
    def _calculate_growth_rate(self) -> Optional[float]:
        """Calculate DB growth rate in MB/day from metrics history."""
        try:
            rows = self.db.fetchall("""
                SELECT db_size_bytes, recorded_at
                FROM db_metrics
                WHERE recorded_at >= datetime('now', '-7 days')
                ORDER BY recorded_at ASC
            """)
            
            if len(rows) < 2:
                return None
            
            oldest = rows[0]
            newest = rows[-1]
            
            size_diff_mb = (newest['db_size_bytes'] - oldest['db_size_bytes']) / (1024 * 1024)
            
            # Parse timestamps
            oldest_time = datetime.fromisoformat(oldest['recorded_at'])
            newest_time = datetime.fromisoformat(newest['recorded_at'])
            days_diff = (newest_time - oldest_time).total_seconds() / 86400
            
            if days_diff > 0:
                return size_diff_mb / days_diff
            return None
            
        except Exception as e:
            logger.warning(f"Failed to calculate growth rate: {e}")
            return None
    
    def get_summary(self) -> str:
        """Get human-readable health summary."""
        report = self.check_health()
        
        lines = [
            f"📊 Database Health Report",
            f"=" * 40,
            f"Status: {report.status.upper()}",
            f"Size: {report.db_size_mb:.2f} MB",
        ]
        
        if report.growth_rate_mb_day:
            lines.append(f"Growth Rate: {report.growth_rate_mb_day:.2f} MB/day")
        
        lines.append(f"\nTable Counts:")
        for table, count in sorted(report.table_counts.items()):
            lines.append(f"  {table}: {count:,}")
        
        if report.alerts:
            lines.append(f"\n⚠️ Alerts:")
            for alert in report.alerts:
                lines.append(f"  {alert}")
        
        if report.recommendations:
            lines.append(f"\n💡 Recommendations:")
            for rec in report.recommendations:
                lines.append(f"  • {rec}")
        
        return "\n".join(lines)
    
    def cleanup_old_data(self, days_to_keep: int = 90) -> Dict[str, int]:
        """
        Clean up old data to manage database size.
        
        Returns dict of deleted row counts.
        """
        results = {}
        cutoff = (datetime.utcnow() - timedelta(days=days_to_keep)).isoformat()
        
        # Clean old scrape_runs
        cursor = self.db.execute(
            "DELETE FROM scrape_runs WHERE started_at < ?",
            (cutoff,)
        )
        results['scrape_runs'] = cursor.rowcount
        
        # Clean old db_metrics
        cursor = self.db.execute(
            "DELETE FROM db_metrics WHERE recorded_at < ?",
            (cutoff,)
        )
        results['db_metrics'] = cursor.rowcount
        
        self.db.connect().commit()
        
        # Reclaim space
        self.db.vacuum()
        
        logger.info(f"Cleanup complete: {results}")
        return results
    
    def archive_price_history(self, archive_path: str, days_to_keep: int = 180) -> int:
        """
        Archive old price history to a separate file.
        
        Returns number of rows archived.
        """
        import json
        from pathlib import Path
        
        cutoff = (datetime.utcnow() - timedelta(days=days_to_keep)).isoformat()
        
        # Get old records
        rows = self.db.fetchall(
            "SELECT * FROM price_history WHERE recorded_at < ?",
            (cutoff,)
        )
        
        if not rows:
            return 0
        
        # Write to archive file
        archive_file = Path(archive_path)
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(archive_file, 'a', encoding='utf-8') as f:
            for row in rows:
                f.write(json.dumps(dict(row), ensure_ascii=False) + '\n')
        
        # Delete archived records
        cursor = self.db.execute(
            "DELETE FROM price_history WHERE recorded_at < ?",
            (cutoff,)
        )
        self.db.connect().commit()
        
        logger.info(f"Archived {len(rows)} price_history rows to {archive_path}")
        return len(rows)


# ============================================
# Migration Recommendations
# ============================================

MIGRATION_GUIDE = """
# SQLite to PostgreSQL Migration Guide

## When to Migrate
- Database size > 500MB
- Concurrent users > 10
- Need full-text search in Bulgarian
- Need advanced analytics queries

## Steps

1. Install PostgreSQL
   ```bash
   sudo apt install postgresql postgresql-contrib
   ```

2. Create database
   ```sql
   CREATE DATABASE promobg;
   CREATE USER promobg_user WITH PASSWORD 'your_password';
   GRANT ALL ON DATABASE promobg TO promobg_user;
   ```

3. Update schema for PostgreSQL
   - Change AUTOINCREMENT to SERIAL
   - Change TEXT datetime to TIMESTAMP
   - Add JSONB columns where noted
   - Add full-text search indexes

4. Migrate data using pgloader
   ```bash
   pgloader sqlite:///path/to/promobg.db postgresql://user:pass@localhost/promobg
   ```

5. Update connection string in config

## PostgreSQL Advantages
- Better concurrent read/write
- Full Bulgarian text search (tsvector)
- JSONB for structured data
- Table partitioning for price_history
- Advanced analytics functions
"""


def get_migration_guide() -> str:
    """Get PostgreSQL migration guide."""
    return MIGRATION_GUIDE
