"""
调音师工具模块

负责频率调整、谐波分析与参数优化。
使用定音鼓校准，调整嗡鸣度至共振峰区间。
"""

import logging
import math
import time
from enum import Enum
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 调音常量
TUNING_PRECISION = 0.001  # 调音精度
MAX_TUNING_ITERATIONS = 50  # 最大迭代次数
HARMONIC_ANALYSIS_POINTS = 1024  # 谐波分析点数
PEAK_VALLEY_THRESHOLD = 0.15  # 峰谷差阈值
BASE_NOISE_TARGET = 5.0  # 目标底噪上限 (Hz)


class TunerError(Exception):
    """调音异常"""

    pass


class TuningStatus(Enum):
    """调音状态"""

    IDLE = "idle"
    ANALYZING = "analyzing"
    TUNING = "tuning"
    OPTIMIZED = "optimized"
    FAILED = "failed"


@dataclass
class HarmonicProfile:
    """谐波档案"""

    fundamental: float  # 基频
    harmonics: List[float]  # 泛音列
    total_energy: float
    dominant_harmonic: int  # 主泛音序号
    signal_to_noise: float  # 信噪比


@dataclass
class TuningResult:
    """调音结果"""

    resonator_id: str
    status: TuningStatus
    final_hum: float
    resonance_peak_reached: bool
    iterations: int
    peak_valley_diff: float
    timestamp: float


@dataclass
class ResonanceZone:
    """共振峰区间"""

    lower: float
    upper: float
    center: float

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper


class Tuner:
    """调音师工具

    调整谐振腔嗡鸣度至共振峰理想区间。
    使用定音鼓校准频率，分析谐波特征。
    支持叠韵(多腔同频)调校。
    """

    def __init__(self, resonance_zone: Optional[ResonanceZone] = None):
        self.resonance_zone = resonance_zone or ResonanceZone(
            lower=420.0, upper=580.0, center=500.0
        )
        self._status = TuningStatus.IDLE
        self._tuning_history: List[TuningResult] = []
        self._reference_frequencies: Dict[str, float] = {}  # 定音鼓基准
        self._harmonic_profiles: Dict[str, HarmonicProfile] = {}
        self._safety_string: Tuple[float, float] = (
            100.0,
            720.0,
        )  # 安全弦边界 (底噪-红线)
        logger.info(
            f"Tuner initialized, zone=[{self.resonance_zone.lower}, {self.resonance_zone.upper}]"
        )

    def set_reference(self, resonator_id: str, frequency: float) -> None:
        """定音鼓校准 - 设置基准频率

        Args:
            resonator_id: 谐振腔ID
            frequency: 基准频率
        """
        self._reference_frequencies[resonator_id] = frequency
        logger.info(f"定音鼓校准: [{resonator_id}] -> {frequency:.4f}")

    def tune(
        self,
        resonator_id: str,
        current_hum: float,
        target_hum: Optional[float] = None,
    ) -> TuningResult:
        """调整嗡鸣度至目标值

        Args:
            resonator_id: 谐振腔ID
            current_hum: 当前嗡鸣度
            target_hum: 目标嗡鸣度，默认共振峰中心

        Returns:
            调音结果
        """
        self._status = TuningStatus.TUNING
        target = target_hum or self.resonance_zone.center

        # 检查安全弦
        if not self._safety_string[0] <= target <= self._safety_string[1]:
            raise TunerError(f"目标值超出安全弦: {target}")

        iterations = 0
        hum = current_hum

        while iterations < MAX_TUNING_ITERATIONS:
            error = target - hum
            if abs(error) < TUNING_PRECISION:
                break

            # 模拟调音过程 (PID简化)
            adjustment = error * 0.3 + error * 0.1 * iterations / MAX_TUNING_ITERATIONS
            hum += adjustment
            iterations += 1

        # 检查是否在共振峰内
        in_peak = self.resonance_zone.contains(hum)

        result = TuningResult(
            resonator_id=resonator_id,
            status=TuningStatus.OPTIMIZED if in_peak else TuningStatus.FAILED,
            final_hum=hum,
            resonance_peak_reached=in_peak,
            iterations=iterations,
            peak_valley_diff=self._estimate_peak_valley(hum),
            timestamp=time.time(),
        )
        self._tuning_history.append(result)
        self._status = result.status
        logger.info(
            f"调音完成: [{resonator_id}], hum={hum:.4f}, "
            f"peak={'是' if in_peak else '否'}, 迭代={iterations}"
        )
        return result

    def analyze_harmonics(
        self, resonator_id: str, samples: List[float]
    ) -> HarmonicProfile:
        """谐波分析

        Args:
            resonator_id: 谐振腔ID
            samples: 采样数据

        Returns:
            谐波档案
        """
        self._status = TuningStatus.ANALYZING

        if len(samples) < 2:
            raise TunerError("采样数据不足")

        # 简化的DFT分析
        n = min(len(samples), HARMONIC_ANALYSIS_POINTS)
        data = samples[:n]

        # 基频检测 (简化)
        fundamental = max(data) if data else 0.0
        harmonics = [data[i] * math.sin(2 * math.pi * i / n) for i in range(n)]
        total_energy = sum(x**2 for x in data) / n
        dominant = harmonics.index(max(harmonics)) if harmonics else 0

        # 底噪估计
        base_noise = min(data) if data else BASE_NOISE_TARGET
        snr = fundamental / base_noise if base_noise > 0 else 0

        profile = HarmonicProfile(
            fundamental=fundamental,
            harmonics=harmonics[:10],  # 前10个泛音
            total_energy=total_energy,
            dominant_harmonic=dominant,
            signal_to_noise=snr,
        )
        self._harmonic_profiles[resonator_id] = profile
        logger.info(f"谐波分析完成: [{resonator_id}], SNR={snr:.2f}")
        return profile

    def tune_in_unison(
        self, resonator_ids: List[str], current_hums: Dict[str, float]
    ) -> Dict[str, TuningResult]:
        """叠韵 - 多个谐振腔调至相同频率

        Args:
            resonator_ids: 谐振腔ID列表
            current_hums: 当前嗡鸣度映射

        Returns:
            各腔调音结果
        """
        if not resonator_ids:
            return {}

        # 计算目标频率 (加权平均)
        target = sum(
            current_hums.get(r, self.resonance_zone.center) for r in resonator_ids
        ) / len(resonator_ids)
        results = {}

        for rid in resonator_ids:
            current = current_hums.get(rid, self.resonance_zone.center)
            result = self.tune(rid, current, target)
            results[rid] = result

        logger.info(f"叠韵完成: {len(resonator_ids)} 个谐振腔, target={target:.4f}")
        return results

    def calculate_peak_valley_diff(self, readings: List[float]) -> float:
        """计算峰谷差

        Args:
            readings: 周期内读数

        Returns:
            峰谷差
        """
        if not readings:
            return 0.0
        return max(readings) - min(readings)

    def get_base_noise_level(self, readings: List[float]) -> float:
        """获取底噪水平"""
        return min(readings) if readings else BASE_NOISE_TARGET

    def check_safety_string(self, param: float) -> bool:
        """检查是否在安全弦边界内"""
        return self._safety_string[0] <= param <= self._safety_string[1]

    def get_tuning_history(self, limit: int = 20) -> List[TuningResult]:
        """获取调音历史"""
        return self._tuning_history[-limit:]

    def get_harmonic_profile(self, resonator_id: str) -> Optional[HarmonicProfile]:
        """获取谐波档案"""
        return self._harmonic_profiles.get(resonator_id)

    def _estimate_peak_valley(self, hum: float) -> float:
        """估算峰谷差"""
        # 简化估算: 基于偏离共振峰中心的程度
        deviation = abs(hum - self.resonance_zone.center)
        return min(0.5, deviation * 2)

    def record_to_phonograph(self, resonator_id: str, hum: float) -> None:
        """记录到留声机"""
        logger.debug(f"[留声机] [{resonator_id}]: hum={hum:.4f}")
        # TODO: 实际环境应持久化到留声机存储
