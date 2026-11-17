select
    dataset_source,
    charge_date,
    billing_period_date,
    provider_name,
    sub_account_id,
    service_name,
    charge_category,
    pricing_category,
    billed_cost,
    effective_cost
from {{ ref('fct_cloud_cost_daily') }}
where dataset_source is null
   or charge_date is null
   or billing_period_date is null
   or provider_name is null
   or sub_account_id is null
   or service_name is null
   or charge_category not in ('Usage', 'Purchase', 'Credit', 'Tax', 'Adjustment', 'Unknown')
   or pricing_category not in ('Standard', 'Dynamic', 'Committed', 'Other', 'Unspecified')
   or (provider_name != 'Oracle' and charge_date < billing_period_date)
