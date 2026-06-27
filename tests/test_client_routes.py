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


def test_apply_mihomo_config_backup_install_restart():
    from app import _apply_mihomo_config
    config = {'rules': ['AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI', 'MATCH,Final']}
    with patch('app.subprocess.run') as mock_run:
        mock_run.return_value = type('R', (), {'returncode': 0, 'stderr': ''})()
        _apply_mihomo_config(config)
        calls = mock_run.call_args_list
        assert calls[0][0][0][:3] == ['sudo', '-n', 'cp']
        assert calls[1][0][0][:3] == ['sudo', '-n', 'install']
        assert calls[2][0][0][:3] == ['sudo', '-n', 'systemctl']


def test_apply_mihomo_config_rollback_on_restart_failure():
    from app import _apply_mihomo_config
    config = {'rules': ['AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI', 'MATCH,Final']}

    def side_effect(cmd, **kwargs):
        if 'systemctl' in cmd:
            return type('R', (), {'returncode': 1, 'stderr': 'restart failed'})()
        return type('R', (), {'returncode': 0, 'stderr': ''})()

    with patch('app.subprocess.run') as mock_run:
        mock_run.side_effect = side_effect
        try:
            _apply_mihomo_config(config)
        except RuntimeError as e:
            assert 'restart failed' in str(e)
        calls = mock_run.call_args_list
        assert len(calls) == 4
        assert calls[3][0][0][:3] == ['sudo', '-n', 'cp']  # rollback
