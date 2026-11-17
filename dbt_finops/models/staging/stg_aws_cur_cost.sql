with raw_cur as (
    select
        identity_line_item_id,
        identity_time_interval,
        {{ safe_cast_date('bill_billing_period_start_date') }} as billing_period_date,
        {{ safe_cast_date('line_item_usage_start_date') }} as usage_date,
        coalesce(cast(line_item_usage_account_id as {{ dbt.type_string() }}), 'unassigned') as usage_account_id,
        coalesce(line_item_product_code, 'Unknown') as product_code,
        coalesce(line_item_line_item_type, 'Unknown') as line_item_line_item_type,
        line_item_usage_type,
        line_item_operation,
        line_item_resource_id,
        pricing_term,
        product_instance_type,
        product_region,
        reservation_reservation_a_r_n,
        coalesce(cast(line_item_unblended_cost as {{ dbt.type_numeric() }}), 0) as line_item_unblended_cost,
        coalesce(cast(line_item_unblended_cost as {{ dbt.type_numeric() }}), 0) as line_item_net_unblended_cost,
        coalesce(cast(line_item_blended_cost as {{ dbt.type_numeric() }}), 0) as line_item_blended_cost,
        coalesce(cast(reservation_effective_cost as {{ dbt.type_numeric() }}), 0) as reservation_effective_cost,
        coalesce(cast(reservation_effective_cost as {{ dbt.type_numeric() }}), 0) as reservation_net_effective_cost,
        coalesce(cast(reservation_amortized_upfront_cost_for_usage as {{ dbt.type_numeric() }}), 0) as reservation_amortized_upfront_cost_for_usage,
        coalesce(cast(reservation_recurring_fee_for_usage as {{ dbt.type_numeric() }}), 0) as reservation_recurring_fee_for_usage,
        coalesce(cast(reservation_unused_amortized_upfront_fee_for_billing_period as {{ dbt.type_numeric() }}), 0) as reservation_unused_amortized_upfront_fee_for_billing_period,
        coalesce(cast(reservation_unused_amortized_upfront_fee_for_billing_period as {{ dbt.type_numeric() }}), 0) as reservation_net_unused_amortized_upfront_fee_for_billing_period,
        coalesce(cast(reservation_unused_recurring_fee as {{ dbt.type_numeric() }}), 0) as reservation_unused_recurring_fee,
        coalesce(cast(reservation_unused_recurring_fee as {{ dbt.type_numeric() }}), 0) as reservation_net_unused_recurring_fee,
        cast(0 as {{ dbt.type_numeric() }}) as savings_plan_savings_plan_effective_cost,
        cast(0 as {{ dbt.type_numeric() }}) as savings_plan_net_savings_plan_effective_cost,
        cast(0 as {{ dbt.type_numeric() }}) as savings_plan_total_commitment_to_date,
        cast(0 as {{ dbt.type_numeric() }}) as savings_plan_used_commitment,
        cast(0 as {{ dbt.type_numeric() }}) as savings_plan_amortized_upfront_commitment_for_billing_period,
        cast(0 as {{ dbt.type_numeric() }}) as savings_plan_net_amortized_upfront_commitment_for_billing_period
    from {{ source('finops_raw', 'aws_cur_export') }}
)

select
    identity_line_item_id,
    identity_time_interval,
    billing_period_date,
    usage_date,
    usage_account_id,
    product_code,
    line_item_line_item_type,
    line_item_usage_type,
    line_item_operation,
    line_item_resource_id,
    pricing_term,
    product_instance_type,
    product_region,
    reservation_reservation_a_r_n,
    line_item_unblended_cost as unblended_cost,
    line_item_blended_cost as blended_cost,
    reservation_effective_cost,
    reservation_amortized_upfront_cost_for_usage,
    reservation_recurring_fee_for_usage,
    reservation_unused_amortized_upfront_fee_for_billing_period,
    reservation_unused_recurring_fee,
    {{ aws_cur_amortized_cost() }} as amortized_cost,
    {{ aws_cur_net_amortized_cost() }} as net_amortized_cost,
    case
        when line_item_line_item_type = 'RIFee'
            then reservation_unused_amortized_upfront_fee_for_billing_period + reservation_unused_recurring_fee
        else 0
    end as unused_commitment_waste
from raw_cur
