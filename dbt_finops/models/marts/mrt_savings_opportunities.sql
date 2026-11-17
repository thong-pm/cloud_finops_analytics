with focus_aws_usage as (
    select *
    from {{ ref('stg_focus_cost') }}
    where provider_name = 'AWS'
      and charge_category = 'Usage'
),

assumptions as (
    select
        opportunity_id,
        lever_category,
        parameter_metric,
        cast(low_factor as {{ dbt.type_numeric() }}) as low_factor,
        cast(base_factor as {{ dbt.type_numeric() }}) as base_factor,
        cast(high_factor as {{ dbt.type_numeric() }}) as high_factor,
        assumption_note,
        aws_doc_url
    from {{ ref('seed_finops_savings_assumptions') }}
),

ec2_daily_ondemand as (
    select
        charge_date,
        billing_period_date,
        sum(case when pricing_category = 'Standard' then list_cost else 0 end) as daily_ondemand_list_cost,
        sum(case when commitment_discount_type = 'Savings Plan' then list_cost else 0 end) as daily_sp_covered_list_cost
    from focus_aws_usage
    where service_name = 'Amazon Elastic Compute Cloud'
    group by charge_date, billing_period_date
),

ec2_ranked as (
    select
        billing_period_date,
        daily_ondemand_list_cost,
        daily_sp_covered_list_cost,
        row_number() over (order by daily_ondemand_list_cost asc) as rn,
        count(*) over () as total_days
    from ec2_daily_ondemand
),

ec2_sp_sizing as (
    select
        '1_ec2_savings_plan_floor_sizing' as opportunity_id,
        'FOCUS_1.0_2024_09' as dataset_source,
        'AWS (FOCUS Sept 2024)' as scope,
        'Amazon Elastic Compute Cloud' as target_service,
        count(distinct billing_period_date) as billing_months_in_scope,
        count(*) as affected_days_or_rows,
        round(sum(daily_ondemand_list_cost + daily_sp_covered_list_cost), 2) as current_spend_or_list_exposure_usd,
        round(
            max(case when rn = cast(ceil(total_days * 0.10) as integer) then daily_ondemand_list_cost else 0 end) * 30.0,
            2
        ) as monthly_addressable_spend_usd,
        'EC2 Savings Plan coverage is 2.0% on a ListCost basis ($35.91 covered vs $1,755.88 On-Demand); sizing a 1-year Compute Savings Plan to the p10 daily On-Demand baseline floor captures steady-state discount with minimal idle commitment risk.' as engineering_rationale
    from ec2_ranked
),

dev_gpu_instances as (
    select
        '2_dev_gpu_offhours_scheduling' as opportunity_id,
        'FOCUS_1.0_2024_09' as dataset_source,
        'AWS (FOCUS Sept 2024)' as scope,
        'Amazon Elastic Compute Cloud (Dev GPU)' as target_service,
        count(distinct billing_period_date) as billing_months_in_scope,
        count(*) as affected_days_or_rows,
        round(sum(billed_cost), 2) as current_spend_or_list_exposure_usd,
        round(
            sum(billed_cost) / nullif(count(distinct billing_period_date), 0),
            2
        ) as monthly_addressable_spend_usd,
        '374 rows of g3/g5 GPU instances tagged environment=dev running On-Demand; stopping non-production GPU instances outside weekday working hours reduces active runtime hours.' as engineering_rationale
    from focus_aws_usage
    where tag_environment = 'dev'
      and (
          charge_description like '%g5.%'
          or charge_description like '%g3.%'
          or charge_description like '%g4%'
          or charge_description like '%p3.%'
      )
),

vpc_idle_ipv4 as (
    select
        '3_vpc_idle_public_ipv4_release' as opportunity_id,
        'FOCUS_1.0_2024_09' as dataset_source,
        'AWS (FOCUS Sept 2024)' as scope,
        'Amazon Virtual Private Cloud' as target_service,
        count(distinct billing_period_date) as billing_months_in_scope,
        count(*) as affected_days_or_rows,
        round(sum(billed_cost), 2) as current_spend_or_list_exposure_usd,
        round(
            sum(case when charge_description like '%Idle public IPv4%' then billed_cost else 0 end)
            / nullif(count(distinct billing_period_date), 0),
            2
        ) as monthly_addressable_spend_usd,
        'Separates $18.07 in-use public IPv4 charges from $1.21 of unattached Idle public IPv4 address hours ($0.005/hr); releasing unattached Elastic IPs eliminates idle address charges.' as engineering_rationale
    from focus_aws_usage
    where service_name = 'Amazon Virtual Private Cloud'
      and charge_description like '%public IPv4%'
),

s3_egress_share as (
    select
        '4_s3_egress_transfer_reduction' as opportunity_id,
        'FOCUS_1.0_2024_09' as dataset_source,
        'AWS (FOCUS Sept 2024)' as scope,
        'Amazon Simple Storage Service' as target_service,
        count(distinct billing_period_date) as billing_months_in_scope,
        count(*) as affected_days_or_rows,
        round(sum(billed_cost), 2) as current_spend_or_list_exposure_usd,
        round(
            sum(
                case
                    when charge_description like '%data transfer out%'
                      or charge_description like '%Out-Bytes%'
                      or charge_description like '%data transfer to%'
                    then billed_cost
                    else 0
                end
            ) / nullif(count(distinct billing_period_date), 0),
            2
        ) as monthly_addressable_spend_usd,
        'S3 transfer charges consist of $3.80 public internet egress ($0.090-$0.085/GB data transfer out) and $0.21 cross-region transfer ($0.02/GB AWS-Out-Bytes/inter-region) vs $2.54 storage; serving public downloads via CloudFront CDN (where S3-to-CloudFront origin fetch is $0.00/GB) with object compression and co-locating cross-region compute reduces transfer spend.' as engineering_rationale
    from focus_aws_usage
    where service_name = 'Amazon Simple Storage Service'
),

cur_ri_unused_waste as (
    select
        '5_cur_reserved_instance_unused_waste' as opportunity_id,
        'AWS_CUR_2018_Q4' as dataset_source,
        'AWS CUR (Oct-Dec 2018 3-Month Normalized to Monthly)' as scope,
        'Reserved Instances (RIFee)' as target_service,
        count(distinct billing_period_date) as billing_months_in_scope,
        count(*) as affected_days_or_rows,
        round(sum(amortized_cost), 2) as current_spend_or_list_exposure_usd,
        round(
            sum(unused_commitment_waste) / nullif(count(distinct billing_period_date), 0),
            2
        ) as monthly_addressable_spend_usd,
        'Quantifies unused Reserved Instance commitment waste ($49.00 Oct + $43.22 Nov + $52.88 Dec = $145.09 across 3 months, or $48.36/month average) recoverable via AZ/Linux instance size-flex modification, Convertible RI exchange, or Standard RI Marketplace resale.' as engineering_rationale
    from {{ ref('stg_aws_cur_cost') }}
    where line_item_line_item_type in ('DiscountedUsage', 'RIFee')
),

unioned_opportunities as (
    select * from ec2_sp_sizing
    union all
    select * from dev_gpu_instances
    union all
    select * from vpc_idle_ipv4
    union all
    select * from s3_egress_share
    union all
    select * from cur_ri_unused_waste
)

select
    u.opportunity_id,
    u.dataset_source,
    a.lever_category,
    u.scope,
    u.target_service,
    u.billing_months_in_scope,
    u.affected_days_or_rows,
    u.current_spend_or_list_exposure_usd,
    u.monthly_addressable_spend_usd,
    round(u.monthly_addressable_spend_usd * a.low_factor, 2) as estimated_monthly_savings_low_usd,
    round(u.monthly_addressable_spend_usd * a.base_factor, 2) as estimated_monthly_savings_usd,
    round(u.monthly_addressable_spend_usd * a.high_factor, 2) as estimated_monthly_savings_high_usd,
    a.parameter_metric,
    a.low_factor,
    a.base_factor,
    a.high_factor,
    a.assumption_note,
    a.aws_doc_url,
    u.engineering_rationale
from unioned_opportunities u
inner join assumptions a
    on u.opportunity_id = a.opportunity_id
order by u.opportunity_id
