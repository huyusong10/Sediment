"""
潮涌检测模块

负责潮涌预测、检测与应急响应触发。
支持假涌识别、引雷针引导与泄洪决策。
"""

import logging
import time
import math
from enum import Enum
from typing import Optional, List, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 潮涌常量
SURGE_PREDICTION_WINDOW = 600  # 预测窗口(秒)
SURGE_THRESHOLD_MULTIPLIER = 1.8  # 潮涌阈值倍数 (基于基准嗡鸣度)
FALSE_SURGE_CONFIDENCE = 0.7  # 假涌置信度阈值
EMERGENCY_RESPONSE_DELAY = 5  # 应急响应延迟(秒)
MAX_SURGE_RECORDS = 5000


class SurgeLevel(Enum):
    """潮涌等级"""

    NORMAL = "normal"
    WATCH = "watch"  # 观察
    WARNING = "warning"  # 警告
    CRITICAL = "critical"  # 危急


class SurgeDetectorError(Exception):
    """潮涌检测异常"""

    pass


@dataclass
class SurgeEvent:
    """潮涌事件"""

    event_id: str
    level: SurgeLevel
    intensity: float
    timestamp: float
    is_false_surge: bool = False
    response_triggered: bool = False


@dataclass
class SurgePrediction:
    """潮涌预测"""

    probability: float
    estimated_time: float  # 预计发生时间
    estimated_intensity: float
    confidence: float


class TidalSurgeDetector:
    """潮涌检测器

    实时监测哈基米浓度变化，预测潮涌发生。
    通过回音壁嗡鸣度数据辅助判断，协调引雷针与泄洪。
    """

    def __init__(
        self,
        base_level: float,
        red_line: float,
        surge_threshold: Optional[float] = None,
    ):
        self.base_level = base_level
        self.red_line = red_line
        self.surge_threshold = surge_threshold or (
            base_level * SURGE_THRESHOLD_MULTIPLIER
        )
        self._readings: List[float] = []
        self._timestamps: List[float] = []
        self._surge_events: List[SurgeEvent] = []
        self._prediction_callbacks: List[Callable] = []
        self._lightning_rod_active = False
        logger.info(
            f"TidalSurgeDetector initialized: "
            f"base={base_level}, threshold={self.surge_threshold}"
        )

    def record_reading(self, hum_level: float) -> Optional[SurgeEvent]:
        """记录嗡鸣度读数并检测潮涌

        Args:
            hum_level: 当前嗡鸣度

        Returns:
            如果检测到潮涌则返回事件，否则为None
        """
        now = time.time()
        self._readings.append(hum_level)
        self._timestamps.append(now)

        # 保持窗口大小
        cutoff = now - SURGE_PREDICTION_WINDOW
        while self._timestamps and self._timestamps[0] < cutoff:
            self._readings.pop(0)
            self._timestamps.pop(0)

        event = self._evaluate_surge(hum_level, now)
        if event:
            self._surge_events.append(event)
            logger.warning(
                f"潮涌检测: level={event.level.value}, intensity={event.intensity:.2f}"
            )
        return event

    def predict_surge(self) -> Optional[SurgePrediction]:
        """预测潮涌

        基于历史数据趋势预测潮涌概率。

        Returns:
            预测结果，无显著趋势则返回None
        """
        if len(self._readings) < 10:
            return None

        # 简单线性趋势分析
        recent = self._readings[-20:]
        if len(recent) < 10:
            return None

        trend = self._calculate_trend(recent)
        if trend <= 0:
            return None

        # 外推预测
        current = recent[-1]
        steps_to_threshold = (
            (self.surge_threshold - current) / trend if trend > 0 else float("inf")
        )

        if steps_to_threshold < 60:  # 1分钟内可能触及阈值
            probability = min(1.0, 1.0 - (steps_to_threshold / 60))
            return SurgePrediction(
                probability=probability,
                estimated_time=time.time() + steps_to_threshold,
                estimated_intensity=current + trend * 30,
                confidence=min(0.9, len(recent) / 50.0),
            )
        return None

    def activate_lightning_rod(self) -> None:
        """激活引雷针 - 引导潮涌能量

        在预测到潮涌时提前激活，分散过量哈基米。
        """
        self._lightning_rod_active = True
        logger.info("引雷针已激活")

    def deactivate_lightning_rod(self) -> None:
        """停用引雷针"""
        self._lightning_rod_active = False
        logger.info("引雷针已停用")

    def register_prediction_callback(
        self, callback: Callable[[SurgePrediction], None]
    ) -> None:
        """注册预测回调"""
        self._prediction_callbacks.append(callback)

    def trigger_flood_release(self, volume: float) -> bool:
        """触发泄洪 - 紧急释放过量哈基米

        由判官决策后执行。

        Args:
            volume: 释放体积

        Returns:
            是否成功执行
        """
        if volume <= 0:
            return False
        logger.critical(f"泄洪触发: 释放={volume}")
        # 模拟泄洪过程
        if self._readings:
            self._readings[-1] = max(self.base_level, self._readings[-1] - volume * 0.1)
        return True

    def get_current_level(self) -> SurgeLevel:
        """获取当前潮涌等级"""
        if not self._readings:
            return SurgeLevel.NORMAL
        current = self._readings[-1]
        if current >= self.red_line:
            return SurgeLevel.CRITICAL
        elif current >= self.surge_threshold:
            return SurgeLevel.WARNING
        elif current >= self.surge_threshold * 0.8:
            return SurgeLevel.WATCH
        return SurgeLevel.NORMAL

    def _evaluate_surge(
        self, hum_level: float, timestamp: float
    ) -> Optional[SurgeEvent]:
        """评估是否发生潮涌"""
        if hum_level < self.base_level * 1.5:
            return None

        intensity = hum_level / self.base_level
        # 判断是否为假涌
        is_false = self._is_false_surge(hum_level)

        if intensity >= SURGE_THRESHOLD_MULTIPLIER:
            level = SurgeLevel.CRITICAL
        elif intensity >= 1.5:
            level = SurgeLevel.WARNING
        else:
            level = SurgeLevel.WATCH

        return SurgeEvent(
            event_id=f"SURGE-{int(timestamp)}",
            level=level,
            intensity=intensity,
            timestamp=timestamp,
            is_false_surge=is_false,
        )

    def _is_false_surge(self, hum_level: float) -> bool:
        """判断是否为假涌

        假涌特征: 单点突增但前后读数正常。
        """
        if len(self._readings) < 3:
            return False
        prev_avg = sum(self._readings[-3:-1]) / 2
        return hum_level > prev_avg * 3 and len(self._readings) >= 5

    def _calculate_trend(self, values: List[float]) -> float:
        """计算趋势斜率"""
        if len(values) < 2:
            return 0.0
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        return numerator / denominator if denominator > 0 else 0.0
