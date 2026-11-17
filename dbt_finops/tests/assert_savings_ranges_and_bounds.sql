select
    opportunity_id,
    dataset_source,
    current_spend_or_list_exposure_usd,
    monthly_addressable_spend_usd,
    estimated_monthly_savings_low_usd,
    estimated_monthly_savings_usd,
    estimated_monthly_savings_high_usd,
    aws_doc_url
from {{ ref('mrt_savings_opportunities') }}
where estimated_monthly_savings_low_usd < 0
   or estimated_monthly_savings_low_usd > estimated_monthly_savings_usd
   or estimated_monthly_savings_usd > estimated_monthly_savings_high_usd
   or estimated_monthly_savings_high_usd > monthly_addressable_spend_usd
   or monthly_addressable_spend_usd > current_spend_or_list_exposure_usd
   or aws_doc_url is null
   or left(aws_doc_url, 8) != 'https://'
