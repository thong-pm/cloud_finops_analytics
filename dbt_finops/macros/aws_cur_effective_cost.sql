{% macro aws_cur_amortized_cost(
    line_item_type_col='line_item_line_item_type',
    unblended_cost_col='line_item_unblended_cost',
    sp_effective_cost_col='savings_plan_savings_plan_effective_cost',
    ri_effective_cost_col='reservation_effective_cost',
    ri_unused_amortized_upfront_col='reservation_unused_amortized_upfront_fee_for_billing_period',
    ri_unused_recurring_col='reservation_unused_recurring_fee'
) %}
    case
        when {{ line_item_type_col }} = 'SavingsPlanCoveredUsage'
            then coalesce({{ sp_effective_cost_col }}, 0)
        when {{ line_item_type_col }} = 'SavingsPlanRecurringFee'
            then coalesce(savings_plan_total_commitment_to_date, 0) - coalesce(savings_plan_used_commitment, 0)
        when {{ line_item_type_col }} = 'SavingsPlanNegation'
            then 0
        when {{ line_item_type_col }} = 'SavingsPlanUpfrontFee'
            then 0
        when {{ line_item_type_col }} = 'DiscountedUsage'
            then coalesce({{ ri_effective_cost_col }}, 0)
        when {{ line_item_type_col }} = 'RIFee'
            then coalesce({{ ri_unused_amortized_upfront_col }}, 0) + coalesce({{ ri_unused_recurring_col }}, 0)
        when {{ line_item_type_col }} = 'Fee'
            and reservation_reservation_a_r_n is not null
            and reservation_reservation_a_r_n != ''
            then 0
        else coalesce({{ unblended_cost_col }}, 0)
    end
{% endmacro %}

{% macro aws_cur_net_amortized_cost(
    line_item_type_col='line_item_line_item_type',
    unblended_cost_col='line_item_unblended_cost',
    net_unblended_cost_col='line_item_net_unblended_cost',
    sp_effective_cost_col='savings_plan_savings_plan_effective_cost',
    sp_net_effective_cost_col='savings_plan_net_savings_plan_effective_cost',
    ri_effective_cost_col='reservation_effective_cost',
    ri_net_effective_cost_col='reservation_net_effective_cost',
    ri_unused_amortized_upfront_col='reservation_unused_amortized_upfront_fee_for_billing_period',
    ri_net_unused_amortized_upfront_col='reservation_net_unused_amortized_upfront_fee_for_billing_period',
    ri_unused_recurring_col='reservation_unused_recurring_fee',
    ri_net_unused_recurring_col='reservation_net_unused_recurring_fee'
) %}
    case
        when {{ line_item_type_col }} = 'SavingsPlanCoveredUsage'
            then coalesce({{ sp_net_effective_cost_col }}, {{ sp_effective_cost_col }}, 0)
        when {{ line_item_type_col }} = 'SavingsPlanRecurringFee'
            then (
                coalesce(savings_plan_total_commitment_to_date, 0) - coalesce(savings_plan_used_commitment, 0)
            ) * coalesce(
                coalesce(
                    savings_plan_net_amortized_upfront_commitment_for_billing_period,
                    savings_plan_amortized_upfront_commitment_for_billing_period
                ) / nullif(savings_plan_amortized_upfront_commitment_for_billing_period, 0),
                1.0
            )
        when {{ line_item_type_col }} = 'SavingsPlanNegation'
            then 0
        when {{ line_item_type_col }} = 'SavingsPlanUpfrontFee'
            then 0
        when {{ line_item_type_col }} = 'DiscountedUsage'
            then coalesce({{ ri_net_effective_cost_col }}, {{ ri_effective_cost_col }}, 0)
        when {{ line_item_type_col }} = 'RIFee'
            then coalesce({{ ri_net_unused_amortized_upfront_col }}, {{ ri_unused_amortized_upfront_col }}, 0)
               + coalesce({{ ri_net_unused_recurring_col }}, {{ ri_unused_recurring_col }}, 0)
        when {{ line_item_type_col }} = 'Fee'
            and reservation_reservation_a_r_n is not null
            and reservation_reservation_a_r_n != ''
            then 0
        else coalesce({{ net_unblended_cost_col }}, {{ unblended_cost_col }}, 0)
    end
{% endmacro %}
