# Card Testing Guest Checkout - Learnings

## Task Completed: 2026-05-18

### Changes Made
Added `is_ip_only_blocking_enabled` and `ip_only_blocking_threshold` fields to:
1. `crates/diesel_models/src/business_profile.rs` - CardTestingGuardConfig struct and Default impl
2. `crates/api_models/src/admin.rs` - CardTestingGuardConfig API model
3. `crates/common_utils/src/consts.rs` - DEFAULT_IP_ONLY_BLOCKING_STATUS and DEFAULT_IP_ONLY_BLOCKING_THRESHOLD constants

### Pattern Notes
- diesel_models uses `is_*_enabled: bool` naming convention
- api_models uses `*_status: CardTestingGuardStatus` enum (already existed in codebase)
- Default impl in diesel_models references `common_utils::consts::*` constants
- CardTestingGuardConfig stored as JSONB - no DB migration needed

### Verification
cargo check errors in output are **pre-existing** - not related to changes (feature-gated types like PaymentIntent, PaymentMethod with #[cfg(feature = "v1/v2")] flags)
