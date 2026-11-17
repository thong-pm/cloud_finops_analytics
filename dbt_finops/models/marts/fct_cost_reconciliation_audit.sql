with focus_slice as (
    select
        'FOCUS_1.0' as dataset_source,
        provider_name as slice_group,
        charge_category,
        pricing_category,
        commitment_discount_type,
        count(*) as row_count,
        round(sum(billed_cost), 4) as total_cash_cost,
        round(sum(effective_cost), 4) as total_amortized_cost,
        round(sum(billed_cost) - sum(effective_cost), 4) as raw_variance,
        round(sum(billed_cost - round(billed_cost, 0)), 4) as upstream_integer_rounding_loss,
        round(sum(round(billed_cost, 0)) - sum(effective_cost), 4) as variance_after_rounding_adjustment,
        sum(case when effective_cost != round(billed_cost, 0) then 1 else 0 end) as rows_not_matching_integer_round
    from {{ ref('stg_focus_cost') }}
    group by
        provider_name,
        charge_category,
        pricing_category,
        commitment_discount_type
),

cur_monthly as (
    select
        'AWS_CUR_2018' as dataset_source,
        cast(billing_period_date as {{ dbt.type_string() }}) as slice_group,
        'All_CUR_Types' as charge_category,
        'Mixed_RI_and_OnDemand' as pricing_category,
        'Reserved_Instance' as commitment_discount_type,
        count(*) as row_count,
        round(sum(unblended_cost), 4) as total_cash_cost,
        round(sum(amortized_cost), 4) as total_amortized_cost,
        round(sum(unblended_cost) - sum(amortized_cost), 4) as raw_variance,
        cast(0 as {{ dbt.type_numeric() }}) as upstream_integer_rounding_loss,
        round(
            sum(amortized_cost) - (
                sum(case when line_item_line_item_type = 'Usage' then unblended_cost else 0 end)
                + sum(case when line_item_line_item_type = 'RIFee' then unblended_cost else 0 end)
                + sum(case when line_item_line_item_type = 'DiscountedUsage' then reservation_amortized_upfront_cost_for_usage else 0 end)
                + sum(case when line_item_line_item_type = 'RIFee' then reservation_unused_amortized_upfront_fee_for_billing_period else 0 end)
            ),
            6
        ) as variance_after_rounding_adjustment,
        cast(0 as bigint) as rows_not_matching_integer_round
    from {{ ref('stg_aws_cur_cost') }}
    group by billing_period_date
)

select * from focus_slice
union all
select * from cur_monthly
