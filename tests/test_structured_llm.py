import json
from typing import ClassVar

import pytest
from finrisk.llm import StructuredLLMProvider


def response(content, prompt=10, completion=5):
    return {"choices":[{"message":{"content":json.dumps(content)}}],"usage":{"prompt_tokens":prompt,"completion_tokens":completion}}


def claim_output(page=2, polarity="positive"):
    return {"claim":"Liquidity is strong.","risk_category":"liquidity","page":page,"evidence_text":"Liquidity is strong.","confidence":.9,"polarity":polarity,"claim_target":"overall_liquidity","direction":polarity,"time_horizon":"next_12_months","basis":"management_statement","qualifiers":[],"required_evidence_types":["liquidity_position","cash_generation","funding_pressure"]}


def test_structured_provider_validates_and_logs_without_network(tmp_path):
    provider=StructuredLLMProvider(transport=lambda _:response({"claims":[claim_output()]}),log_path=tmp_path/"calls.jsonl",input_cost_per_million=1,output_cost_per_million=2)
    claims=provider.extract({2:"Liquidity is strong."},"10-K",2024)
    assert claims[0].evidence.page==2 and provider.call_logs[0].estimated_cost_usd==.00002
    assert provider.call_logs[0].schema_valid and len(provider.call_logs[0].input_hash) == 64
    assert provider.call_logs[0].max_tokens == 1200
    assert (tmp_path/"calls.jsonl").exists()


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///tmp/provider",
        "ftp://provider.example/api",
        "http://provider.example/api",
        "https://user:secret@provider.example/api",
    ],
)
def test_structured_provider_rejects_unsafe_endpoints(endpoint):
    with pytest.raises(ValueError, match="HTTPS"):
        StructuredLLMProvider(endpoint=endpoint, transport=lambda _: {})


def test_structured_provider_allows_loopback_http_for_local_compatible_servers():
    provider = StructuredLLMProvider(
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        transport=lambda _: {},
    )
    assert provider.endpoint.startswith("http://127.0.0.1:")


def test_structured_provider_does_not_retry_schema_failure():
    calls=[]
    def transport(_):
        calls.append(1)
        return response({"wrong":[]}) if len(calls)==1 else response({"claims":[]})
    provider=StructuredLLMProvider(transport=transport,max_retries=1)
    with pytest.raises(RuntimeError):
        provider.extract({1:"text"},"10-K",2024)
    assert len(calls)==1


def test_structured_provider_context_and_logs_are_request_bounded():
    provider=StructuredLLMProvider(transport=lambda _:response({"claims":[]}),max_input_chars=12,max_page_chars=8)
    payload=provider._payload({1:"a"*20,2:"b"*20},"10-K",2024)
    source=payload["messages"][1]["content"]
    assert "a"*8 in source and "b"*4 in source and "b"*5 not in source
    provider.extract({1:"first"},"10-K",2024)
    assert len(provider.call_logs)==1
    provider.extract({1:"second"},"10-K",2024)
    assert len(provider.call_logs)==1


def test_structured_provider_rejects_page_outside_source():
    provider=StructuredLLMProvider(transport=lambda _:response({"claims":[claim_output(page=9, polarity="neutral")]}),max_retries=0)
    with pytest.raises(RuntimeError): provider.extract({1:"Text"},"10-K",2024)


def test_http_transport_bounds_and_decodes_provider_response(monkeypatch):
    body = json.dumps(response({"claims": []})).encode()

    class HttpResponse:
        headers: ClassVar[dict[str, str]] = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, amount):
            assert amount == StructuredLLMProvider.MAX_RESPONSE_BYTES + 1
            return body

    monkeypatch.setattr("finrisk.llm.urllib.request.urlopen", lambda *_, **__: HttpResponse())
    provider = StructuredLLMProvider(api_key="test-key")
    assert provider._http_transport({"messages": []})["choices"]

    class Oversized(HttpResponse):
        headers: ClassVar[dict[str, str]] = {
            "Content-Length": str(StructuredLLMProvider.MAX_RESPONSE_BYTES + 1)
        }

    monkeypatch.setattr("finrisk.llm.urllib.request.urlopen", lambda *_, **__: Oversized())
    with pytest.raises(ValueError, match="size limit"):
        provider._http_transport({"messages": []})
