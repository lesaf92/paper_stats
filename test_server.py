"""Offline checks for Flask deployment controls and configuration validation."""
from unittest.mock import patch

import server


def test_read_only_mode():
    with patch.object(server, 'READ_ONLY', True):
        client = server.app.test_client()
        response = client.get('/')
        page = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'action="/run"' not in page
        assert 'Save Configuration' not in page
        assert client.post('/run').status_code == 403
        assert client.post('/save_config', data={
            'num_samples': '10', 'year_start': '2020', 'year_end': '2025'
        }).status_code == 403


def test_configuration_bounds():
    bad_forms = [
        {'num_samples': 'abc', 'year_start': '2020', 'year_end': '2025'},
        {'num_samples': str(server.MAX_SAMPLES_PER_JOURNAL + 1), 'year_start': '2020', 'year_end': '2025'},
        {'num_samples': '1', 'year_start': str(server.MIN_PUBLICATION_YEAR - 1), 'year_end': '2020'},
        {'num_samples': '1', 'year_start': '2020', 'year_end': str(server.MAX_PUBLICATION_YEAR + 1)},
        {'num_samples': '1', 'year_start': '2025', 'year_end': '2024'},
    ]
    with patch.object(server, 'READ_ONLY', False), patch.object(server, 'save_config') as save_config:
        client = server.app.test_client()
        for form in bad_forms:
            response = client.post('/save_config', data=form)
            assert response.status_code == 302
        save_config.assert_not_called()


def test_configuration_boundaries_are_accepted():
    form = {
        'num_samples': str(server.MAX_SAMPLES_PER_JOURNAL),
        'year_start': str(server.MIN_PUBLICATION_YEAR),
        'year_end': str(server.MAX_PUBLICATION_YEAR),
    }
    with patch.object(server, 'READ_ONLY', False), patch.object(server, 'save_config') as save_config:
        response = server.app.test_client().post('/save_config', data=form)
        assert response.status_code == 302
        save_config.assert_called_once_with({
            'num_samples': server.MAX_SAMPLES_PER_JOURNAL,
            'year_start': server.MIN_PUBLICATION_YEAR,
            'year_end': server.MAX_PUBLICATION_YEAR,
            'mine_pdfs': False,
        })


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
    print('All checks passed.')
