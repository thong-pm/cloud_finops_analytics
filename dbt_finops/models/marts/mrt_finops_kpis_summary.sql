with focus_kpis as (
    select
        cast('FOCUS_1.0' as {{ dbt.type_string() }}) as dataset_source,
        provider_name,
        count(distinct billing_period_date) as billing_months_count,
        round(sum(billed_cost), 2) as total_billed_cost_usd,
        round(sum(effective_cost), 2) as total_effective_cost_usd,
        round(sum(case when charge_category = 'Usage' and not is_untagged then billed_cost else 0 end), 2) as tagged_usage_spend_usd,
        round(sum(case when charge_category = 'Usage' and is_untagged then billed_cost else 0 end), 2) as untagged_usage_spend_usd,
        round(
            case
                when sum(case when charge_category = 'Usage' then billed_cost else 0 end) > 0 then
                    sum(case when charge_category = 'Usage' and not is_untagged then billed_cost else 0 end)
                    / sum(case when charge_category = 'Usage' then billed_cost else 0 end) * 100.0
                else 0
            end,
            2
        ) as tag_coverage_pct,
        round(sum(case when charge_category = 'Usage' and commitment_discount_type != 'None' then list_cost else 0 end), 2) as commitment_covered_list_cost_usd,
        round(sum(case when charge_category = 'Usage' and commitment_discount_type = 'None' then list_cost else 0 end), 2) as ondemand_list_cost_usd,
        round(
            case
                when sum(case when charge_category = 'Usage' then list_cost else 0 end) > 0 then
                    sum(case when charge_category = 'Usage' and commitment_discount_type != 'None' then list_cost else 0 end)
                    / sum(case when charge_category = 'Usage' then list_cost else 0 end) * 100.0
                else 0
            end,
            2
        ) as commitment_coverage_pct,
        round(sum(case when commitment_discount_status = 'Unused' then effective_cost else 0 end), 2) as unused_commitment_waste_usd,
        round(
            case
                when sum(case when charge_category = 'Usage' and commitment_discount_type != 'None' and list_cost > 0 then list_cost else 0 end) > 0 then
                    (
                        sum(case when charge_category = 'Usage' and commitment_discount_type != 'None' and list_cost > 0 then list_cost else 0 end)
                        - sum(case when charge_category = 'Usage' and commitment_discount_type != 'None' and list_cost > 0 then effective_cost else 0 end)
                    ) / sum(case when charge_category = 'Usage' and commitment_discount_type != 'None' and list_cost > 0 then list_cost else 0 end) * 100.0
                else 0
            end,
            2
        ) as effective_savings_rate_pct
    from {{ ref('stg_focus_cost') }}
    group by provider_name
),

cur_kpis as (
    select
        cast('AWS_CUR_2018' as {{ dbt.type_string() }}) as dataset_source,
        cast('AWS' as {{ dbt.type_string() }}) as provider_name,
        count(distinct billing_period_date) as billing_months_count,
        round(sum(unblended_cost), 2) as total_billed_cost_usd,
        round(sum(amortized_cost), 2) as total_effective_cost_usd,
        cast(0.00 as {{ dbt.type_numeric() }}) as tagged_usage_spend_usd,
        round(sum(case when line_item_line_item_type in ('Usage', 'DiscountedUsage') then amortized_cost else 0 end), 2) as untagged_usage_spend_usd,
        cast(0.00 as {{ dbt.type_numeric() }}) as tag_coverage_pct,
        round(sum(case when line_item_line_item_type = 'DiscountedUsage' then amortized_cost else 0 end), 2) as commitment_covered_list_cost_usd,
        round(sum(case when line_item_line_item_type = 'Usage' then unblended_cost else 0 end), 2) as ondemand_list_cost_usd,
        round(
            case
                when sum(case when line_item_line_item_type in ('Usage', 'DiscountedUsage') then amortized_cost else 0 end) > 0 then
                    sum(case when line_item_line_item_type = 'DiscountedUsage' then amortized_cost else 0 end)
                    / sum(case when line_item_line_item_type in ('Usage', 'DiscountedUsage') then amortized_cost else 0 end) * 100.0
                else 0
            end,
            2
        ) as commitment_coverage_pct,
        round(sum(unused_commitment_waste), 2) as unused_commitment_waste_usd,
        round(
            case
                when sum(case when line_item_line_item_type in ('DiscountedUsage', 'RIFee') then amortized_cost else 0 end) > 0 then
                    (
                        1.0 - sum(unused_commitment_waste)
                        / sum(case when line_item_line_item_type in ('DiscountedUsage', 'RIFee') then amortized_cost else 0 end)
                    ) * 100.0
                else 0
            end,
            2
        ) as effective_savings_rate_pct
    from {{ ref('stg_aws_cur_cost') }}
)

select * from focus_kpis
union all
select * from cur_kpis
