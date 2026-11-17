select
    dataset_source,
    slice_group,
    charge_category,
    pricing_category,
    commitment_discount_type,
    row_count,
    raw_variance,
    upstream_integer_rounding_loss,
    variance_after_rounding_adjustment,
    rows_not_matching_integer_round
from {{ ref('fct_cost_reconciliation_audit') }}
where dataset_source = 'FOCUS_1.0'
  and charge_category = 'Usage'
  and pricing_category = 'Standard'
  and commitment_discount_type = 'None'
  and (
      (slice_group = 'Microsoft' and abs(raw_variance) > 0.01)
      or (slice_group = 'AWS' and rows_not_matching_integer_round > 15)
  )

