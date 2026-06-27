import os
import json
import tempfile
from pathlib import Path
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


def test_inject_client_overrides_creates_rules():
    from app import _inject_client_overrides
    config = {'rules': ['DOMAIN-SUFFIX,google.com,Proxy', 'MATCH,Final']}
    overrides = {'192.168.50.141': {'plex.tv': 'AI'}}
    result = _inject_client_overrides(config, overrides)
    assert len(result['rules']) == 3
    assert result['rules'][0] == 'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI'
    assert result['rules'][1] == 'DOMAIN-SUFFIX,google.com,Proxy'
    assert result['rules'][2] == 'MATCH,Final'


def test_inject_client_overrides_creates_rules_list_if_missing():
    from app import _inject_client_overrides
    config = {}
    overrides = {'192.168.50.141': {'plex.tv': 'AI'}}
    result = _inject_client_overrides(config, overrides)
    assert result['rules'][0] == 'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI'


def test_inject_client_overrides_removes_old_and_rules():
    from app import _inject_client_overrides
    config = {'rules': [
        'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,old.tv)),Old',
        'MATCH,Final'
    ]}
    overrides = {'192.168.50.141': {'plex.tv': 'AI'}}
    result = _inject_client_overrides(config, overrides)
    assert all('old.tv' not in r for r in result['rules'])
    assert result['rules'][0] == 'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI'


def test_apply_mihomo_config_backup_and_writes():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / 'config.yaml'
        config_path.write_text('rules:\n  - MATCH,Final\n', encoding='utf-8')
        config = {'rules': ['AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI', 'MATCH,Final']}
        with patch('app.MIHOMO_CONFIG', str(config_path)):
            with patch('app.mihomo_put') as mock_put:
                from app import _apply_mihomo_config
                _apply_mihomo_config(config)
                text = config_path.read_text(encoding='utf-8')
                assert 'DOMAIN-SUFFIX,plex.tv' in text
                backups = list(Path(tmp).glob('config.yaml.bak.*'))
                assert len(backups) == 1
                assert 'MATCH,Final' in backups[0].read_text(encoding='utf-8')
                mock_put.assert_called_once()


def test_apply_mihomo_config_rollback_on_failure():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / 'config.yaml'
        original = 'rules:\n  - MATCH,Final\n'
        config_path.write_text(original, encoding='utf-8')
        config = {'rules': ['AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI', 'MATCH,Final']}
        with patch('app.MIHOMO_CONFIG', str(config_path)):
            with patch('app.mihomo_put', side_effect=RuntimeError('reload failed')):
                from app import _apply_mihomo_config
                try:
                    _apply_mihomo_config(config)
                except RuntimeError:
                    pass
                assert config_path.read_text(encoding='utf-8') == original
