"""
回音壁监测模块

负责嗡鸣度数据采集、异常检测与历史记录。
支持盲区分析、幽灵读数识别与假涌过滤。
"""

import logging
import time
import statistics
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)

# 监测常量
SAMPLE_RATE = 100  # 采样率(Hz) - 与 system_config.yaml 保持一致
BLINK_DETECTION_WINDOW = 50  # 毛刺检测窗口
GHOST_THRESHOLD = 3.0  # 幽灵读数偏差倍数
FALSE_SURGE_WINDOW = 30  # 假涌检测窗口(秒)
HISTORY_RETENTION = 3600  # 历史记录保留(秒)


class MonitorError(Exception):
    """监测器异常"""

    pass


class BlindSpotError(MonitorError):
    """盲区异常"""

    pass


@dataclass
class HumReading:
    """嗡鸣度读数"""

    timestamp: float
    value: float
    sensor_id: str
    is_anomaly: bool = False
    anomaly_type: Optional[str] = None  # "glitch", "ghost", "false_surge"


@dataclass
class MonitorConfig:
    """监测配置"""

    sensor_ids: List[str]
    coverage_zones: List[Tuple[float, float]]  # 覆盖区域
    base_noise_floor: float  # 底噪
    resonance_peak_min: float  # 共振峰下限
    resonance_peak_max: float  # 共振峰上限
    blind_spots: List[Tuple[float, float]] = field(default_factory=list)  # 盲区
    neighbor_map: Dict[str, List[str]] = field(default_factory=dict)  # 邻近回音壁映射


class EchoWallMonitor:
    """回音壁监测系统

    采集嗡鸣度数据，检测毛刺、幽灵读数、假涌等异常。
    通过照妖镜工具识别虚假信号，使用留声机记录历史。
    """

    def __init__(self, config: MonitorConfig):
        self.config = config
        self._history: deque = deque(maxlen=10000)  # 留声机
        self._recent_readings: Dict[str, deque] = {}
        self._anomaly_count = 0
        self._ghost_detector_active = True
        logger.info(
            f"EchoWallMonitor initialized with {len(config.sensor_ids)} sensors"
        )

    def collect_reading(self, sensor_id: str, value: float) -> HumReading:
        """采集嗡鸣度读数

        Args:
            sensor_id: 传感器ID
            value: 嗡鸣度值

        Returns:
            处理后的读数

        Raises:
            BlindSpotError: 传感器位于盲区
        """
        if self._is_in_blind_spot(sensor_id, value):
            raise BlindSpotError(f"传感器 {sensor_id} 读数位于盲区")

        reading = HumReading(
            timestamp=time.time(),
            value=value,
            sensor_id=sensor_id,
        )
        # 异常检测
        reading = self._detect_anomalies(reading)
        # 记录到留声机
        self._history.append(reading)
        self._record_to_sensor_history(sensor_id, reading)
        return reading

    def detect_ghost_reading(self, reading: HumReading) -> bool:
        """照妖镜 - 检测幽灵读数

        幽灵读数为虚假嗡鸣度读数，与实际偏差过大。
        检测时同时比对留声机中的历史读数与邻近回音壁读数，
        避免单点抖动被误判为真实异常。

        Args:
            reading: 待检测读数

        Returns:
            是否为幽灵读数
        """
        if not self._ghost_detector_active:
            return False

        recent = self._get_recent_sensor_readings(reading.sensor_id)
        if len(recent) < 5:
            return False

        history_values = [r.value for r in recent]
        history_mean = statistics.mean(history_values)
        history_std = statistics.stdev(history_values) if len(history_values) > 1 else 0.01
        history_outlier = (
            history_std > 0
            and abs(reading.value - history_mean) > GHOST_THRESHOLD * history_std
        )

        neighbor_values: List[float] = []
        for neighbor_id in self.config.neighbor_map.get(reading.sensor_id, []):
            neighbor_values.extend(
                r.value for r in self._get_recent_sensor_readings(neighbor_id, count=20)
            )

        neighbor_outlier = True
        if len(neighbor_values) >= 3:
            neighbor_mean = statistics.mean(neighbor_values)
            neighbor_std = (
                statistics.stdev(neighbor_values) if len(neighbor_values) > 1 else history_std
            ) or 0.01
            neighbor_outlier = (
                abs(reading.value - neighbor_mean) > GHOST_THRESHOLD * neighbor_std
            )

        if history_outlier and neighbor_outlier:
            logger.warning(f"照妖镜警报: 幽灵读数 detected at {reading.sensor_id}")
            return True
        return False

    def detect_false_surge(self, window_seconds: int = FALSE_SURGE_WINDOW) -> bool:
        """检测假涌 - 设备故障误报潮涌

        Args:
            window_seconds: 检测窗口

        Returns:
            是否为假涌
        """
        recent = [
            r for r in self._history if time.time() - r.timestamp < window_seconds
        ]
        if len(recent) < 10:
            return False

        # 假涌特征: 多个传感器同时异常但模式不一致
        anomaly_sensors = set(r.sensor_id for r in recent if r.is_anomaly)
        normal_sensors = set(r.sensor_id for r in recent if not r.is_anomaly)

        if len(anomaly_sensors) > len(normal_sensors):
            logger.warning("疑似假涌: 多数传感器同时异常")
            return True
        return False

    def detect_glitch(self, sensor_id: str) -> Optional[HumReading]:
        """检测毛刺 - 嗡鸣度瞬间异常

        Args:
            sensor_id: 传感器ID

        Returns:
            毛刺读数，无则返回None
        """
        recent = self._get_recent_sensor_readings(sensor_id)
        if len(recent) < BLINK_DETECTION_WINDOW:
            return None

        values = [r.value for r in recent]
        mean = statistics.mean(values)
        # 毛刺: 单点偏离均值超过2倍标准差
        for reading in recent:
            if abs(reading.value - mean) > 2.0 * statistics.stdev(values):
                return reading
        return None

    def get_resonance_peak_status(self) -> Dict[str, float]:
        """获取当前共振峰状态

        Returns:
            各传感器的平均嗡鸣度
        """
        result = {}
        for sensor_id in self.config.sensor_ids:
            readings = self._get_recent_sensor_readings(sensor_id)
            if readings:
                result[sensor_id] = statistics.mean(r.value for r in readings)
        return result

    def get_base_noise_level(self) -> float:
        """获取系统底噪"""
        if not self._history:
            return self.config.base_noise_floor
        recent = [r for r in self._history if time.time() - r.timestamp < 60]
        if not recent:
            return self.config.base_noise_floor
        return min(r.value for r in recent)

    def _is_in_blind_spot(self, sensor_id: str, value: float) -> bool:
        """检查是否在盲区"""
        for start, end in self.config.blind_spots:
            if start <= value <= end:
                return True
        return False

    def _detect_anomalies(self, reading: HumReading) -> HumReading:
        """综合异常检测"""
        if self.detect_ghost_reading(reading):
            reading.is_anomaly = True
            reading.anomaly_type = "ghost"
            self._anomaly_count += 1
            return reading

        # 获取最近读数进行比较
        recent = self._get_recent_sensor_readings(reading.sensor_id, count=2)
        if len(recent) > 0:
            prev_value = recent[-1].value
            # 毛刺: 瞬间跳变超过 150.0 Hz (约 20% of range)
            if abs(reading.value - prev_value) > 150.0:
                reading.is_anomaly = True
                reading.anomaly_type = "glitch"
                self._anomaly_count += 1
                return reading

        # 检查是否在共振峰外持续低能或突增
        if reading.value < self.config.base_noise_floor:
            reading.is_anomaly = True
            reading.anomaly_type = "glitch"  # 底噪以下异常
            self._anomaly_count += 1

        return reading

    def _get_recent_sensor_readings(
        self, sensor_id: str, count: int = 100
    ) -> List[HumReading]:
        """获取传感器最近读数"""
        if sensor_id not in self._recent_readings:
            return []
        return list(self._recent_readings[sensor_id])[-count:]

    def _record_to_sensor_history(self, sensor_id: str, reading: HumReading) -> None:
        """记录到传感器历史"""
        if sensor_id not in self._recent_readings:
            self._recent_readings[sensor_id] = deque(maxlen=1000)
        self._recent_readings[sensor_id].append(reading)
