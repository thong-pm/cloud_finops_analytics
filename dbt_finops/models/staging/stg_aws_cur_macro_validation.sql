with seed_rows as (
    select
        test_case_id,
        line_item_line_item_type,
        cast(line_item_unblended_cost as {{ dbt.type_numeric() }}) as line_item_unblended_cost,
        cast(line_item_net_unblended_cost as {{ dbt.type_numeric() }}) as line_item_net_unblended_cost,
        cast(savings_plan_savings_plan_effective_cost as {{ dbt.type_numeric() }}) as savings_plan_savings_plan_effective_cost,
        cast(savings_plan_net_savings_plan_effective_cost as {{ dbt.type_numeric() }}) as savings_plan_net_savings_plan_effective_cost,
        cast(savings_plan_total_commitment_to_date as {{ dbt.type_numeric() }}) as savings_plan_total_commitment_to_date,
        cast(savings_plan_used_commitment as {{ dbt.type_numeric() }}) as savings_plan_used_commitment,
        cast(savings_plan_amortized_upfront_commitment_for_billing_period as {{ dbt.type_numeric() }}) as savings_plan_amortized_upfront_commitment_for_billing_period,
        cast(savings_plan_net_amortized_upfront_commitment_for_billing_period as {{ dbt.type_numeric() }}) as savings_plan_net_amortized_upfront_commitment_for_billing_period,
        cast(reservation_reservation_a_r_n as {{ dbt.type_string() }}) as reservation_reservation_a_r_n,
        cast(reservation_effective_cost as {{ dbt.type_numeric() }}) as reservation_effective_cost,
        cast(reservation_net_effective_cost as {{ dbt.type_numeric() }}) as reservation_net_effective_cost,
        cast(reservation_unused_amortized_upfront_fee_for_billing_period as {{ dbt.type_numeric() }}) as reservation_unused_amortized_upfront_fee_for_billing_period,
        cast(reservation_net_unused_amortized_upfront_fee_for_billing_period as {{ dbt.type_numeric() }}) as reservation_net_unused_amortized_upfront_fee_for_billing_period,
        cast(reservation_unused_recurring_fee as {{ dbt.type_numeric() }}) as reservation_unused_recurring_fee,
        cast(reservation_net_unused_recurring_fee as {{ dbt.type_numeric() }}) as reservation_net_unused_recurring_fee,
        cast(expected_amortized_cost as {{ dbt.type_numeric() }}) as expected_amortized_cost,
        cast(expected_net_amortized_cost as {{ dbt.type_numeric() }}) as expected_net_amortized_cost
    from {{ ref('seed_aws_cur_all_types') }}
)

select
    test_case_id,
    line_item_line_item_type,
    expected_amortized_cost,
    {{ aws_cur_amortized_cost() }} as calculated_amortized_cost,
    expected_net_amortized_cost,
    {{ aws_cur_net_amortized_cost() }} as calculated_net_amortized_cost
from seed_rows

