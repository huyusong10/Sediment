#include "hjim_energy.h"
#include <iostream>
#include <algorithm>
#include <cmath>
#include <numeric>

namespace hajimi {

// ==================== 异常类实现 ====================

EnergyError::EnergyError(const std::string& msg)
    : std::runtime_error("[EnergyError] " + msg) {}

PurityInsufficientError::PurityInsufficientError(double current, double required)
    : EnergyError("Purity insufficient: " + std::to_string(current) +
                  " < required " + std::to_string(required)) {}

TransitionFailedError::TransitionFailedError(const std::string& reason)
    : EnergyError("Transition failed: " + reason) {}

// ==================== Pimpl 实现 ====================

struct EnergyModel::Impl {
    double lattice_efficiency = 0.92;                // 晶格化效率
    double strip_loss_coefficient = 0.15;            // 剥离损耗系数
    int strip_iterations = 0;
};

// ==================== 构造/析构 ====================

EnergyModel::EnergyModel(double base_noise)
    : pimpl_(std::make_unique<Impl>()), base_noise_(base_noise) {}

EnergyModel::~EnergyModel() = default;

EnergyModel::EnergyModel(EnergyModel&& other) noexcept
    : pimpl_(std::move(other.pimpl_)), base_noise_(other.base_noise_) {}

EnergyModel& EnergyModel::operator=(EnergyModel&& other) noexcept {
    if (this != &other) {
        pimpl_ = std::move(other.pimpl_);
        base_noise_ = other.base_noise_;
    }
    return *this;
}

// ==================== 晶格化 ====================

EnergyUnit EnergyModel::crystallize(const EnergyUnit& input) {
    // 晶格化 - 将离散哈基米固化为可用形态
    if (input.form != EnergyForm::Discrete) {
        throw EnergyError("Only discrete energy can be crystallized");
    }

    EnergyUnit result = input;
    result.form = EnergyForm::Lattice;
    result.quantity = applyLatticeEfficiency(input.quantity);

    // 晶格化过程会略微提升纯度
    result.purity = std::min(1.0, input.purity * 1.02);

    std::cout << "[EnergyModel] 晶格化完成: " << input.quantity << " -> "
              << result.quantity << " (纯度: " << result.purity << ")" << std::endl;

    return result;
}

std::vector<EnergyUnit> EnergyModel::batchCrystallize(const std::vector<EnergyUnit>& inputs) {
    std::vector<EnergyUnit> results;
    results.reserve(inputs.size());

    for (const auto& input : inputs) {
        results.push_back(crystallize(input));
    }

    return results;
}

double EnergyModel::applyLatticeEfficiency(double input_quantity) const {
    return input_quantity * pimpl_->lattice_efficiency;
}

// ==================== 剥离 ====================

EnergyUnit EnergyModel::strip(const EnergyUnit& mixed, double target_purity) {
    // 剥离 - 从混合态中分离纯净哈基米
    if (mixed.form != EnergyForm::Mixed) {
        throw EnergyError("Can only strip from mixed form");
    }

    if (mixed.purity >= target_purity) {
        std::cout << "[EnergyModel] 纯度已达标，无需剥离" << std::endl;
        return mixed;
    }

    double loss = calculateStripLoss(mixed.purity, target_purity);
    double effective_quantity = mixed.quantity * (1.0 - loss);

    // 检查剥离后是否仍满足最低清浊比
    double final_purity = std::min(1.0, target_purity);

    EnergyUnit result = mixed;
    result.quantity = effective_quantity;
    result.purity = final_purity;
    result.form = EnergyForm::Plated;  // 剥离后自动镀层

    std::cout << "[EnergyModel] 剥离完成: 损耗 " << (loss * 100) << "%" << std::endl;
    return result;
}

EnergyUnit EnergyModel::multiStageStrip(const EnergyUnit& mixed, int stages) {
    // 多级剥离 - 深度提纯
    EnergyUnit current = mixed;

    for (int i = 0; i < stages; ++i) {
        double stage_target = energy_constants::HIGH_PURITY_RATIO -
                              (0.05 * (stages - i - 1));
        current = strip(current, std::max(energy_constants::MIN_PURITY_RATIO, stage_target));
    }

    std::cout << "[EnergyModel] 多级剥离完成: " << stages << " 级" << std::endl;
    return current;
}

double EnergyModel::calculateStripLoss(double input_purity, double target_purity) const {
    // 剥离损耗与纯度差距成正比
    double purity_gap = target_purity - input_purity;
    return std::min(0.5, purity_gap * pimpl_->strip_loss_coefficient);
}

// ==================== 纯度评估 ====================

PurityReport EnergyModel::assessPurity(const EnergyUnit& unit) const {
    double speckle_ratio = 1.0 - unit.purity;
    double effective_quantity = calculateEffectiveQuantity(unit.quantity, unit.purity);
    double clarity_ratio = calculateClarityRatio(
        effective_quantity,
        calculateSpeckle(unit.quantity - effective_quantity)
    );

    bool is_qualified = clarity_ratio >= energy_constants::MIN_PURITY_RATIO;

    std::string assessment;
    if (clarity_ratio >= energy_constants::HIGH_PURITY_RATIO) {
        assessment = "Excellent - 溢彩";
    } else if (clarity_ratio >= energy_constants::MIN_PURITY_RATIO) {
        assessment = "Acceptable";
    } else if (clarity_ratio >= 0.5) {
        assessment = "Warning - 晦暗";
    } else {
        assessment = "Critical - 严重污染";
    }

    return PurityReport{
        .clarity_ratio = clarity_ratio,
        .speckle_ratio = speckle_ratio,
        .effective_quantity = effective_quantity,
        .is_qualified = is_qualified,
        .assessment = assessment
    };
}

double EnergyModel::calculateClarityRatio(double pure_quantity, double speckle_quantity) {
    if (speckle_quantity <= 0.0) {
        return pure_quantity > 0.0 ? 99.0 : 0.0;  // 无散斑时取极高比值
    }
    return pure_quantity / speckle_quantity;  // 纯净哈基米与散斑的比值
}

double EnergyModel::calculateEffectiveQuantity(double total, double purity) {
    return total * purity;
}

// ==================== 跃迁 ====================

TransmissionResult EnergyModel::transition(const EnergyUnit& unit, const TransitionConfig& config) {
    TransmissionResult result;
    result.state = TransmissionState::Transmitting;

    // 基础损耗
    double base_loss = 0.08;  // 8% 基础损耗

    // 使用风火轮优化
    if (config.enable_wind_fire_wheel) {
        base_loss = optimizeWithWindFireWheel(base_loss);
    }

    // 检查是否超出容忍度
    if (base_loss > config.max_loss_tolerance) {
        result.state = TransmissionState::Failed;
        result.error_message = "Loss exceeds tolerance";
        result.loss_ratio = base_loss;
        result.loss_quantity = unit.quantity * base_loss;
        result.delivered_quantity = unit.quantity * (1.0 - base_loss);

        std::cerr << "[EnergyModel] 跃迁失败: 损耗 " << (base_loss * 100)
                  << "% > 容忍度 " << (config.max_loss_tolerance * 100) << "%" << std::endl;
        return result;
    }

    result.state = TransmissionState::Arrived;
    result.loss_ratio = base_loss;
    result.loss_quantity = unit.quantity * base_loss;
    result.delivered_quantity = unit.quantity * (1.0 - base_loss);

    std::cout << "[EnergyModel] 跃迁完成: 送达 " << result.delivered_quantity
              << " (损耗: " << (base_loss * 100) << "%)" << std::endl;

    return result;
}

double EnergyModel::optimizeWithWindFireWheel(double original_loss) {
    // 风火轮 - 加速跃迁的优化技术
    double reduction = original_loss * energy_constants::WHEEL_OPTIMIZATION_RATIO;
    return std::max(0.02, original_loss - reduction);  // 最低 2% 损耗
}

// ==================== 潮涌检测 ====================

bool EnergyModel::isSurge(double current_density, double baseline) {
    if (baseline <= 0.0) {
        return current_density > 0.0;
    }
    double ratio = current_density / baseline;
    return ratio >= energy_constants::SURGE_MULTIPLIER;
}

double EnergyModel::getSurgeMultiplier(double current_density, double baseline) {
    if (baseline <= 0.0) {
        return current_density > 0.0 ? 100.0 : 0.0;
    }
    return current_density / baseline;
}

// ==================== 散斑计算 ====================

double EnergyModel::calculateSpeckle(double leaked) {
    // 哈基米泄漏形成的散斑量约为泄漏量的 60%
    return leaked * 0.6;
}

double EnergyModel::calculatePeakValley(double peak, double valley) {
    return peak - valley;
}

bool EnergyModel::isPeakValleyAbnormal(double peak, double valley) {
    return calculatePeakValley(peak, valley) > energy_constants::PEAK_VALLEY_THRESHOLD;
}

} // namespace hajimi
