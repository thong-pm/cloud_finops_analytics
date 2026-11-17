{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite' if target.type == 'bigquery' else 'delete+insert',
        on_schema_change='sync_all_columns',
        unique_key=['dataset_source', 'charge_date', 'provider_name', 'sub_account_id', 'service_name', 'charge_category', 'pricing_category', 'commitment_discount_type', 'tag_application', 'tag_environment', 'tag_business_unit', 'is_untagged'],
        partition_by={
            "field": "charge_date",
            "data_type": "date",
            "granularity": "day"
        } if target.type == 'bigquery' else none,
        cluster_by=['provider_name', 'sub_account_id', 'service_name', 'charge_category'] if target.type == 'bigquery' else none
    )
}}

with focus_conformed as (
    select
        cast('FOCUS_1.0' as {{ dbt.type_string() }}) as dataset_source,
        charge_date,
        billing_period_date,
        provider_name,
        sub_account_id,
        sub_account_name,
        service_category,
        service_name,
        charge_category,
        pricing_category,
        commitment_discount_type,
        tag_application,
        tag_environment,
        tag_business_unit,
        is_untagged,
        billed_cost,
        effective_cost,
        list_cost,
        contracted_cost,
        consumed_quantity
    from {{ ref('stg_focus_cost') }}
),

aws_cur_conformed as (
    select
        cast('AWS_CUR' as {{ dbt.type_string() }}) as dataset_source,
        usage_date as charge_date,
        billing_period_date,
        cast('AWS' as {{ dbt.type_string() }}) as provider_name,
        usage_account_id as sub_account_id,
        usage_account_id as sub_account_name,
        case
            when product_code in ('AmazonEC2', 'AWSLambda') then 'Compute'
            when product_code in ('AmazonS3', 'AmazonEFS') then 'Storage'
            when product_code in ('AmazonRDS', 'AmazonDynamoDB') then 'Database'
            else 'Other'
        end as service_category,
        product_code as service_name,
        case
            when line_item_line_item_type in ('Usage', 'DiscountedUsage', 'SavingsPlanCoveredUsage') then 'Usage'
            when line_item_line_item_type in ('Fee', 'RIFee', 'SavingsPlanUpfrontFee', 'SavingsPlanRecurringFee') then 'Purchase'
            when line_item_line_item_type in ('Credit', 'SavingsPlanNegation') then 'Credit'
            when line_item_line_item_type = 'Tax' then 'Tax'
            else 'Adjustment'
        end as charge_category,
        case
            when line_item_line_item_type in ('DiscountedUsage', 'RIFee', 'Fee', 'SavingsPlanCoveredUsage', 'SavingsPlanRecurringFee', 'SavingsPlanUpfrontFee') then 'Committed'
            else 'Standard'
        end as pricing_category,
        case
            when line_item_line_item_type in ('DiscountedUsage', 'RIFee', 'Fee') then 'Reserved Instance'
            when line_item_line_item_type like 'SavingsPlan%' then 'Savings Plan'
            else 'None'
        end as commitment_discount_type,
        cast('unallocated' as {{ dbt.type_string() }}) as tag_application,
        cast('unallocated' as {{ dbt.type_string() }}) as tag_environment,
        cast('unallocated' as {{ dbt.type_string() }}) as tag_business_unit,
        true as is_untagged,
        unblended_cost as billed_cost,
        amortized_cost as effective_cost,
        unblended_cost as list_cost,
        amortized_cost as contracted_cost,
        cast(0 as {{ dbt.type_numeric() }}) as consumed_quantity
    from {{ ref('stg_aws_cur_cost') }}
),

unioned as (
    select * from focus_conformed
    union all
    select * from aws_cur_conformed
),

filtered as (
    select *
    from unioned
    {% if is_incremental() %}
        where charge_date >= (
            select coalesce(max(charge_date), cast('1970-01-01' as date))
            from {{ this }}
        )
    {% endif %}
)

select
    dataset_source,
    charge_date,
    billing_period_date,
    provider_name,
    sub_account_id,
    sub_account_name,
    service_category,
    service_name,
    charge_category,
    pricing_category,
    commitment_discount_type,
    tag_application,
    tag_environment,
    tag_business_unit,
    is_untagged,
    count(*) as line_item_count,
    sum(billed_cost) as billed_cost,
    sum(effective_cost) as effective_cost,
    sum(list_cost) as list_cost,
    sum(contracted_cost) as contracted_cost,
    sum(consumed_quantity) as consumed_quantity
from filtered
group by
    dataset_source,
    charge_date,
    billing_period_date,
    provider_name,
    sub_account_id,
    sub_account_name,
    service_category,
    service_name,
    charge_category,
    pricing_category,
    commitment_discount_type,
    tag_application,
    tag_environment,
    tag_business_unit,
    is_untagged
