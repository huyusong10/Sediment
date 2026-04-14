"""
清道夫流程模块

散斑清理与污染控制。
负责补天(大规模污染修复)、洗髓(深度清洁)等运维任务。
"""

import logging
import time
from enum import Enum
from typing import Optional, List, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 清道夫常量
CLEAN_CYCLE_INTERVAL = 300  # 清理周期(秒)
MAX_SPECKLE_DENSITY = 0.15  # 最大散斑密度
CLEANING_EFFICIENCY = 0.85  # 单次清理效率
REPAIR_THRESHOLD = 0.30  # 触发补天的污染阈值


class CleanerError(Exception):
    """清道夫异常"""

    pass


class PollutionLevel(Enum):
    """污染等级"""

    CLEAN = "clean"
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    CRITICAL = "critical"


@dataclass
class SpeckleCluster:
    """散斑簇"""

    cluster_id: str
    location: str
    density: float
    volume: float
    age: float  # 存在时间(秒)
    is_stable: bool


@dataclass
class CleanReport:
    """清理报告"""

    report_id: str
    pollution_level: PollutionLevel
    speckle_before: int
    speckle_after: int
    purity_before: float
    purity_after: float
    actions_taken: List[str]
    timestamp: float


class Cleaner:
    """清道夫系统

    由园丁团队运维，负责散斑清理、污染控制与健康恢复。
    支持补天(大规模修复)、八卦镜反射污染与洗髓(深度清洁)。
    """

    def __init__(self, zone_id: str):
        self.zone_id = zone_id
        self._speckle_clusters: Dict[str, SpeckleCluster] = {}
        self._clean_reports: List[CleanReport] = []
        self._purity_history: List[float] = []
        self._is_cleaning = False
        self._ba_gua_mirror_active = False
        logger.info(f"Cleaner [{zone_id}] initialized")

    def scan_pollution(self, current_purity: float) -> PollutionLevel:
        """扫描污染等级

        Args:
            current_purity: 当前清浊比

        Returns:
            污染等级
        """
        self._purity_history.append(current_purity)

        if current_purity >= 19.0:
            return PollutionLevel.CLEAN
        elif current_purity >= 9.0:
            return PollutionLevel.LIGHT
        elif current_purity >= 7.0:
            return PollutionLevel.MODERATE
        elif current_purity >= 5.6:
            return PollutionLevel.HEAVY
        return PollutionLevel.CRITICAL

    def register_speckle_cluster(self, cluster: SpeckleCluster) -> None:
        """登记散斑簇"""
        self._speckle_clusters[cluster.cluster_id] = cluster
        logger.info(f"登记散斑簇: {cluster.cluster_id}, density={cluster.density:.3f}")

    def execute_clean_cycle(self, current_purity: float) -> CleanReport:
        """执行清理周期

        Args:
            current_purity: 当前清浊比

        Returns:
            清理报告
        """
        if self._is_cleaning:
            raise CleanerError("清理任务进行中")

        self._is_cleaning = True
        pollution_level = self.scan_pollution(current_purity)
        actions = []
        speckle_before = self._count_total_speckle()

        try:
            if pollution_level in (PollutionLevel.HEAVY, PollutionLevel.CRITICAL):
                # 需要补天
                actions.append("触发补天流程")
                self._repair_heavy_pollution()

            if self._ba_gua_mirror_active:
                actions.append("八卦镜反射污染")
                self._reflect_speckle()

            # 常规清理
            cleaned_count = self._clean_speckle(pollution_level)
            actions.append(f"清理散斑: {cleaned_count} 簇")

            # 评估清理效果
            purity_after = self._estimate_purity_after_clean(
                current_purity, cleaned_count
            )

        finally:
            self._is_cleaning = False

        speckle_after = self._count_total_speckle()
        report = CleanReport(
            report_id=f"CLR-{int(time.time())}",
            pollution_level=pollution_level,
            speckle_before=speckle_before,
            speckle_after=speckle_after,
            purity_before=current_purity,
            purity_after=purity_after,
            actions_taken=actions,
            timestamp=time.time(),
        )
        self._clean_reports.append(report)
        logger.info(
            f"清理完成: {report.report_id}, {pollution_level.value} -> 清浊比={purity_after:.3f}"
        )
        return report

    def wash_marrows(self) -> float:
        """洗髓 - 深度清洁谐振腔

        Returns:
            清洁后的清浊比估计
        """
        logger.info("洗髓流程启动")
        # 模拟深度清洁
        removed = 0
        for cid in list(self._speckle_clusters.keys()):
            cluster = self._speckle_clusters[cid]
            if cluster.density > 0.05:
                removed += 1
                del self._speckle_clusters[cid]

        logger.info(f"洗髓完成: 移除 {removed} 个深层散斑簇")
        return (
            min(99.0, self._purity_history[-1] + 5.0) if self._purity_history else 19.0
        )

    def activate_ba_gua_mirror(self) -> None:
        """激活八卦镜 - 反射散斑污染"""
        self._ba_gua_mirror_active = True
        logger.info("八卦镜已激活")

    def deactivate_ba_gua_mirror(self) -> None:
        """停用八卦镜"""
        self._ba_gua_mirror_active = False
        logger.info("八卦镜已停用")

    def check_resonator_collapse_impact(self, resonator_id: str) -> Dict:
        """检查坍缩对区域的影响"""
        # 坍缩会产生大量散斑
        impact = {
            "resonator": resonator_id,
            "new_speckle_estimate": 50,
            "recommended_action": "补天",
        }
        logger.warning(
            f"坍缩影响评估: {resonator_id}, 预计产生散斑={impact['new_speckle_estimate']}"
        )
        return impact

    def _repair_heavy_pollution(self) -> None:
        """补天 - 修复大规模散斑污染"""
        logger.warning("补天流程启动")
        clusters_to_remove = [
            cid for cid, c in self._speckle_clusters.items() if c.density > 0.10
        ]
        for cid in clusters_to_remove:
            del self._speckle_clusters[cid]
        logger.info(f"补天完成: 移除 {len(clusters_to_remove)} 个重度污染簇")

    def _reflect_speckle(self) -> int:
        """八卦镜反射散斑"""
        reflected = 0
        for cid in list(self._speckle_clusters.keys()):
            if self._speckle_clusters[cid].is_stable:
                reflected += 1
                del self._speckle_clusters[cid]
        return reflected

    def _clean_speckle(self, level: PollutionLevel) -> int:
        """常规清理散斑"""
        if level == PollutionLevel.CLEAN:
            return 0

        cleaned = 0
        for cid in list(self._speckle_clusters.keys()):
            if self._speckle_clusters[cid].density < CLEANING_EFFICIENCY:
                del self._speckle_clusters[cid]
                cleaned += 1
        return cleaned

    def _count_total_speckle(self) -> int:
        """统计散斑簇数量"""
        return len(self._speckle_clusters)

    def _estimate_purity_after_clean(
        self, current_purity: float, cleaned_count: int
    ) -> float:
        """估算清理后的清浊比"""
        improvement = cleaned_count * 0.1
        return min(99.0, current_purity + improvement)

    def get_purity_trend(self) -> Optional[float]:
        """获取清浊比趋势"""
        if len(self._purity_history) < 2:
            return None
        return self._purity_history[-1] - self._purity_history[0]
