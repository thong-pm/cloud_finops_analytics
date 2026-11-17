select
    dataset_source,
    slice_group,
    row_count,
    total_cash_cost,
    total_amortized_cost,
    variance_after_rounding_adjustment
from {{ ref('fct_cost_reconciliation_audit') }}
where dataset_source = 'AWS_CUR_2018'
  and abs(variance_after_rounding_adjustment) > 0.001

