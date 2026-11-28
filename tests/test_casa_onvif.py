import re

from optimus.tools.casa import _extrair_xaddrs_onvif, _mensagem_probe_onvif


def test_extrai_endpoints_http_onvif_sem_duplicar():
    xml = b"""<?xml version="1.0"?>
    <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
      xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <s:Body><d:ProbeMatches><d:ProbeMatch>
        <d:XAddrs>http://192.168.1.20/onvif/device_service https://cam.local/onvif/device_service</d:XAddrs>
      </d:ProbeMatch><d:ProbeMatch>
        <d:XAddrs>http://192.168.1.20/onvif/device_service</d:XAddrs>
      </d:ProbeMatch></d:ProbeMatches></s:Body></s:Envelope>"""
    assert _extrair_xaddrs_onvif(xml) == [
        "http://192.168.1.20/onvif/device_service",
        "https://cam.local/onvif/device_service",
    ]


def test_rejeita_endpoints_com_credenciais_embutidas_e_esquemas_nao_http():
    xml = b"""<Envelope><XAddrs>
      http://user:secret@192.168.1.20/onvif/device_service
      ftp://192.168.1.20/onvif
      javascript:alert(1)
      http://192.168.1.21/onvif/device_service
    </XAddrs></Envelope>"""
    assert _extrair_xaddrs_onvif(xml) == [
        "http://192.168.1.21/onvif/device_service"
    ]


def test_xml_invalido_nao_interrompe_descoberta():
    assert _extrair_xaddrs_onvif(b"<Envelope><XAddrs>") == []



def test_probe_usa_uuid_valido_e_unico_em_cada_requisicao():
    primeira = _mensagem_probe_onvif().decode("utf-8")
    segunda = _mensagem_probe_onvif().decode("utf-8")
    padrao = r"<w:MessageID>urn:uuid:([0-9a-fA-F-]{36})</w:MessageID>"
    id_primeiro = re.search(padrao, primeira)
    id_segundo = re.search(padrao, segunda)
    assert id_primeiro is not None
    assert id_segundo is not None
    assert id_primeiro.group(1) != id_segundo.group(1)
    assert primeira.count("<d:Probe>") == 1
