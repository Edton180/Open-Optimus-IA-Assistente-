"""Celular: QR code para abrir o Optimus no telefone e agenda dos lembretes no calendário.

- `endereco_rede` descobre o IP deste PC na rede de casa (sem mandar nada para a internet: um
  socket UDP "conectado" não envia pacote, só escolhe a placa de rede).
- `qr_svg` / `qr_terminal` desenham o QR code (pacote opcional `segno`; sem ele, mostra o link).
- `agenda_ics` gera um calendário iCalendar (RFC 5545) com os lembretes pendentes. No iPhone:
  Ajustes > Calendário > Contas > Adicionar conta > Outra > Calendário assinado, e cole o link
  `/api/agenda.ics?chave=...`. O Google Agenda e o Outlook também aceitam o mesmo link.
"""

from __future__ import annotations

import datetime as dt
import io
import secrets
import socket
from typing import Any


def ip_local() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # não envia nada; só escolhe a interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def endereco_rede(porta: int, host: str = "0.0.0.0") -> str:
    ip = ip_local() if host in ("0.0.0.0", "", "::") else host
    return f"http://{ip}:{porta}"


def _qr(texto: str):
    try:
        import segno
    except ImportError:
        return None
    return segno.make(texto, error="m")


def qr_svg(texto: str) -> str:
    """SVG do QR code, ou "" se o pacote `segno` não estiver instalado."""
    qr = _qr(texto)
    if qr is None:
        return ""
    saida = io.BytesIO()
    qr.save(saida, kind="svg", scale=6, border=2, dark="#000", light="#fff", xmldecl=False)
    return saida.getvalue().decode("utf-8")


def qr_terminal(texto: str) -> bool:
    qr = _qr(texto)
    if qr is None:
        return False
    try:
        qr.terminal(compact=True)
        return True
    except Exception:  # noqa: BLE001 - terminal sem suporte a esses caracteres
        return False


def token_agenda(config) -> str:
    """Chave do link da agenda (criada na primeira vez). O app de calendário não manda senha."""
    atual = config.get("web", "token_agenda", "") or ""
    if not atual:
        atual = secrets.token_urlsafe(18)
        config.definir("web", "token_agenda", atual)
        if getattr(config, "caminho", None):
            config.salvar()
    return atual


# ---------------------------------------------------------------------- iCalendar
def _escapar(t: str) -> str:
    return (t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _dobrar(linha: str) -> str:
    """Linhas de no máximo 75 bytes (RFC 5545 §3.1), continuando com um espaço."""
    partes, atual = [], b""
    for c in linha:
        b = c.encode("utf-8")
        if len(atual) + len(b) > (75 if not partes else 74):
            partes.append(atual.decode("utf-8"))
            atual = b""
        atual += b
    partes.append(atual.decode("utf-8"))
    return "\r\n ".join(partes)


def _utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _regra(minutos: int) -> str:
    if minutos <= 0:
        return ""
    if minutos % 10080 == 0:
        return f"RRULE:FREQ=WEEKLY;INTERVAL={minutos // 10080}"
    if minutos % 1440 == 0:
        return f"RRULE:FREQ=DAILY;INTERVAL={minutos // 1440}"
    if minutos % 60 == 0:
        return f"RRULE:FREQ=HOURLY;INTERVAL={minutos // 60}"
    return f"RRULE:FREQ=MINUTELY;INTERVAL={minutos}"


def agenda_ics(lembretes: list[dict[str, Any]], nome: str = "Optimus",
               agora: float | None = None) -> str:
    carimbo = _utc(agora if agora is not None else dt.datetime.now().timestamp())
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Open Optimus//Agenda//PT",
              "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_escapar(nome)}",
              "REFRESH-INTERVAL;VALUE=DURATION:PT15M", "X-PUBLISHED-TTL:PT15M"]
    for item in lembretes:
        inicio = float(item["quando"])
        linhas += ["BEGIN:VEVENT", f"UID:lembrete-{item['id']}@open-optimus",
                   f"DTSTAMP:{carimbo}", f"DTSTART:{_utc(inicio)}",
                   f"DTEND:{_utc(inicio + 15 * 60)}",
                   f"SUMMARY:{_escapar(str(item['texto']))}"]
        regra = _regra(int(item.get("repetir_minutos") or 0))
        if regra:
            linhas.append(regra)
        linhas += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escapar(str(item['texto']))}",
                   "TRIGGER:PT0M", "END:VALARM", "END:VEVENT"]
    linhas.append("END:VCALENDAR")
    return "\r\n".join(_dobrar(x) for x in linhas) + "\r\n"
