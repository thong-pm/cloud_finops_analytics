with raw_focus as (
    select * from {{ source('finops_raw', 'focus_cost_export') }}
),

normalized as (
    select
        {{ clean_null_str('id') }} as focus_row_id,
        coalesce({{ clean_null_str('provider_name') }}, 'Unknown') as provider_name,
        coalesce({{ clean_null_str('billing_account_id') }}, 'unassigned') as billing_account_id,
        coalesce({{ clean_null_str('sub_account_id') }}, 'unassigned') as sub_account_id,
        coalesce({{ clean_null_str('sub_account_name') }}, 'Unassigned Account') as sub_account_name,
        {{ safe_cast_date('charge_period_start') }} as charge_date,
        {{ safe_cast_date('billing_period_start') }} as billing_period_date,
        initcap(coalesce({{ clean_null_str('charge_category') }}, 'Unknown')) as charge_category,
        initcap(coalesce({{ clean_null_str('pricing_category') }}, 'Unspecified')) as pricing_category,
        coalesce({{ clean_null_str('commitment_discount_type') }}, 'None') as commitment_discount_type,
        coalesce({{ clean_null_str('commitment_discount_status') }}, 'None') as commitment_discount_status,
        coalesce({{ clean_null_str('service_category') }}, 'Other') as service_category,
        coalesce({{ clean_null_str('service_name') }}, 'Other') as service_name,
        {{ clean_null_str('charge_description') }} as charge_description,
        {{ clean_null_str('resource_id') }} as resource_id,
        {{ clean_null_str('resource_type') }} as resource_type,
        {{ clean_null_str('region_id') }} as region_id,
        {{ safe_cast_numeric('billed_cost') }} as billed_cost,
        {{ safe_cast_numeric('effective_cost') }} as effective_cost,
        {{ safe_cast_numeric('list_cost') }} as list_cost,
        {{ safe_cast_numeric('contracted_cost') }} as contracted_cost,
        {{ safe_cast_numeric('consumed_quantity') }} as consumed_quantity,
        {{ clean_null_str('consumed_unit') }} as consumed_unit,
        {{ clean_null_str('tags') }} as raw_tags_json,
        case
            when {{ clean_null_str('tags') }} is null or {{ clean_null_str('tags') }} = '{}' then true
            else false
        end as is_untagged,
        coalesce({{ json_extract_tag('tags', 'application') }}, 'unallocated') as tag_application,
        coalesce({{ json_extract_tag('tags', 'environment') }}, 'unallocated') as tag_environment,
        coalesce({{ json_extract_tag('tags', 'business_unit') }}, 'unallocated') as tag_business_unit
    from raw_focus
)

select * from normalized

