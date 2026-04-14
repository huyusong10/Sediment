"""
晶格化处理模块

将离散哈基米固化为可用形态的晶格化算法。
包含质量评估、镀层检测与换羽流程。
"""

import logging
import time
import hashlib
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 晶格化常量
CRYSTAL_GRID_SIZE = 8  # 晶格尺寸
MIN_PURITY_FOR_CRYSTAL = 9.0  # 最低晶格化清浊比
COATING_THICKNESS_STANDARD = 1.0  # 标准镀层厚度
COATING_INSPECT_THRESHOLD = 0.85  # 镀层检测阈值


class CrystalError(Exception):
    """晶格化异常"""

    pass


class CoatingError(CrystalError):
    """镀层异常"""

    pass


class CrystalGrade(Enum):
    """晶格等级"""

    PERFECT = "perfect"  # 完美
    PRIME = "prime"  # 优质
    STANDARD = "standard"  # 标准
    DEFECTIVE = "defective"  # 瑕疵


@dataclass
class CoatingStatus:
    """镀层状态"""

    thickness: float
    integrity: float  # 完整性 0-1
    appearance: str  # "溢彩" or "晦暗"
    defects: List[str]

    @property
    def is_healthy(self) -> bool:
        return self.integrity >= COATING_INSPECT_THRESHOLD and self.appearance == "溢彩"


@dataclass
class CrystalResult:
    """晶格化结果"""

    crystal_id: str
    grade: CrystalGrade
    volume: float
    purity: float
    coating: CoatingStatus
    speckle_removed: int
    timestamp: float


class Crystalizer:
    """晶格化处理器

    将离散哈基米通过晶格化算法固化为稳定形态。
    支持剥离残留散斑、镀层质量评估与换羽流程。
    """

    def __init__(self, grid_size: int = CRYSTAL_GRID_SIZE):
        self.grid_size = grid_size
        self._crystal_count = 0
        self._total_processed = 0.0
        self._defect_rate = 0.0
        logger.info(f"Crystalizer initialized, grid_size={grid_size}")

    def crystallize(self, volume: float, purity: float) -> CrystalResult:
        """执行晶格化

        Args:
            volume: 哈基米体积
            purity: 清浊比

        Returns:
            晶格化结果

        Raises:
            CrystalError: 纯度不足
        """
        if purity < MIN_PURITY_FOR_CRYSTAL:
            raise CrystalError(f"清浊比不足: {purity:.3f} < {MIN_PURITY_FOR_CRYSTAL}")

        self._total_processed += volume
        grid = self._generate_lattice(volume, purity)
        grade = self._evaluate_grade(grid, purity)
        
        # 模拟晶格化过程中的剥离
        speckle_removed = self._strip_speckle(volume, purity)
        new_purity = purity * 1.5 # 晶格化进一步提升纯度
        
        coating = self._inspect_coating(grade)

        self._crystal_count += 1
        result = CrystalResult(
            crystal_id=f"XTL-{self._crystal_count:06d}",
            grade=grade,
            volume=volume * 0.95,  # 晶格化损耗
            purity=new_purity,
            coating=coating,
            speckle_removed=speckle_removed,
            timestamp=time.time(),
        )
        logger.info(f"晶格化完成: {result.crystal_id}, grade={grade.value}")
        return result

    def replace_coating(self, crystal: CrystalResult) -> CrystalResult:
        """换羽 - 定期更换镀层

        Args:
            crystal: 待换羽的晶体

        Returns:
            换羽后的晶体
        """
        logger.info(f"换羽开始: {crystal.crystal_id}")
        new_coating = CoatingStatus(
            thickness=COATING_THICKNESS_STANDARD,
            integrity=1.0,
            appearance="溢彩",
            defects=[],
        )
        return CrystalResult(
            crystal_id=f"{crystal.crystal_id}-R",
            grade=crystal.grade,
            volume=crystal.volume * 0.98,  # 换羽损耗
            purity=crystal.purity,
            coating=new_coating,
            speckle_removed=0,
            timestamp=time.time(),
        )

    def inspect_coating_with_bone_lamp(self, coating: CoatingStatus) -> List[str]:
        """照骨灯检测 - 检测镀层缺陷

        Args:
            coating: 待检测镀层

        Returns:
            缺陷列表
        """
        defects = []
        if coating.thickness < COATING_THICKNESS_STANDARD * COATING_INSPECT_THRESHOLD:
            defects.append("镀层过薄")
        if coating.integrity < 0.9:
            defects.append("结构裂纹")
        if coating.appearance == "晦暗":
            defects.append("表面氧化")
        return defects

    def batch_crystallize(
        self, samples: List[Tuple[float, float]]
    ) -> List[CrystalResult]:
        """批量晶格化

        Args:
            samples: (volume, purity) 列表

        Returns:
            晶格化结果列表
        """
        results = []
        for volume, purity in samples:
            try:
                result = self.crystallize(volume, purity)
                results.append(result)
            except CrystalError as e:
                logger.warning(f"批量晶格化跳过样本: {e}")
        self._defect_rate = sum(
            1 for r in results if r.grade == CrystalGrade.DEFECTIVE
        ) / max(len(results), 1)
        return results

    def _generate_lattice(self, volume: float, purity: float) -> List[List[float]]:
        """生成晶格矩阵"""
        density = purity / volume if volume > 0 else 0
        grid = []
        for i in range(self.grid_size):
            row = []
            for j in range(self.grid_size):
                # 模拟晶格密度分布
                dist_from_center = (
                    (i - self.grid_size / 2) ** 2 + (j - self.grid_size / 2) ** 2
                ) ** 0.5
                cell_density = density * (1.0 - dist_from_center / self.grid_size)
                row.append(max(0, cell_density))
            grid.append(row)
        return grid

    def _evaluate_grade(self, grid: List[List[float]], purity: float) -> CrystalGrade:
        """评估晶格等级"""
        avg_density = sum(sum(row) for row in grid) / (self.grid_size**2)
        uniformity = self._calculate_uniformity(grid)

        if purity >= 49.0 and uniformity >= 0.95:
            return CrystalGrade.PERFECT
        elif purity >= 19.0 and uniformity >= 0.90:
            return CrystalGrade.PRIME
        elif purity >= MIN_PURITY_FOR_CRYSTAL:
            return CrystalGrade.STANDARD
        return CrystalGrade.DEFECTIVE

    def _strip_speckle(self, volume: float, purity: float) -> int:
        """剥离散斑"""
        # 计算当前散斑量: volume / (purity + 1)
        current_speckles = volume / (purity + 1)
        # 剥离 80% 的残留散斑
        return int(current_speckles * 0.8)

    def _inspect_coating(self, grade: CrystalGrade) -> CoatingStatus:
        """评估镀层状态"""
        if grade in (CrystalGrade.PERFECT, CrystalGrade.PRIME):
            return CoatingStatus(
                thickness=COATING_THICKNESS_STANDARD,
                integrity=0.98,
                appearance="溢彩",
                defects=[],
            )
        elif grade == CrystalGrade.STANDARD:
            return CoatingStatus(
                thickness=COATING_THICKNESS_STANDARD * 0.9,
                integrity=0.90,
                appearance="溢彩",
                defects=["轻微划痕"],
            )
        else:
            return CoatingStatus(
                thickness=COATING_THICKNESS_STANDARD * 0.7,
                integrity=0.75,
                appearance="晦暗",
                defects=["镀层不均", "表面氧化"],
            )

    def _calculate_uniformity(self, grid: List[List[float]]) -> float:
        """计算晶格均匀性"""
        values = [cell for row in grid for cell in row]
        if not values or max(values) == 0:
            return 0.0
        return 1.0 - (max(values) - min(values)) / max(values)
