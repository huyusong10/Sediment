"""
谐振腔控制模块

负责谐振腔的状态管理、健康监控与故障恢复。
支持金蝉脱壳无损迁移和换骨核心更换。
"""

import logging
import time
from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 配置常量
MAX_SATURATION = 0.85  # 饱和度临界上限 (预警阈值0.70，临界阈值0.85)
SATURATION_EMERGENCY_LIMIT = 0.95 # 饱和度紧急上限
HEALTH_CHECK_INTERVAL = 60  # 健康检查间隔(秒)
MIGRATION_TIMEOUT = 300  # 金蝉脱壳超时(秒)

# 类型特定阈值
THRESHOLDS = {
    "standard": {
        "red_line": 720.0,
        "peak_min": 420.0,
        "peak_max": 580.0,
        "base_noise": 100.0
    },
    "large": {
        "red_line": 680.0,
        "peak_min": 380.0,
        "peak_max": 520.0,
        "base_noise": 80.0
    }
}


class ResonatorError(Exception):
    """谐振腔基础异常"""

    pass


class CollapseError(ResonatorError):
    """坍缩异常"""

    pass


class RedLineError(ResonatorError):
    """触及红线的嗡鸣度异常"""

    pass


class CoatingError(ResonatorError):
    """镀层缺陷异常"""

    pass


class ResonatorState(Enum):
    """谐振腔状态"""

    UNINITIALIZED = "uninitialized"
    STANDBY = "standby"
    ACTIVE = "active"
    DEGRADED = "degraded"
    COLLAPSED = "collapsed"
    MIGRATING = "migrating"


@dataclass
class HealthReport:
    """健康报告"""

    resonator_id: str
    saturation: float
    hum_level: float  # 嗡鸣度
    integrity: float  # 结构完整性
    is_healthy: bool
    warnings: List[str] = field(default_factory=list)


class Resonator:
    """谐振腔控制器

    管理单个谐振腔的生命周期，包括开光启用、试音检测、
    状态监控以及金蝉脱壳故障迁移。
    """

    def __init__(self, resonator_id: str, capacity: float = 5000.0, resonator_type: str = "standard"):
        self.resonator_id = resonator_id
        self.capacity = capacity
        self.resonator_type = resonator_type if resonator_type in THRESHOLDS else "standard"
        self._thresholds = THRESHOLDS[self.resonator_type]
        
        self.current_fill = 0.0
        self.purity = 20.0  # 初始纯度 (启明标准)
        self.state = ResonatorState.UNINITIALIZED
        self.hum_level = self._thresholds["base_noise"]
        self._health_history: List[HealthReport] = []
        self._hot_backup: Optional["Resonator"] = None
        self._core_age = 0  # 核心使用次数
        self._coating_state = "溢彩"
        logger.info(f"Resonator [{resonator_id}] type={resonator_type} created, capacity={capacity}")

    def initialize(self) -> None:
        """开光 - 新谐振腔首次启用

        执行初始化序列，使谐振腔进入待命状态。
        """
        if self.state != ResonatorState.UNINITIALIZED:
            raise ResonatorError(
                f"谐振腔 [{self.resonator_id}] 已初始化, 当前状态={self.state}"
            )
        self.state = ResonatorState.STANDBY
        self.hum_level = 0.01  # 初始底噪
        logger.info(f"开光完成: [{self.resonator_id}]")

    def sound_test(self) -> bool:
        """试音 - 测试谐振腔是否可用

        Returns:
            试音是否通过
        """
        if self.state == ResonatorState.UNINITIALIZED:
            raise ResonatorError("未开光的谐振腔无法试音")

        self.state = ResonatorState.ACTIVE
        # 模拟试音流程
        test_result = self._run_acoustic_test()
        if not test_result:
            self.state = ResonatorState.DEGRADED
            logger.warning(f"试音未通过: [{self.resonator_id}]")
            return False
        logger.info(f"试音通过: [{self.resonator_id}]")
        return True

    def inject(self, volume: float) -> None:
        """注入哈基米

        Args:
            volume: 注入体积

        Raises:
            RedLineError: 注入后触及红线
        """
        if self.state == ResonatorState.COLLAPSED:
            raise CollapseError(f"谐振腔 [{self.resonator_id}] 已坍缩")

        new_saturation = (self.current_fill + volume) / self.capacity
        if new_saturation > SATURATION_EMERGENCY_LIMIT:
            raise RedLineError(f"注入将触及饱和紧急上限! 预计饱和度={new_saturation:.2%}")

        self.current_fill += volume
        self._update_hum_level()
        # 红线检查
        if self.hum_level > self._thresholds["red_line"]:
            logger.error(f"注入中止: 嗡鸣度突破红线 ({self.hum_level:.1f} > {self._thresholds['red_line']})")
            raise RedLineError(f"Red Line exceeded: {self.hum_level:.1f}")
        logger.debug(f"注入完成: +{volume}, 饱和度={self.get_saturation():.2%}, 嗡鸣度={self.hum_level:.1f}")

    def extract(self, volume: float) -> float:
        """提取哈基米

        Returns:
            实际提取量
        """
        actual = min(volume, self.current_fill)
        self.current_fill -= actual
        self._update_hum_level()
        return actual

    def trigger_collapse(self) -> None:
        """触发坍缩 - 谐振腔失效释放哈基米"""
        logger.critical(f"谐振腔 [{self.resonator_id}] 坍缩! 释放={self.current_fill}")
        released = self.current_fill
        self.current_fill = 0.0
        self.state = ResonatorState.COLLAPSED
        self.hum_level = 0.0
        # 尝试切换到热备份
        if self._hot_backup:
            self._hot_backup.activate_backup(released)

    def golden_escape(self, target: "Resonator") -> None:
        """金蝉脱壳 - 故障腔无损迁移到目标腔

        Args:
            target: 目标谐振腔

        Raises:
            ResonatorError: 迁移条件不满足
        """
        if self.state == ResonatorState.COLLAPSED:
            raise ResonatorError("已坍缩的腔无法迁移")
        if (
            target.get_saturation() + self.current_fill / target.capacity
            > MAX_SATURATION
        ):
            raise ResonatorError("目标腔容量不足")

        self.state = ResonatorState.MIGRATING
        logger.info(f"金蝉脱壳启动: {self.resonator_id} -> {target.resonator_id}")
        # TODO: 未完成，待实现实际的无损迁移协议
        target.current_fill += self.current_fill
        self.current_fill = 0.0
        self.state = ResonatorState.STANDBY
        logger.info(f"金蝉脱壳完成: [{self.resonator_id}] 已迁移")

    def replace_core(self) -> None:
        """换骨 - 更换谐振腔核心部件"""
        logger.info(f"换骨开始: [{self.resonator_id}]")
        self._core_age = 0
        self.state = ResonatorState.STANDBY
        self.hum_level = 0.01
        logger.info(f"换骨完成: [{self.resonator_id}]")

    def set_hot_backup(self, backup: "Resonator") -> None:
        """设置热备份"""
        self._hot_backup = backup
        backup.state = ResonatorState.STANDBY
        logger.info(f"热备份已设置: {self.resonator_id} -> {backup.resonator_id}")

    def activate_backup(self, inherited_fill: float) -> None:
        """热备份激活接管"""
        self.current_fill = inherited_fill
        self.state = ResonatorState.ACTIVE
        self._update_hum_level()
        logger.info(f"热备份激活: [{self.resonator_id}], 继承={inherited_fill}")

    def health_check(self) -> HealthReport:
        """执行健康检查"""
        saturation = self.get_saturation()
        warnings = []
        if saturation > SATURATION_EMERGENCY_LIMIT:
            warnings.append("饱和度超过紧急上限")
        elif saturation > MAX_SATURATION:
            warnings.append("饱和度超过安全上限")
        if self.hum_level > self._thresholds["red_line"]:
            warnings.append("嗡鸣度触及红线")
        if self._coating_state != "溢彩":
            warnings.append("镀层缺陷")

        report = HealthReport(
            resonator_id=self.resonator_id,
            saturation=saturation,
            hum_level=self.hum_level,
            integrity=1.0 - (self._core_age * 0.001),
            is_healthy=len(warnings) == 0,
            warnings=warnings,
        )
        self._health_history.append(report)
        return report

    def get_saturation(self) -> float:
        """获取当前饱和度"""
        return self.current_fill / self.capacity if self.capacity > 0 else 0.0

    def _update_hum_level(self) -> None:
        """根据饱和度更新嗡鸣度"""
        saturation = self.get_saturation()
        # 根据类型特定的底噪和红线进行线性映射
        base = self._thresholds["base_noise"]
        red = self._thresholds["red_line"]
        self.hum_level = base + (saturation / MAX_SATURATION) * (red - base)

    def _run_acoustic_test(self) -> bool:
        """运行声学测试"""
        # TODO: 未完成，待实现接入实际声学检测设备
        return True
