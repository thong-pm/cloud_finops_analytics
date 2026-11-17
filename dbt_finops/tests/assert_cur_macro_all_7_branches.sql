select
    test_case_id,
    line_item_line_item_type,
    expected_amortized_cost,
    calculated_amortized_cost,
    expected_net_amortized_cost,
    calculated_net_amortized_cost
from {{ ref('stg_aws_cur_macro_validation') }}
where abs(calculated_amortized_cost - expected_amortized_cost) > 0.0001
   or abs(calculated_net_amortized_cost - expected_net_amortized_cost) > 0.0001

