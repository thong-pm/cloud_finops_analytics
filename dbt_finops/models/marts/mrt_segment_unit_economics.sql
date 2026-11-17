with aws_account_spend as (
    select
        sub_account_id,
        sub_account_name,
        sum(case when not is_untagged then billed_cost else 0 end) as tagged_direct_cost_usd,
        sum(case when is_untagged then billed_cost else 0 end) as untagged_account_cost_usd,
        sum(billed_cost) as total_account_usage_cost_usd
    from {{ ref('stg_focus_cost') }}
    where provider_name = 'AWS'
      and charge_category = 'Usage'
    group by sub_account_id, sub_account_name
),

rev_seed as (
    select
        cast(sub_account_id as {{ dbt.type_string() }}) as sub_account_id,
        sub_account_name,
        customer_segment,
        cast(active_projects as integer) as active_projects,
        cast(monthly_revenue_usd as {{ dbt.type_numeric() }}) as monthly_revenue_usd,
        cast(is_synthetic_revenue as boolean) as is_synthetic_revenue
    from {{ ref('seed_synthetic_segment_revenue') }}
    where sub_account_id is not null
),

unmapped_pool as (
    select
        coalesce(sum(a.total_account_usage_cost_usd), 0) as unmapped_shared_infra_cost_usd
    from aws_account_spend a
    left join rev_seed r on a.sub_account_id = r.sub_account_id
    where r.sub_account_id is null
),

joined as (
    select
        r.sub_account_id,
        r.sub_account_name,
        r.customer_segment,
        r.active_projects,
        r.monthly_revenue_usd,
        r.is_synthetic_revenue,
        coalesce(a.tagged_direct_cost_usd, 0) as tagged_direct_cost_usd,
        coalesce(a.untagged_account_cost_usd, 0) as untagged_account_cost_usd,
        coalesce(a.total_account_usage_cost_usd, 0) as direct_account_cost_usd,
        sum(coalesce(a.total_account_usage_cost_usd, 0)) over () as total_mapped_direct_cost_usd
    from rev_seed r
    left join aws_account_spend a on r.sub_account_id = a.sub_account_id
)

select
    j.sub_account_id,
    j.sub_account_name,
    j.customer_segment,
    j.active_projects,
    j.is_synthetic_revenue,
    round(j.monthly_revenue_usd, 2) as monthly_revenue_usd,
    round(j.tagged_direct_cost_usd, 2) as tagged_direct_cost_usd,
    round(j.untagged_account_cost_usd, 2) as untagged_account_cost_usd,
    round(j.direct_account_cost_usd, 2) as direct_account_cost_usd,
    round(
        u.unmapped_shared_infra_cost_usd * (j.direct_account_cost_usd / nullif(j.total_mapped_direct_cost_usd, 0)),
        2
    ) as allocated_shared_infra_cost_usd,
    round(
        j.direct_account_cost_usd
        + u.unmapped_shared_infra_cost_usd * (j.direct_account_cost_usd / nullif(j.total_mapped_direct_cost_usd, 0)),
        2
    ) as fully_loaded_cost_usd,
    round(
        (
            j.direct_account_cost_usd
            + u.unmapped_shared_infra_cost_usd * (j.direct_account_cost_usd / nullif(j.total_mapped_direct_cost_usd, 0))
        ) / nullif(j.active_projects, 0),
        2
    ) as cost_per_active_project_usd,
    round(
        j.monthly_revenue_usd - (
            j.direct_account_cost_usd
            + u.unmapped_shared_infra_cost_usd * (j.direct_account_cost_usd / nullif(j.total_mapped_direct_cost_usd, 0))
        ),
        2
    ) as gross_margin_usd,
    round(
        case
            when j.monthly_revenue_usd > 0 then
                (
                    j.monthly_revenue_usd - (
                        j.direct_account_cost_usd
                        + u.unmapped_shared_infra_cost_usd * (j.direct_account_cost_usd / nullif(j.total_mapped_direct_cost_usd, 0))
                    )
                ) / j.monthly_revenue_usd * 100.0
            else null
        end,
        2
    ) as gross_margin_pct
from joined j
cross join unmapped_pool u
order by fully_loaded_cost_usd desc

