import json

import pytest
from finrisk.llm import StructuredLLMProvider


def response(content, prompt=10, completion=5):
    return {"choices":[{"message":{"content":json.dumps(content)}}],"usage":{"prompt_tokens":prompt,"completion_tokens":completion}}


def test_structured_provider_validates_and_logs_without_network(tmp_path):
    provider=StructuredLLMProvider(transport=lambda _:response({"claims":[{"claim":"Liquidity is strong.","risk_category":"liquidity","page":2,"evidence_text":"Liquidity is strong.","confidence":.9,"polarity":"positive"}]}),log_path=tmp_path/"calls.jsonl",input_cost_per_million=1,output_cost_per_million=2)
    claims=provider.extract({2:"Liquidity is strong."},"10-K",2024)
    assert claims[0].evidence.page==2 and provider.call_logs[0].estimated_cost_usd==.00002
    assert (tmp_path/"calls.jsonl").exists()


def test_structured_provider_retries_schema_failure():
    calls=[]
    def transport(_):
        calls.append(1)
        return response({"wrong":[]}) if len(calls)==1 else response({"claims":[]})
    provider=StructuredLLMProvider(transport=transport,max_retries=1)
    assert provider.extract({1:"text"},"10-K",2024)==[] and len(calls)==2


def test_structured_provider_rejects_page_outside_source():
    provider=StructuredLLMProvider(transport=lambda _:response({"claims":[{"claim":"Claim","risk_category":"liquidity","page":9,"evidence_text":"Text","confidence":.5,"polarity":"neutral"}]}),max_retries=0)
    with pytest.raises(RuntimeError): provider.extract({1:"Text"},"10-K",2024)
