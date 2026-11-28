"""Endereço seguro (https) para o celular: o navegador só libera o microfone e a câmera em
https ou em localhost. Pela rede de casa (http://192.168.x.x) o microfone não abre.

O Optimus cria um certificado próprio deste PC (autoassinado), válido para os IPs da rede de
casa, e abre uma porta https ao lado da porta do celular. Na primeira vez o navegador avisa
que não conhece quem assinou: toque em "Avançado" e "Continuar". Depois o microfone funciona.

O certificado e a chave ficam em `~/.optimus/web/` e nunca saem do PC. Ele é criado com o
pacote `cryptography` (vem no extra [celular]) ou, sem ele, com o comando `openssl`.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import logging
import shutil
import ssl
import subprocess
from pathlib import Path

from optimus.config import pasta_base

log = logging.getLogger(__name__)


def pasta() -> Path:
    return pasta_base() / "web"


def arquivos() -> tuple[Path, Path]:
    return pasta() / "optimus-cert.pem", pasta() / "optimus-chave.pem"


def _ips_salvos() -> list[str]:
    try:
        return json.loads((pasta() / "optimus-cert.json").read_text(encoding="utf-8"))["ips"]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _com_cryptography(ips: list[str], cert: Path, chave: Path) -> bool:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError:
        return False
    k = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Open Optimus (este PC)")])
    agora = dt.datetime.now(dt.timezone.utc)
    nomes = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    certificado = (
        x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
        .public_key(k.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(days=1))
        .not_valid_after(agora + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(nomes), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(k, hashes.SHA256()))
    chave.write_bytes(k.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    cert.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    return True


def _com_openssl(ips: list[str], cert: Path, chave: Path) -> bool:
    openssl = shutil.which("openssl")
    if not openssl:
        return False
    nomes = ",".join(["DNS:localhost", *(f"IP:{i}" for i in ips)])
    r = subprocess.run(
        [openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
         "-nodes", "-keyout", str(chave), "-out", str(cert), "-days", "825",
         "-subj", "/CN=Open Optimus (este PC)", "-addext", f"subjectAltName={nomes}"],
        capture_output=True, timeout=60, check=False)
    return r.returncode == 0 and cert.exists() and chave.exists()


def garantir(ips: list[str]) -> tuple[Path, Path] | None:
    """Cria (ou recria, se o IP do PC mudou) o certificado. None se não houver como criar."""
    validos = []
    for ip in dict.fromkeys(["127.0.0.1", *ips]):
        try:
            ipaddress.ip_address(ip)
            validos.append(ip)
        except ValueError:
            continue
    cert, chave = arquivos()
    if cert.exists() and chave.exists() and set(validos) <= set(_ips_salvos()):
        return cert, chave
    pasta().mkdir(parents=True, exist_ok=True)
    try:
        feito = _com_cryptography(validos, cert, chave) or _com_openssl(validos, cert, chave)
    except Exception:  # noqa: BLE001 - sem https o resto continua funcionando
        log.exception("Não consegui criar o certificado do https")
        feito = False
    if not feito:
        return None
    try:
        chave.chmod(0o600)
    except OSError:
        pass
    (pasta() / "optimus-cert.json").write_text(json.dumps({"ips": validos}), encoding="utf-8")
    return cert, chave


def contexto(ips: list[str]) -> ssl.SSLContext | None:
    par = garantir(ips)
    if not par:
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(par[0]), str(par[1]))
    return ctx
