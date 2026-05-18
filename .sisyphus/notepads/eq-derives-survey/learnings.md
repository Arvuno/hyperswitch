# Eq Derives Survey - SessionToken Containment Analysis

## Date: 2025-05-18

## Task
Find all types in `crates/api_models/src/payments.rs` that:
1. Derive `Eq`
2. Transitively contain `SessionToken`, `ApplePaySessionResponse`, or `ApplepaySessionTokenResponse`

## Background
The error was:
```
error[E0277]: the trait bound `SessionToken: std::cmp::Eq` is not satisfied
```

This occurred during OpenAPI spec generation after removing `Eq` from `SessionToken`.

## Methodology
1. Searched for all `#[derive(...)]` lines containing `Eq` (found 57 total)
2. Identified types that transitively contain the problematic types
3. Cross-referenced to find which types derive `Eq`

## Types with `Eq` Removed (Previous Tasks)
- `ApplePaySessionResponse` (line 10726) - removed Eq
- `ApplepaySessionTokenResponse` (line 10660) - removed Eq
- `SessionToken` (line 10317) - removed Eq

## Transitive Containment Chain
```
serde_json::Value
    ↓
ApplePaySessionResponse (NoThirdPartySdk variant)
    ↓
ApplepaySessionTokenResponse.session_token_data: Option<ApplePaySessionResponse>
    ↓
SessionToken.ApplePay variant: Box<ApplepaySessionTokenResponse>
    ↓
NextActionData.ThirdPartySdkSessionToken.variant: Option<SessionToken>
    ↓
PaymentsPostSessionTokensResponse.next_action: Option<NextActionData>
```

## Key Finding: NO ADDITIONAL TYPES NEED Eq REMOVED

### Verification Details

| Container Type | Contains | Derives Eq? | Status |
|----------------|----------|-------------|--------|
| `PaymentsPostSessionTokensResponse` | `Option<NextActionData>` | No | OK |
| `PaymentAttemptResponse` v2 | `Option<NextActionData>` | No | OK |
| `PaymentsResponse` v2 | `Option<NextActionData>` | No | OK |
| `NextActionData` | `Option<SessionToken>` | No | OK |
| `PaymentsSessionResponse` v1 | `Vec<SessionToken>` | No | OK |
| `PaymentsSessionResponse` v2 | `Vec<SessionToken>` | No | OK |
| `NextActionType` | N/A (unit variants only) | No | OK |

## Full List of 57 Types with Eq Derive
(For reference - NONE of these contain the problematic types transitively)
1. PaymentOp (line 93)
2. BankCodeResponse (line 118)
3. Amount (line 2307)
4. (line 2361 - unnamed type at ~2360)
5. MandateReferenceId (line 2408)
6. (line 2417)
7. (line 2425)
8. (line 2435)
9. (line 2445)
10. UpdateHistory (line 2536)
11. SingleUseMandate (line 2581)
12. ExtendedCardInfo (line 2762)
13. RecordAttemptPaymentMethodDataRequest (line 3392)
14. ProxyPaymentMethodDataRequest (line 3401)
15. (line 3414)
16. ProxyCardData (line 3422)
17. (line 3473)
18. (line 4081)
19. (line 4132)
20. AdditionalPaymentData (line 4169)
21. KlarnaSdkPaymentMethod (line 4245)
22. InteracPaymentMethod (line 4250)
23. SofortBilling (line 4779)
24. RewardData (line 5840)
25. PaymentIdType v1 (line 6283)
26. (line 6296)
27. (line 6578)
28. UrlDetails (line 6656)
29. AuthenticationForStartResponse (line 6661)
30. MobilePaymentNextStepData (line 7025)
31. (line 8463)
32. (line 8475)
33. (line 8496)
34. (line 8508)
35. (line 8521)
36. (line 9178)
37. (line 9186)
38. (line 9200)
39. (line 9456)
40. (line 9466)
41. VaultSessionDetails (line 10350)
42. VgsSessionDetails (line 10357)
43. HyperswitchVaultSessionDetails (line 10366)
44. ApplepayPaymentMethod (line 5782 - also derives Eq!)
45. (line 10602)
46. (line 10608)
47. (line 10868)
48. (line 10870)
49. PixAdditionalDetails (line 11746)
50. (line 11754)
51. (line 11769)
52. (line 11788)
53. (line 11795)
54. (line 12342)
55. (line 12475)
56. NullObject (line 13277)

## Conclusion
All types that transitively contain `SessionToken`, `ApplePaySessionResponse`, or `ApplepaySessionTokenResponse` do NOT derive `Eq`. The fix was already complete when the leaf types had `Eq` removed.