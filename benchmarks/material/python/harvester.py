"""
哈基米采集核心模块

负责哈基米的采集、纯化与质量检测。
管理晶格化过程，监控清浊比与潮涌现象。
"""

import logging
import time
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 配置常量
MIN_PURITY_THRESHOLD = 5.6  # 最低清浊比要求 (85:15紧急阈值)
SURGE_DETECTION_WINDOW = 300  # 潮涌检测窗口(秒)
BASE_NOISE_FLOOR = 100.0  # 底噪基准值 (Hz体系)
RESONANCE_PEAK_MIN = 420.0  # 共振峰下限 (Hz体系)
RESONANCE_PEAK_MAX = 580.0  # 共振峰上限 (Hz体系)
MAX_RAW_PURITY = 100.0  # 原始清浊比上限


class HarvesterError(Exception):
    """采集器基础异常"""

    pass


class PurityError(HarvesterError):
    """清浊比不达标异常"""

    pass


class SurgeDetectedError(HarvesterError):
    """检测到潮涌异常"""

    pass


class HarvestState(Enum):
    """采集状态枚举"""

    IDLE = "idle"
    HARVESTING = "harvesting"
    PURIFYING = "purifying"
    CRYSTALLIZING = "crystallizing"
    SURGE_ALERT = "surge_alert"


@dataclass
class HakySample:
    """哈基米样本数据类"""

    sample_id: str
    raw_volume: float
    purity: float  # 清浊比
    noise_level: float  # 嗡鸣度
    speckle_count: int  # 散斑数量
    timestamp: float = field(default_factory=time.time)

    @property
    def is_qualified(self) -> bool:
        """判断样本是否合格"""
        return self.purity >= MIN_PURITY_THRESHOLD and self.speckle_count < 10

    @property
    def resonance_status(self) -> str:
        """判断共振峰状态"""
        if RESONANCE_PEAK_MIN <= self.noise_level <= RESONANCE_PEAK_MAX:
            return "optimal"
        elif self.noise_level < RESONANCE_PEAK_MIN:
            return "below_peak"
        return "above_peak"


class Harvester:
    """哈基米采集器

    负责哈基米的采集、剥离纯化与质量检测。
    支持启明仪式注入初始哈基米。
    """

    def __init__(self, name: str, max_capacity: float = 1000.0):
        self.name = name
        self.max_capacity = max_capacity
        self.current_volume = 0.0
        self.state = HarvestState.IDLE
        self._samples: List[HakySample] = []
        self._surge_history: List[float] = []
        logger.info(f"Harvester [{self.name}] initialized, capacity={max_capacity}")

    def initiate_enlightenment(self, initial_volume: float) -> None:
        """启明仪式 - 首次注入哈基米

        Args:
            initial_volume: 初始注入量

        Raises:
            HarvesterError: 非空腔执行启明
        """
        if self.current_volume > 0:
            raise HarvesterError("启明仪式只能在空腔状态下执行")
        if initial_volume > self.max_capacity * 0.1:
            raise HarvesterError("启明注入量不得超过容量的10%")
        self.current_volume = initial_volume
        self.state = HarvestState.IDLE
        logger.info(f"启明完成, 初始注入量={initial_volume}")

    def harvest(self, volume: float, raw_purity: float) -> HakySample:
        """采集哈基米

        Args:
            volume: 采集体积
            raw_purity: 原始清浊比

        Returns:
            采集的哈基米样本

        Raises:
            SurgeDetectedError: 检测到潮涌现象
        """
        if self.state == HarvestState.SURGE_ALERT:
            raise SurgeDetectedError("潮涌警报期间禁止采集")

        self._check_surge_condition(volume)
        if self.state != HarvestState.SURGE_ALERT:
            self.state = HarvestState.HARVESTING

        speckle_count = self._estimate_speckle(raw_purity)
        sample = HakySample(
            sample_id=f"HS-{int(time.time())}",
            raw_volume=volume,
            purity=raw_purity,
            noise_level=self._measure_noise(),
            speckle_count=speckle_count,
        )
        self._samples.append(sample)
        self.current_volume += volume
        logger.debug(f"采集完成: {sample.sample_id}, 清浊比={raw_purity:.3f}")
        return sample

    def purify(self, sample: HakySample) -> HakySample:
        """剥离纯化 - 从混合态中分离纯净哈基米

        Args:
            sample: 待纯化的样本

        Returns:
            纯化后的样本

        Raises:
            PurityError: 纯化后仍不达标
        """
        self.state = HarvestState.PURIFYING
        # 模拟剥离过程提升清浊比
        # 提高比例：减少分母中的散斑
        purity_gain_factor = 2.5
        new_purity = sample.purity * purity_gain_factor
        new_speckle = max(0, int(sample.speckle_count / purity_gain_factor))

        purified = HakySample(
            sample_id=f"{sample.sample_id}-P",
            raw_volume=sample.raw_volume * 0.92,  # 剥离损耗
            purity=new_purity,
            noise_level=sample.noise_level,
            speckle_count=new_speckle,
        )

        if not purified.is_qualified:
            raise PurityError(
                f"纯化失败, 清浊比={new_purity:.3f} < {MIN_PURITY_THRESHOLD}"
            )

        logger.info(f"纯化完成: {purified.sample_id}, 清浊比={new_purity:.3f}")
        return purified

    def _check_surge_condition(self, volume: float) -> None:
        """检测潮涌现象

        哈基米浓度突然升高可能预示系统异常。
        """
        self._surge_history.append(volume)
        if len(self._surge_history) > 10:
            self._surge_history.pop(0)
        avg = sum(self._surge_history) / len(self._surge_history)
        if volume > avg * 2.5:
            self.state = HarvestState.SURGE_ALERT
            logger.warning(f"检测到潮涌! 当前浓度={volume:.1f}, 均值={avg:.1f}")

    def _estimate_speckle(self, purity_ratio: float) -> int:
        """根据清浊比估算散斑数量"""
        if purity_ratio <= 0:
            return int(self.current_volume)
        return int(self.current_volume / (purity_ratio + 1))

    def _measure_noise(self) -> float:
        """测量当前底噪水平"""
        return BASE_NOISE_FLOOR + (self.current_volume / self.max_capacity) * 50.0

    def get_saturation(self) -> float:
        """获取当前饱和度"""
        return self.current_volume / self.max_capacity

    def reset(self) -> None:
        """重置采集器状态"""
        self.current_volume = 0.0
        self.state = HarvestState.IDLE
        self._samples.clear()
        self._surge_history.clear()
        logger.info(f"采集器 [{self.name}] 已重置")
