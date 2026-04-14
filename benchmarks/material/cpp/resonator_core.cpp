#include "resonator_core.h"
#include <iostream>
#include <algorithm>
#include <cmath>
#include <map>

namespace hajimi {

// ==================== 异常类实现 ====================

ResonatorError::ResonatorError(const std::string& msg)
    : std::runtime_error("[ResonatorError] " + msg) {}

StateTransitionError::StateTransitionError(const std::string& from, const std::string& to)
    : ResonatorError("Invalid state transition: " + from + " -> " + to) {}

SaturationOverflowError::SaturationOverflowError(double current, double limit)
    : ResonatorError("Saturation overflow: " + std::to_string(current) +
                     "% exceeds limit " + std::to_string(limit) + "%") {}

// ==================== 辅助函数 ====================

std::string stateToString(ResonatorState state) {
    switch (state) {
        case ResonatorState::Silent:       return "Silent";
        case ResonatorState::Warm:         return "Warm";
        case ResonatorState::Running:      return "Running";
        case ResonatorState::Collapsing:   return "Collapsing";
        case ResonatorState::Sealed:       return "Sealed";
        case ResonatorState::HotStandby:   return "HotStandby";
    }
    return "Unknown";
}

std::string healthToString(HealthLevel level) {
    switch (level) {
        case HealthLevel::Excellent:  return "Excellent";
        case HealthLevel::Good:       return "Good";
        case HealthLevel::Warning:    return "Warning";
        case HealthLevel::Critical:   return "Critical";
        case HealthLevel::Dead:       return "Dead";
    }
    return "Unknown";
}

// ==================== Pimpl 实现 ====================

struct ResonatorCore::Impl {
    ResonatorState current_state = ResonatorState::Silent;
    double hum_level = 0.0;
    double saturation = 0.0;
    HealthLevel health = HealthLevel::Excellent;
    bool is_locked = false;                          // 锁龙井锁定状态
    int retry_count = 0;                             // 三振法则计数
    std::chrono::system_clock::time_point last_state_change;
    std::string last_operation = "none";

    // 回调
    StateChangeCallback on_state_change;
    CollapseWarningCallback on_collapse_warning;

    // 热备份引用
    ResonatorCore* hot_standby_ref = nullptr;
};

// ==================== 构造/析构 ====================

ResonatorCore::ResonatorCore(const ResonatorConfig& config)
    : pimpl_(std::make_unique<Impl>()), config_(config) {
    pimpl_->last_state_change = std::chrono::system_clock::now();
}

ResonatorCore::~ResonatorCore() = default;

ResonatorCore::ResonatorCore(ResonatorCore&& other) noexcept
    : pimpl_(std::move(other.pimpl_)), config_(std::move(other.config_)) {}

ResonatorCore& ResonatorCore::operator=(ResonatorCore&& other) noexcept {
    if (this != &other) {
        pimpl_ = std::move(other.pimpl_);
        config_ = std::move(other.config_);
    }
    return *this;
}

// ==================== 状态验证 ====================

bool ResonatorCore::validateStateTransition(ResonatorState from, ResonatorState to) const {
    // 定义合法的状态转换图
    static const std::map<ResonatorState, std::vector<ResonatorState>> valid_transitions = {
        {ResonatorState::Silent,     {ResonatorState::Warm, ResonatorState::Running}},
        {ResonatorState::Warm,       {ResonatorState::Running, ResonatorState::Silent,
                                       ResonatorState::Sealed}},
        {ResonatorState::Running,    {ResonatorState::Warm, ResonatorState::Collapsing,
                                       ResonatorState::HotStandby}},
        {ResonatorState::Collapsing, {ResonatorState::Silent}},
        {ResonatorState::Sealed,     {ResonatorState::Silent}},
        {ResonatorState::HotStandby, {ResonatorState::Running, ResonatorState::Silent}}
    };

    auto it = valid_transitions.find(from);
    if (it == valid_transitions.end()) {
        return false;
    }

    const auto& allowed = it->second;
    return std::find(allowed.begin(), allowed.end(), to) != allowed.end();
}

void ResonatorCore::notifyStateChange(ResonatorState old_state, ResonatorState new_state) {
    pimpl_->last_state_change = std::chrono::system_clock::now();
    if (pimpl_->on_state_change) {
        pimpl_->on_state_change(old_state, new_state);
    }
}

void ResonatorCore::checkCollapseRisk() {
    if (pimpl_->hum_level >= config_.red_line * 0.9) {
        // 接近红线，发出警告
        if (pimpl_->on_collapse_warning) {
            pimpl_->on_collapse_warning(pimpl_->hum_level, config_.red_line);
        }
    }

    // 三振法则：连续三次异常则隔离
    if (pimpl_->hum_level > config_.red_line) {
        pimpl_->retry_count++;
        if (pimpl_->retry_count >= config_.max_retry_count) {
            std::cerr << "[ResonatorCore] 三振法则触发，准备隔离谐振腔: "
                      << config_.resonator_id << std::endl;
            emergencyLock();
            pimpl_->retry_count = 0;
        }
    } else {
        pimpl_->retry_count = 0;
    }
}

// ==================== 生命周期管理 ====================

bool ResonatorCore::tryConsecration() {
    // 开光 - 新谐振腔首次启用
    if (pimpl_->current_state != ResonatorState::Silent) {
        std::cerr << "[ResonatorCore] 开光失败: 谐振腔非静默态" << std::endl;
        return false;
    }

    pimpl_->last_operation = "consecration";
    pimpl_->hum_level = config_.warm_hum_threshold;
    pimpl_->saturation = 0.0;
    pimpl_->health = HealthLevel::Excellent;

    auto old_state = pimpl_->current_state;
    pimpl_->current_state = ResonatorState::Warm;
    notifyStateChange(old_state, pimpl_->current_state);

    std::cout << "[ResonatorCore] 开光成功: " << config_.resonator_id << std::endl;
    return true;
}

bool ResonatorCore::trySoundTest() {
    // 试音 - 测试谐振腔是否可用
    if (pimpl_->current_state != ResonatorState::Warm) {
        std::cerr << "[ResonatorCore] 试音失败: 谐振腔非温存态" << std::endl;
        return false;
    }

    pimpl_->last_operation = "sound_test";

    // 模拟试音过程：短暂提升到共振峰区间
    double test_hum = (config_.resonance_peak_min + config_.resonance_peak_max) / 2.0;
    pimpl_->hum_level = test_hum;

    bool is_healthy = (pimpl_->hum_level >= config_.resonance_peak_min &&
                       pimpl_->hum_level <= config_.resonance_peak_max);

    // 试音后恢复到温存态
    pimpl_->hum_level = config_.warm_hum_threshold;

    std::cout << "[ResonatorCore] 试音完成: " << (is_healthy ? "通过" : "失败") << std::endl;
    return is_healthy;
}

bool ResonatorCore::tryStartup() {
    if (!validateStateTransition(pimpl_->current_state, ResonatorState::Running)) {
        throw StateTransitionError(stateToString(pimpl_->current_state), "Running");
    }

    pimpl_->last_operation = "startup";
    auto old_state = pimpl_->current_state;
    pimpl_->current_state = ResonatorState::Running;
    pimpl_->hum_level = (config_.resonance_peak_min + config_.resonance_peak_max) / 2.0;
    pimpl_->retry_count = 0;

    notifyStateChange(old_state, pimpl_->current_state);
    return true;
}

bool ResonatorCore::tryShutdown() {
    if (!validateStateTransition(pimpl_->current_state, ResonatorState::Silent)) {
        throw StateTransitionError(stateToString(pimpl_->current_state), "Silent");
    }

    pimpl_->last_operation = "shutdown";
    auto old_state = pimpl_->current_state;
    pimpl_->current_state = ResonatorState::Silent;
    pimpl_->hum_level = 0.0;
    pimpl_->saturation = 0.0;

    notifyStateChange(old_state, pimpl_->current_state);
    return true;
}

bool ResonatorCore::trySeal() {
    // 封窖 - 长期存储哈基米的休眠模式
    if (!validateStateTransition(pimpl_->current_state, ResonatorState::Sealed)) {
        throw StateTransitionError(stateToString(pimpl_->current_state), "Sealed");
    }

    pimpl_->last_operation = "seal";
    auto old_state = pimpl_->current_state;
    pimpl_->current_state = ResonatorState::Sealed;
    pimpl_->is_locked = true;

    notifyStateChange(old_state, pimpl_->current_state);
    std::cout << "[ResonatorCore] 封窖完成: " << config_.resonator_id << std::endl;
    return true;
}

bool ResonatorCore::tryUnseal() {
    // 破窖 - 从封窖状态恢复
    if (pimpl_->current_state != ResonatorState::Sealed) {
        std::cerr << "[ResonatorCore] 破窖失败: 非封窖状态" << std::endl;
        return false;
    }

    pimpl_->last_operation = "unseal";
    auto old_state = pimpl_->current_state;
    pimpl_->current_state = ResonatorState::Silent;
    pimpl_->is_locked = false;

    notifyStateChange(old_state, pimpl_->current_state);
    return true;
}

// ==================== 状态查询 ====================

ResonatorState ResonatorCore::getState() const {
    return pimpl_->current_state;
}

StateSnapshot ResonatorCore::getSnapshot() const {
    return StateSnapshot{
        .state = pimpl_->current_state,
        .hum_level = pimpl_->hum_level,
        .saturation = pimpl_->saturation,
        .health = pimpl_->health,
        .timestamp = std::chrono::system_clock::now(),
        .last_operation = pimpl_->last_operation
    };
}

double ResonatorCore::getHumLevel() const {
    return pimpl_->hum_level;
}

double ResonatorCore::getSaturation() const {
    return pimpl_->saturation;
}

HealthLevel ResonatorCore::getHealthLevel() const {
    return pimpl_->health;
}

bool ResonatorCore::isHealthy() const {
    return pimpl_->health != HealthLevel::Critical &&
           pimpl_->health != HealthLevel::Dead &&
           !pimpl_->is_locked;
}

bool ResonatorCore::isAtRedLine() const {
    return pimpl_->hum_level >= config_.red_line;
}

bool ResonatorCore::isInResonancePeak() const {
    return pimpl_->hum_level >= config_.resonance_peak_min &&
           pimpl_->hum_level <= config_.resonance_peak_max;
}

// ==================== 状态转换 ====================

bool ResonatorCore::tryEnterWarm() {
    // 切换到温存态 - 维持最低嗡鸣度待机
    if (!validateStateTransition(pimpl_->current_state, ResonatorState::Warm)) {
        throw StateTransitionError(stateToString(pimpl_->current_state), "Warm");
    }

    auto old_state = pimpl_->current_state;
    pimpl_->current_state = ResonatorState::Warm;
    pimpl_->hum_level = config_.warm_hum_threshold;

    notifyStateChange(old_state, pimpl_->current_state);
    return true;
}

bool ResonatorCore::tryEnterHotStandby() {
    if (!validateStateTransition(pimpl_->current_state, ResonatorState::HotStandby)) {
        throw StateTransitionError(stateToString(pimpl_->current_state), "HotStandby");
    }

    if (!config_.enable_hot_standby) {
        std::cerr << "[ResonatorCore] 热备份未启用" << std::endl;
        return false;
    }

    auto old_state = pimpl_->current_state;
    pimpl_->current_state = ResonatorState::HotStandby;

    notifyStateChange(old_state, pimpl_->current_state);
    std::cout << "[ResonatorCore] 进入热备份状态: " << config_.resonator_id << std::endl;
    return true;
}

bool ResonatorCore::takeOverStandby(ResonatorCore& standby) {
    // 接管热备份
    if (standby.getState() != ResonatorState::HotStandby) {
        std::cerr << "[ResonatorCore] 目标非热备份状态" << std::endl;
        return false;
    }

    // 交换状态
    std::swap(pimpl_->hum_level, standby.pimpl_->hum_level);
    std::swap(pimpl_->saturation, standby.pimpl_->saturation);
    std::swap(pimpl_->health, standby.pimpl_->health);

    // 原谐振腔进入静默，备用进入运行
    pimpl_->current_state = ResonatorState::Silent;
    standby.pimpl_->current_state = ResonatorState::Running;

    std::cout << "[ResonatorCore] 热备份接管完成" << std::endl;
    return true;
}

// ==================== 故障恢复 ====================

bool ResonatorCore::executeGoldenShell(ResonatorCore& target) {
    // 金蝉脱壳 - 故障腔无损迁移到热备份
    if (pimpl_->current_state == ResonatorState::Collapsing) {
        std::cerr << "[ResonatorCore] 谐振腔已坍缩，无法迁移" << std::endl;
        return false;
    }

    if (target.getState() != ResonatorState::HotStandby) {
        std::cerr << "[ResonatorCore] 目标未处于热备份状态" << std::endl;
        return false;
    }

    // 检查目标腔容量是否足够
    double combined_saturation = target.getSaturation() + pimpl_->saturation;
    if (combined_saturation > constants::MAX_SATURATION) {
        std::cerr << "[ResonatorCore] 目标腔容量不足，无法迁移" << std::endl;
        return false;
    }

    std::cout << "[ResonatorCore] 执行金蝉脱壳: " << config_.resonator_id
              << " -> " << target.getId() << std::endl;

    // 迁移状态数据
    target.pimpl_->hum_level = pimpl_->hum_level;
    target.pimpl_->saturation = pimpl_->saturation;
    target.pimpl_->health = pimpl_->health;
    target.pimpl_->current_state = ResonatorState::Running;

    // 原谐振腔进入坍缩流程
    triggerCollapse();

    return true;
}

bool ResonatorCore::triggerCollapse() {
    // 触发坍缩流程
    if (!validateStateTransition(pimpl_->current_state, ResonatorState::Collapsing)) {
        std::cerr << "[ResonatorCore] 无法触发坍缩" << std::endl;
        return false;
    }

    auto old_state = pimpl_->current_state;
    pimpl_->current_state = ResonatorState::Collapsing;
    pimpl_->health = HealthLevel::Dead;

    notifyStateChange(old_state, pimpl_->current_state);

    // 坍缩后释放所有哈基米
    pimpl_->saturation = 0.0;
    pimpl_->hum_level = 0.0;

    std::cout << "[ResonatorCore] 坍缩完成: " << config_.resonator_id << std::endl;
    return true;
}

bool ResonatorCore::emergencyLock() {
    // 紧急锁定 - 锁龙井机制
    pimpl_->is_locked = true;
    pimpl_->last_operation = "emergency_lock";
    std::cout << "[ResonatorCore] 锁龙井激活: " << config_.resonator_id << std::endl;
    return true;
}

// ==================== 回调注册 ====================

void ResonatorCore::onStateChange(StateChangeCallback cb) {
    pimpl_->on_state_change = std::move(cb);
}

void ResonatorCore::onCollapseWarning(CollapseWarningCallback cb) {
    pimpl_->on_collapse_warning = std::move(cb);
}

} // namespace hajimi
