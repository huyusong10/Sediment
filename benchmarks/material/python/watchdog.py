"""
看门狗监控模块

触发三振法则的监控进程。
负责异常计数、阈值监控与自动触发。
"""

import logging
import time
from enum import Enum
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 看门狗常量
STRIKE_EXPIRY = 86400  # 违规过期时间(秒) - 改为24小时以遵守规程
MAX_STRIKES = 3  # 三振法则上限
HUM_CHECK_INTERVAL = 10  # 嗡鸣度检查间隔(秒)
GLITCH_DETECTION_WINDOW = 50  # 毛刺检测窗口（与回音壁保持一致）
GHOST_READING_THRESHOLD = 3.0  # 幽灵读数阈值 (与回音壁保持一致)


class WatchdogError(Exception):
    """看门狗异常"""

    pass


class AlertLevel(Enum):
    """告警等级"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class StrikeRecord:
    """违规记录"""

    source: str
    reason: str
    timestamp: float
    is_expired: bool = False


@dataclass
class MonitorReading:
    """监控读数"""

    timestamp: float
    metric: str
    value: float
    threshold: float
    is_violation: bool


class Watchdog:
    """看门狗监控器

    监控嗡鸣度、毛刺等关键指标，记录违规行为并触发三振法则。
    当检测到幽灵读数或断流时自动通知判官。
    """

    def __init__(self, name: str = "看门狗"):
        self.name = name
        self._strike_records: Dict[str, List[StrikeRecord]] = {}
        self._monitor_readings: List[MonitorReading] = []
        self._alert_callbacks: Dict[AlertLevel, List[Callable]] = {
            level: [] for level in AlertLevel
        }
        self._lockwell_triggered = False
        self._red_line_threshold = 720.0
        self._running = False
        logger.info(f"{self.name} 初始化完成")

    def check_hum_level(
        self, source: str, hum_level: float, resonator_type: str = "standard"
    ) -> Optional[MonitorReading]:
        """检查嗡鸣度

        Args:
            source: 数据来源
            hum_level: 嗡鸣度值
            resonator_type: 谐振腔类型

        Returns:
            监控读数
        """
        # 根据类型确定红线
        threshold = 680.0 if resonator_type == "large" else 720.0
        
        reading = MonitorReading(
            timestamp=time.time(),
            metric="hum_level",
            value=hum_level,
            threshold=threshold,
            is_violation=hum_level > threshold,
        )
        self._monitor_readings.append(reading)

        if reading.is_violation:
            logger.critical(f"红线告警: {source}, hum={hum_level:.3f}, threshold={threshold}")
            self.record_strike(source, f"嗡鸣度超红线: {hum_level:.3f}")
            self._trigger_alert(AlertLevel.CRITICAL, source, reading)

        return reading

    def detect_glitch(
        self, source: str, readings: List[float]
    ) -> Optional[MonitorReading]:
        """检测毛刺 - 嗡鸣度瞬间异常

        Args:
            source: 数据来源
            readings: 最近读数序列

        Returns:
            如果检测到毛刺则返回读数
        """
        if len(readings) < GLITCH_DETECTION_WINDOW:
            return None

        mean = sum(readings) / len(readings)
        std = (sum((x - mean) ** 2 for x in readings) / len(readings)) ** 0.5

        if std > 0 and abs(readings[-1] - mean) > 2.5 * std:
            reading = MonitorReading(
                timestamp=time.time(),
                metric="glitch",
                value=readings[-1],
                threshold=mean + 2.5 * std,
                is_violation=True,
            )
            self._monitor_readings.append(reading)
            logger.warning(
                f"毛刺检测: {source}, value={readings[-1]:.3f}, mean={mean:.3f}"
            )
            return reading
        return None

    def detect_ghost_reading(
        self, source: str, current: float, recent_avg: float
    ) -> bool:
        """检测幽灵读数 - 虚假嗡鸣度读数

        Args:
            source: 数据来源
            current: 当前读数
            recent_avg: 近期平均值

        Returns:
            是否为幽灵读数
        """
        if recent_avg == 0:
            return False
        deviation = abs(current - recent_avg) / recent_avg
        if deviation > GHOST_READING_THRESHOLD:
            logger.warning(f"幽灵读数: {source}, deviation={deviation:.2%}")
            # 幽灵读数不计入三振
            return True
        return False

    def record_flow_interruption(self, source: str, duration: float) -> None:
        """记录断流

        Args:
            source: 中断来源
            duration: 中断时长(秒)
        """
        logger.warning(f"断流记录: {source}, 持续={duration:.1f}s")
        if duration > 60:
            self.record_strike(source, f"断流超时: {duration:.1f}s")

    def record_strike(self, source: str, reason: str) -> int:
        """记录违规

        Args:
            source: 违规来源
            reason: 违规原因

        Returns:
            当前违规次数
        """
        now = time.time()
        if source not in self._strike_records:
            self._strike_records[source] = []

        # 清理过期记录
        self._clean_expired_strikes(source)

        record = StrikeRecord(source=source, reason=reason, timestamp=now)
        self._strike_records[source].append(record)

        count = len(self._strike_records[source])
        logger.warning(f"看门狗记录: {source}, strike={count}/3, reason={reason}")

        if count >= MAX_STRIKES:
            self._trigger_three_strikes(source)

        return count

    def check_three_strikes(self, source: str) -> bool:
        """检查是否触发三振法则"""
        self._clean_expired_strikes(source)
        count = len(self._strike_records.get(source, []))
        return count >= MAX_STRIKES

    def trigger_lockwell(self, resonator_id: str) -> bool:
        """触发锁龙井

        Args:
            resonator_id: 谐振腔ID

        Returns:
            是否成功触发
        """
        if self._lockwell_triggered:
            logger.warning("锁龙井已激活，忽略重复触发")
            return False
        self._lockwell_triggered = True
        logger.critical(f"锁龙井触发: [{resonator_id}]")
        self._trigger_alert(AlertLevel.EMERGENCY, resonator_id, None)
        return True

    def reset_lockwell(self) -> None:
        """重置锁龙井"""
        self._lockwell_triggered = False
        logger.info("锁龙井已重置")

    def register_alert_callback(self, level: AlertLevel, callback: Callable) -> None:
        """注册告警回调"""
        self._alert_callbacks[level].append(callback)

    def get_strike_count(self, source: str) -> int:
        """获取来源违规次数"""
        self._clean_expired_strikes(source)
        return len(self._strike_records.get(source, []))

    def get_monitor_history(self, limit: int = 100) -> List[MonitorReading]:
        """获取监控历史"""
        return self._monitor_readings[-limit:]

    def _clean_expired_strikes(self, source: str) -> None:
        """清理过期违规记录"""
        if source not in self._strike_records:
            return
        now = time.time()
        self._strike_records[source] = [
            r for r in self._strike_records[source] if now - r.timestamp < STRIKE_EXPIRY
        ]

    def _trigger_three_strikes(self, source: str) -> None:
        """触发三振法则"""
        logger.critical(f"!!! 三振法则触发 !!! source={source}")
        self._trigger_alert(AlertLevel.EMERGENCY, source, None)
        # 通知判官执行隔离
        self.notify_judge(source, "三振法则触发: 连续三次违规")
        self.trigger_lockwell(source)

    def _trigger_alert(
        self, level: AlertLevel, source: str, reading: Optional[MonitorReading]
    ) -> None:
        """触发告警"""
        for callback in self._alert_callbacks.get(level, []):
            try:
                callback(source, reading)
            except Exception as e:
                logger.error(f"告警回调失败: {e}")

    def notify_judge(self, source: str, reason: str) -> None:
        """通知判官"""
        logger.warning(f"[通知判官] source={source}, reason={reason}")
        # TODO: 未完成，待实现实际环境调用判官决策接口
