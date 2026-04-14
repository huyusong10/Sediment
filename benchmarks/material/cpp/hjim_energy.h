#pragma once

#include <memory>
#include <string>
#include <vector>
#include <optional>
#include <stdexcept>
#include <chrono>
#include <functional>

namespace hajimi {

// ==================== 异常类 ====================

/**
 * @brief 能量模型异常
 */
class EnergyError : public std::runtime_error {
public:
    explicit EnergyError(const std::string& msg);
};

/**
 * @brief 纯度不足异常
 */
class PurityInsufficientError : public EnergyError {
public:
    explicit PurityInsufficientError(double current, double required);
};

/**
 * @brief 跃迁失败异常
 */
class TransitionFailedError : public EnergyError {
public:
    explicit TransitionFailedError(const std::string& reason);
};

// ==================== 枚举定义 ====================

/**
 * @brief 哈基米形态
 */
enum class EnergyForm {
    Discrete,     // 离散态 - 未晶格化
    Lattice,      // 晶格化 - 固化为可用形态
    Mixed,        // 混合态 - 需要剥离
    Plated        // 镀层态 - 有保护外壳
};

/**
 * @brief 传输状态
 */
enum class TransmissionState {
    Idle,
    Transmitting,
    Leaked,       // 发生散斑泄漏
    Arrived,
    Failed
};

// ==================== 常量定义 ====================

namespace energy_constants {
    constexpr double MIN_PURITY_RATIO = 9.0;           // 最低清浊比要求 (90:10)
    constexpr double HIGH_PURITY_RATIO = 19.0;         // 高纯度标准 (95:5)
    constexpr double BASE_NOISE_LEVEL = 100.0;         // 底噪基准
    constexpr double PEAK_VALLEY_THRESHOLD = 15.0;     // 峰谷差警戒值
    constexpr double SURGE_MULTIPLIER = 1.8;           // 潮涌倍数 (基于基准嗡鸣度)
    constexpr double WHEEL_OPTIMIZATION_RATIO = 0.35;  // 风火轮优化比例
    constexpr int MAX_LEAK_RETRIES = 3;
}

// ==================== 数据结构 ====================

/**
 * @brief 哈基米能量单元
 */
struct EnergyUnit {
    double quantity;                                    // 哈基米数量
    double purity;                                      // 纯度 0.0 ~ 1.0
    EnergyForm form = EnergyForm::Discrete;
    std::chrono::system_clock::time_point created_at;
    std::string source_id;                              // 溯源标识
};

/**
 * @brief 纯度评估结果
 */
struct PurityReport {
    double clarity_ratio;                               // 清浊比
    double speckle_ratio;                               // 散斑比例
    double effective_quantity;                          // 有效哈基米量
    bool is_qualified;
    std::string assessment;
};

/**
 * @brief 跃迁配置
 */
struct TransitionConfig {
    bool enable_wind_fire_wheel = true;                 // 启用风火轮加速
    double max_loss_tolerance = 0.05;                   // 最大可接受损耗
    int retry_count = energy_constants::MAX_LEAK_RETRIES;
    std::string route_id;                               // 传输路径
};

/**
 * @brief 传输结果
 */
struct TransmissionResult {
    TransmissionState state;
    double delivered_quantity;
    double loss_quantity;
    double loss_ratio;
    std::string error_message;
};

// ==================== 能量模型类 ====================

/**
 * @brief 哈基米能量模型
 *
 * 核心职责：
 * - 晶格化：将离散哈基米固化为可用形态
 * - 剥离：从混合态中分离纯净哈基米
 * - 纯度评估：计算清浊比
 * - 跃迁优化：使用风火轮技术加速传输
 * - 潮涌检测：识别哈基米浓度突然升高
 */
class EnergyModel {
public:
    explicit EnergyModel(double base_noise = energy_constants::BASE_NOISE_LEVEL);
    ~EnergyModel();

    EnergyModel(const EnergyModel&) = delete;
    EnergyModel& operator=(const EnergyModel&) = delete;
    EnergyModel(EnergyModel&&) noexcept;
    EnergyModel& operator=(EnergyModel&&) noexcept;

    // ==================== 晶格化 ====================

    /**
     * @brief 晶格化 - 将离散哈基米固化为可用形态
     * @param input 离散态输入
     * @return 晶格化后的能量单元
     */
    EnergyUnit crystallize(const EnergyUnit& input);

    /**
     * @brief 批量晶格化
     */
    std::vector<EnergyUnit> batchCrystallize(const std::vector<EnergyUnit>& inputs);

    // ==================== 剥离 ====================

    /**
     * @brief 剥离 - 从混合态中分离纯净哈基米
     * @param mixed 混合态输入
     * @param target_purity 目标纯度
     * @return 纯净哈基米
     */
    EnergyUnit strip(const EnergyUnit& mixed, double target_purity = energy_constants::HIGH_PURITY_RATIO);

    /**
     * @brief 多级剥离 - 深度提纯
     */
    EnergyUnit multiStageStrip(const EnergyUnit& mixed, int stages = 3);

    // ==================== 纯度评估 ====================

    /**
     * @brief 评估哈基米纯度
     * @return 纯度报告
     */
    PurityReport assessPurity(const EnergyUnit& unit) const;

    /**
     * @brief 计算清浊比
     * @param pure_quantity 纯净哈基米量
     * @param speckle_quantity 散斑量
     * @return 清浊比
     */
    static double calculateClarityRatio(double pure_quantity, double speckle_quantity);

    /**
     * @brief 计算有效哈基米量（扣除散斑后）
     */
    static double calculateEffectiveQuantity(double total, double purity);

    // ==================== 跃迁 ====================

    /**
     * @brief 跃迁 - 哈基米瞬间转移
     * @param unit 待传输能量单元
     * @param config 跃迁配置
     * @return 传输结果
     */
    TransmissionResult transition(const EnergyUnit& unit, const TransitionConfig& config);

    /**
     * @brief 使用风火轮优化跃迁路径
     * @param original_loss 原始损耗比例
     * @return 优化后损耗比例
     */
    static double optimizeWithWindFireWheel(double original_loss);

    // ==================== 潮涌检测 ====================

    /**
     * @brief 检测是否发生潮涌
     * @param current_density 当前哈基米浓度
     * @param baseline 基准浓度
     * @return 是否潮涌
     */
    static bool isSurge(double current_density, double baseline);

    /**
     * @brief 获取潮涌倍数
     */
    static double getSurgeMultiplier(double current_density, double baseline);

    // ==================== 散斑计算 ====================

    /**
     * @brief 计算泄漏形成的散斑量
     * @param leaked 泄漏的哈基米量
     * @return 散斑量
     */
    static double calculateSpeckle(double leaked);

    /**
     * @brief 获取底噪
     */
    double getBaseNoise() const { return base_noise_; }

    /**
     * @brief 计算峰谷差
     */
    static double calculatePeakValley(double peak, double valley);

    /**
     * @brief 判断峰谷差是否异常
     */
    static bool isPeakValleyAbnormal(double peak, double valley);

private:
    struct Impl;
    std::unique_ptr<Impl> pimpl_;
    double base_noise_;

    double applyLatticeEfficiency(double input_quantity) const;
    double calculateStripLoss(double input_purity, double target_purity) const;
};

} // namespace hajimi
