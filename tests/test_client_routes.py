import os
import json
import tempfile
from unittest.mock import patch


def test_load_mihomo_state_initializes_client_route_overrides():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{}')
        path = f.name
    try:
        from app import load_mihomo_state, save_mihomo_state
        with patch('app.MIHOMO_STATE_FILE', path):
            state = load_mihomo_state()
            assert state.get('client_route_overrides') == {}
            state['client_route_overrides'] = {'192.168.50.141': {'plex.tv': 'AI'}}
            save_mihomo_state(state)
            with open(path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            assert saved['client_route_overrides']['192.168.50.141']['plex.tv'] == 'AI'
    finally:
        os.unlink(path)
