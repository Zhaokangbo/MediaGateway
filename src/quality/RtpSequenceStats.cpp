#include "mediagateway/quality/RtpSequenceStats.h"

namespace mediagateway { namespace quality {

RtpSequenceStats::RtpSequenceStats() { seen_.fill(-1); }

void RtpSequenceStats::reset() {
    const auto next_epoch = stats_.epoch + 1;
    stats_ = Snapshot{};
    stats_.epoch = next_epoch;
    first_ = -1;
    seen_.fill(-1);
}

RtpSequenceStats::Result RtpSequenceStats::observe(std::uint16_t sequence) {
    ++stats_.received;
    if (stats_.highest_extended < 0) {
        first_ = sequence;
        stats_.highest_extended = sequence;
        seen_[sequence % kWindow] = sequence;
        ++stats_.unique;
        return Result::First;
    }

    // Explicit modular subtraction avoids implementation-defined uint16->int16
    // conversion. Exactly half a sequence space has no unambiguous direction.
    const auto highest16 = static_cast<std::uint16_t>(stats_.highest_extended);
    const auto modular = static_cast<std::uint16_t>(sequence - highest16);
    const int delta = modular <= 32767 ? static_cast<int>(modular)
                                      : static_cast<int>(modular) - 65536;
    if (modular == 32768 || delta > kMaxForwardStep) {
        ++stats_.discontinuities;
        return Result::Discontinuity;
    }

    const auto extended = stats_.highest_extended + delta;
    if (extended < first_ || stats_.highest_extended - extended >= static_cast<std::int64_t>(kWindow)) {
        ++stats_.too_old;
        return Result::TooOld;
    }

    auto &slot = seen_[static_cast<std::size_t>(extended % static_cast<std::int64_t>(kWindow))];
    if (slot == extended) {
        ++stats_.duplicates;
        return Result::Duplicate;
    }
    slot = extended;
    ++stats_.unique;
    if (extended < stats_.highest_extended) {
        ++stats_.reordered;
        return Result::Reordered;
    }
    stats_.highest_extended = extended;
    return Result::InOrder;
}

}} // namespace mediagateway::quality
