"""Tests para el cliente iBus."""

import time

import pytest

from red_transporte_api.clients.ibus import IBusClient, _parse_ibus_html


# HTML que emula la respuesta real de m.ibus.cl
SAMPLE_IBUS_HTML = """
<html><body>
<table class="cabecera4">
<tr><td>Paradero</td><td>:</td><td>PA433</td></tr>
<tr><td>Nombre</td><td>:</td><td>Av. Providencia / Los Leones</td></tr>
<tr><td>Hora consulta</td><td>:</td><td>12:30 hrs.</td></tr>
</table>
<table>
<tr><td class="menu_respuesta_cabecera">Servicio</td></tr>
<tr>
    <td class="menu_respuesta" rowspan="2">506</td>
    <td class="menu_respuesta">BJFG-12</td>
    <td class="menu_respuesta">Entre 03 y 07 min.</td>
    <td class="menu_respuesta">1234</td>
</tr>
<tr>
    <td class="menu_respuesta">CDEF-34</td>
    <td class="menu_respuesta">Entre 10 y 15 min.</td>
    <td class="menu_respuesta">3456</td>
</tr>
<tr>
    <td class="menu_respuesta">D12</td>
    <td class="menu_respuesta">WXYZ-99</td>
    <td class="menu_respuesta">Llegando.</td>
    <td class="menu_respuesta">500</td>
</tr>
</table>
</body></html>
"""


class TestIBusParser:
    """Test del parser HTML de iBus (sin red)."""

    def test_parse_html(self):
        result = _parse_ibus_html(SAMPLE_IBUS_HTML)
        assert result is not None
        assert result["paradero"]["codigo"] == "PA433"
        assert result["paradero"]["nombre"] == "Av. Providencia / Los Leones"

        servicios = result.get("servicios", [])
        assert len(servicios) >= 1

    def test_parse_empty_html_raises(self):
        with pytest.raises(ValueError):
            _parse_ibus_html("<html><body></body></html>")


class TestIBusCache:
    """Test del mecanismo de cache TTL."""

    def test_cache_stores_result(self):
        client = IBusClient(cache_ttl=5)
        key = client._cache_key("PA433", "")
        data = {"paradero": {"codigo": "PA433"}, "servicios": []}
        client._cache[key] = (time.monotonic(), data)
        cached = client._get_cached(key)
        assert cached is not None
        assert cached["paradero"]["codigo"] == "PA433"

    def test_cache_expires(self):
        client = IBusClient(cache_ttl=1)
        key = client._cache_key("PA433", "")
        data = {"paradero": {"codigo": "PA433"}, "servicios": []}
        client._cache[key] = (time.monotonic() - 10, data)
        cached = client._get_cached(key)
        assert cached is None
