import io
from unittest.mock import MagicMock, patch


# Minimal valid JPEG bytes (SOI marker only — enough for Pillow/file detection)
FAKE_JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 16


class TestScanCard:
    def test_returns_400_when_api_key_not_configured(self, client):
        """No anthropic_api_key in CONFIG → 400 with clear error."""
        with patch.dict('app.CONFIG', {}, clear=False):
            # Ensure key is absent
            import app as app_module
            app_module.CONFIG.pop('anthropic_api_key', None)
            resp = client.post('/api/scan-card')
        assert resp.status_code == 400
        assert 'anthropic_api_key not configured' in resp.get_json()['error']

    def test_returns_400_when_no_image_files_provided(self, client):
        """API key present but no files → 400."""
        with patch.dict('app.CONFIG', {'anthropic_api_key': 'sk-ant-test'}):
            resp = client.post('/api/scan-card')
        assert resp.status_code == 400
        assert 'No valid image' in resp.get_json()['error']

    def test_returns_structured_fields_on_success(self, client):
        """Happy path: Claude returns JSON → endpoint returns same JSON."""
        claude_json = (
            '{"player":"Mike Trout","year":"2011","card_set":"Topps Update",'
            '"variation":null,"serial_number":null,"grade":null,'
            '"grader":null,"condition_raw":"NM-MT"}'
        )
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=claude_json)]

        with patch.dict('app.CONFIG', {'anthropic_api_key': 'sk-ant-test'}):
            with patch('app.anthropic.Anthropic') as MockClient:
                MockClient.return_value.messages.create.return_value = mock_msg
                resp = client.post(
                    '/api/scan-card',
                    data={'front': (io.BytesIO(FAKE_JPEG), 'front.jpg')},
                    content_type='multipart/form-data',
                )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['player'] == 'Mike Trout'
        assert data['year'] == '2011'
        assert data['card_set'] == 'Topps Update'
        assert data['variation'] is None

    def test_returns_500_on_claude_api_error(self, client):
        """Claude raises an exception → endpoint returns 500 with error message."""
        with patch.dict('app.CONFIG', {'anthropic_api_key': 'sk-ant-test'}):
            with patch('app.anthropic.Anthropic') as MockClient:
                MockClient.return_value.messages.create.side_effect = Exception('API timeout')
                resp = client.post(
                    '/api/scan-card',
                    data={'front': (io.BytesIO(FAKE_JPEG), 'front.jpg')},
                    content_type='multipart/form-data',
                )

        assert resp.status_code == 500
        assert 'API timeout' in resp.get_json()['error']
