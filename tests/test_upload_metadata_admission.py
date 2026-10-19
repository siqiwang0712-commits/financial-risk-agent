"""Document metadata must be rejected before either isolated PDF worker."""
import pytest
from finrisk import api
from test_api_upload import authenticated_client, pdf_bytes


@pytest.mark.parametrize('company,year,filename', [
    ('x'*301, '2025', 'report.pdf'), ('', '2025', 'report.pdf'),
    ('valid', '1899', 'report.pdf'), ('valid', '2101', 'report.pdf'),
    ('valid', '2025', 'x'*501+'.pdf'),
])
def test_metadata_limits_precede_pdf_inspection(monkeypatch, company, year, filename):
    client, headers = authenticated_client()

    async def forbidden(*_):
        pytest.fail('invalid metadata must not start an expensive PDF worker')

    monkeypatch.setattr(api, '_run_inspect_isolated', forbidden)
    monkeypatch.setattr(api, '_run_document_isolated', forbidden)
    response = client.post('/api/v1/documents/analyze', headers=headers,
                           data={'company': company, 'fiscal_year': year},
                           files={'file': (filename, pdf_bytes('valid'), 'application/pdf')})
    assert response.status_code == 422
