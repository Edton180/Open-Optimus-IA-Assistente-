"""Idiomas do estúdio. O português do Brasil é o idioma principal, em todos os motores."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Idioma:
    codigo: str  # pt-BR, en-US...
    nome: str  # como a pessoa fala: "português do Brasil"
    whisper: str  # código do reconhecimento (pt, en...)
    edge_f: str = ""  # vozes neurais online (feminina, masculina)
    edge_m: str = ""
    kokoro: str = ""  # idioma no Kokoro (offline), se houver
    clone: str = ""  # idioma no motor de clonagem (Chatterbox Multilingual)
    instrucao: str = ""  # como pedir a tradução ao modelo de IA


IDIOMAS: list[Idioma] = [
    Idioma("pt-BR", "português do Brasil", "pt", "pt-BR-FranciscaNeural", "pt-BR-AntonioNeural",
           "pt-br", "pt", "português do Brasil (pt-BR), natural e coloquial como se fala no "
           "Brasil, com vocabulário brasileiro (ônibus, celular, trem, café da manhã) e nunca "
           "português de Portugal"),
    Idioma("pt-PT", "português de Portugal", "pt", "pt-PT-RaquelNeural", "pt-PT-DuarteNeural",
           "", "pt", "português europeu (pt-PT)"),
    Idioma("en-US", "inglês", "en", "en-US-JennyNeural", "en-US-GuyNeural", "en-us", "en",
           "American English"),
    Idioma("en-GB", "inglês britânico", "en", "en-GB-SoniaNeural", "en-GB-RyanNeural", "en-gb",
           "en", "British English"),
    Idioma("es-ES", "espanhol", "es", "es-ES-ElviraNeural", "es-ES-AlvaroNeural", "es", "es",
           "español de España"),
    Idioma("es-MX", "espanhol latino", "es", "es-MX-DaliaNeural", "es-MX-JorgeNeural", "es",
           "es", "español latinoamericano neutro"),
    Idioma("fr-FR", "francês", "fr", "fr-FR-DeniseNeural", "fr-FR-HenriNeural", "fr-fr", "fr",
           "français"),
    Idioma("de-DE", "alemão", "de", "de-DE-KatjaNeural", "de-DE-ConradNeural", "", "de",
           "Deutsch"),
    Idioma("it-IT", "italiano", "it", "it-IT-ElsaNeural", "it-IT-DiegoNeural", "it", "it",
           "italiano"),
    Idioma("ja-JP", "japonês", "ja", "ja-JP-NanamiNeural", "ja-JP-KeitaNeural", "ja", "ja",
           "日本語"),
    Idioma("zh-CN", "chinês", "zh", "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh", "zh",
           "简体中文"),
    Idioma("ko-KR", "coreano", "ko", "ko-KR-SunHiNeural", "ko-KR-InJoonNeural", "", "ko",
           "한국어"),
    Idioma("ru-RU", "russo", "ru", "ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural", "", "ru",
           "русский"),
    Idioma("ar-SA", "árabe", "ar", "ar-SA-ZariyahNeural", "ar-SA-HamedNeural", "", "ar",
           "العربية الفصحى"),
    Idioma("hi-IN", "hindi", "hi", "hi-IN-SwaraNeural", "hi-IN-MadhurNeural", "hi", "hi",
           "हिन्दी"),
    Idioma("nl-NL", "holandês", "nl", "nl-NL-ColetteNeural", "nl-NL-MaartenNeural", "", "nl",
           "Nederlands"),
    Idioma("pl-PL", "polonês", "pl", "pl-PL-ZofiaNeural", "pl-PL-MarekNeural", "", "pl",
           "polski"),
    Idioma("tr-TR", "turco", "tr", "tr-TR-EmelNeural", "tr-TR-AhmetNeural", "", "tr", "Türkçe"),
]

PADRAO = "pt-BR"
_POR_CODIGO = {i.codigo.lower(): i for i in IDIOMAS}
_APELIDOS = {
    "pt": "pt-BR", "pt-br": "pt-BR", "ptbr": "pt-BR", "portugues": "pt-BR", "brasil": "pt-BR",
    "portugues do brasil": "pt-BR", "portugues brasileiro": "pt-BR", "brasileiro": "pt-BR",
    "portugues de portugal": "pt-PT", "europeu": "pt-PT", "en": "en-US", "ingles": "en-US",
    "english": "en-US", "americano": "en-US", "britanico": "en-GB", "es": "es-ES",
    "espanhol": "es-ES", "castelhano": "es-ES", "spanish": "es-ES", "latino": "es-MX",
    "espanhol latino": "es-MX", "mexicano": "es-MX", "fr": "fr-FR", "frances": "fr-FR",
    "de": "de-DE", "alemao": "de-DE", "it": "it-IT", "italiano": "it-IT", "ja": "ja-JP",
    "japones": "ja-JP", "zh": "zh-CN", "chines": "zh-CN", "mandarim": "zh-CN", "ko": "ko-KR",
    "coreano": "ko-KR", "ru": "ru-RU", "russo": "ru-RU", "ar": "ar-SA", "arabe": "ar-SA",
    "hi": "hi-IN", "hindi": "hi-IN", "nl": "nl-NL", "holandes": "nl-NL", "pl": "pl-PL",
    "polones": "pl-PL", "tr": "tr-TR", "turco": "tr-TR",
}


def _normal(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower().replace("_", "-"))
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def idioma(nome: str | None) -> Idioma:
    """Acha o idioma por código ou nome ("inglês", "en", "pt-BR"). Padrão: português do Brasil."""
    if not nome:
        return _POR_CODIGO[PADRAO.lower()]
    t = _normal(nome)
    t = t.removeprefix("para ").removeprefix("em ").strip()
    if t in _POR_CODIGO:
        return _POR_CODIGO[t]
    if t in _APELIDOS:
        return _POR_CODIGO[_APELIDOS[t].lower()]
    raise ValueError(f"Idioma não suportado: {nome}. Use, por exemplo: "
                     + ", ".join(i.nome for i in IDIOMAS[:8]) + "...")


def do_whisper(codigo: str) -> Idioma:
    """Idioma a partir do código que o reconhecimento detectou ('pt' vira pt-BR)."""
    for i in IDIOMAS:
        if i.whisper == codigo:
            return i
    return idioma(codigo)


def voz_edge(i: Idioma, genero: str = "feminina") -> str:
    return i.edge_m if genero.startswith("m") and i.edge_m else i.edge_f
