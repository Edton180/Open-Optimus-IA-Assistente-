"""Idiomas do estúdio. O português do Brasil é o idioma principal, em todos os motores."""

from __future__ import annotations

import re
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


# Todos os idiomas que o reconhecimento (Whisper) entende: transcrever, legendar e traduzir.
# Para falar neles: vozes Edge do idioma (online), OmniVoice (600+ idiomas) ou clonagem.
WHISPER = {
    "af": "africâner", "am": "amárico", "ar": "árabe", "as": "assamês", "az": "azerbaijano",
    "ba": "bashkir", "be": "bielorrusso", "bg": "búlgaro", "bn": "bengali", "bo": "tibetano",
    "br": "bretão", "bs": "bósnio", "ca": "catalão", "cs": "tcheco", "cy": "galês",
    "da": "dinamarquês", "de": "alemão", "el": "grego", "en": "inglês", "es": "espanhol",
    "et": "estoniano", "eu": "basco", "fa": "persa", "fi": "finlandês", "fo": "feroês",
    "fr": "francês", "gl": "galego", "gu": "guzerate", "ha": "hauçá", "haw": "havaiano",
    "he": "hebraico", "hi": "hindi", "hr": "croata", "ht": "crioulo haitiano",
    "hu": "húngaro", "hy": "armênio", "id": "indonésio", "is": "islandês", "it": "italiano",
    "ja": "japonês", "jw": "javanês", "ka": "georgiano", "kk": "cazaque", "km": "khmer",
    "kn": "canarês", "ko": "coreano", "la": "latim", "lb": "luxemburguês", "ln": "lingala",
    "lo": "laosiano", "lt": "lituano", "lv": "letão", "mg": "malgaxe", "mi": "maori",
    "mk": "macedônio", "ml": "malaiala", "mn": "mongol", "mr": "marati", "ms": "malaio",
    "mt": "maltês", "my": "birmanês", "ne": "nepalês", "nl": "holandês", "nn": "norueguês nynorsk",
    "no": "norueguês", "oc": "occitano", "pa": "punjabi", "pl": "polonês", "ps": "pashto",
    "pt": "português", "ro": "romeno", "ru": "russo", "sa": "sânscrito", "sd": "sindi",
    "si": "cingalês", "sk": "eslovaco", "sl": "esloveno", "sn": "shona", "so": "somali",
    "sq": "albanês", "sr": "sérvio", "su": "sundanês", "sv": "sueco", "sw": "suaíli",
    "ta": "tâmil", "te": "telugo", "tg": "tadjique", "th": "tailandês", "tk": "turcomeno",
    "tl": "tagalo", "tr": "turco", "tt": "tártaro", "uk": "ucraniano", "ur": "urdu",
    "uz": "uzbeque", "vi": "vietnamita", "yi": "iídiche", "yo": "iorubá", "yue": "cantonês",
    "zh": "chinês",
}
# Idiomas que a clonagem Chatterbox Multilingual fala
CLONE = {"ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja", "ko", "ms",
         "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh"}
_POR_NOME = {_n: c for c, _n in WHISPER.items()}
_CODIGO_LIVRE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")


def _extra(codigo: str, nome: str = "") -> Idioma:
    base = codigo.split("-")[0]
    nome = nome or WHISPER.get(base, codigo)
    return Idioma(codigo, nome, base if base in WHISPER else "", "", "", "",
                  base if base in CLONE else "", nome)


def idioma(nome: str | None) -> Idioma:
    """Acha o idioma por código ou nome ("inglês", "en", "pt-BR", "ucraniano", "sw").

    Padrão: português do Brasil. Além dos 18 principais, aceita os ~100 idiomas do Whisper
    pelo nome ou código e qualquer código de idioma (ISO 639) para o OmniVoice."""
    if not nome:
        return _POR_CODIGO[PADRAO.lower()]
    t = _normal(nome)
    t = t.removeprefix("para ").removeprefix("em ").strip()
    if t in _POR_CODIGO:
        return _POR_CODIGO[t]
    if t in _APELIDOS:
        return _POR_CODIGO[_APELIDOS[t].lower()]
    for nome_pt, codigo in _POR_NOME.items():
        if _normal(nome_pt) == t:
            return _extra(codigo, nome_pt)
    if _CODIGO_LIVRE.match(t):
        base = t.split("-")[0]
        principal = next((i for i in IDIOMAS if i.whisper == base), None)
        if principal and "-" not in t:
            return principal
        return _extra(t if "-" not in t else base + "-" + t.split("-")[1].upper())
    raise ValueError(f"Idioma não suportado: {nome}. Use, por exemplo: "
                     + ", ".join(i.nome for i in IDIOMAS[:8]) + "...")


def todos() -> list[Idioma]:
    """Os 18 principais e depois os demais do reconhecimento, em ordem alfabética."""
    vistos = {i.whisper for i in IDIOMAS}
    extras = sorted((_extra(c) for c in WHISPER if c not in vistos), key=lambda i: _normal(i.nome))
    return IDIOMAS + extras


def do_whisper(codigo: str) -> Idioma:
    """Idioma a partir do código que o reconhecimento detectou ('pt' vira pt-BR)."""
    for i in IDIOMAS:
        if i.whisper == codigo:
            return i
    return idioma(codigo)


_VOZES_EDGE: list[dict] = []


def _lista_edge() -> list[dict]:
    """Vozes do Edge (online), uma vez por sessão. Vazio sem internet."""
    if not _VOZES_EDGE:
        try:
            import asyncio
            import threading

            import edge_tts

            resultado: list = []

            def buscar() -> None:
                try:
                    resultado.extend(asyncio.run(edge_tts.list_voices()))
                except Exception:  # noqa: BLE001 - sem internet
                    pass

            linha = threading.Thread(target=buscar, daemon=True)
            linha.start()
            linha.join(15)
            _VOZES_EDGE.extend(resultado)
        except ImportError:
            pass
    return _VOZES_EDGE


def voz_edge(i: Idioma, genero: str = "feminina") -> str:
    """Voz neural do Edge para o idioma. Fora dos 18 principais, procura na lista do Edge."""
    if i.edge_f:
        return i.edge_m if genero.startswith("m") and i.edge_m else i.edge_f
    quer = "Male" if genero.startswith("m") else "Female"
    prefixo = i.codigo.lower()
    candidatas = [v for v in _lista_edge()
                  if str(v.get("Locale", "")).lower().startswith(prefixo)]
    candidatas.sort(key=lambda v: (v.get("Gender") != quer, "Multilingual" in v["ShortName"]))
    return candidatas[0]["ShortName"] if candidatas else ""

# Nomes em inglês que servidores compatíveis com a OpenAI devolvem ("portuguese") → código
WHISPER_INGLES = {
    "english": "en", "chinese": "zh", "german": "de", "spanish": "es", "russian": "ru",
    "korean": "ko", "french": "fr", "japanese": "ja", "portuguese": "pt", "turkish": "tr",
    "polish": "pl", "catalan": "ca", "dutch": "nl", "arabic": "ar", "swedish": "sv",
    "italian": "it", "indonesian": "id", "hindi": "hi", "finnish": "fi", "vietnamese": "vi",
    "hebrew": "he", "ukrainian": "uk", "greek": "el", "malay": "ms", "czech": "cs",
    "romanian": "ro", "danish": "da", "hungarian": "hu", "tamil": "ta", "norwegian": "no",
    "thai": "th", "urdu": "ur", "croatian": "hr", "bulgarian": "bg", "lithuanian": "lt",
    "latin": "la", "maori": "mi", "malayalam": "ml", "welsh": "cy", "slovak": "sk",
    "telugu": "te", "persian": "fa", "latvian": "lv", "bengali": "bn", "serbian": "sr",
    "azerbaijani": "az", "slovenian": "sl", "kannada": "kn", "estonian": "et",
    "macedonian": "mk", "breton": "br", "basque": "eu", "icelandic": "is", "armenian": "hy",
    "nepali": "ne", "mongolian": "mn", "bosnian": "bs", "kazakh": "kk", "albanian": "sq",
    "swahili": "sw", "galician": "gl", "marathi": "mr", "punjabi": "pa", "sinhala": "si",
    "khmer": "km", "shona": "sn", "yoruba": "yo", "somali": "so", "afrikaans": "af",
    "occitan": "oc", "georgian": "ka", "belarusian": "be", "tajik": "tg", "sindhi": "sd",
    "gujarati": "gu", "amharic": "am", "yiddish": "yi", "lao": "lo", "uzbek": "uz",
    "faroese": "fo", "haitian creole": "ht", "pashto": "ps", "turkmen": "tk", "nynorsk": "nn",
    "maltese": "mt", "sanskrit": "sa", "luxembourgish": "lb", "myanmar": "my", "tibetan": "bo",
    "tagalog": "tl", "malagasy": "mg", "assamese": "as", "tatar": "tt", "hawaiian": "haw",
    "lingala": "ln", "hausa": "ha", "bashkir": "ba", "javanese": "jw", "sundanese": "su",
    "cantonese": "yue",
}


def codigo_detectado(lingua: str) -> str:
    """Código do Whisper a partir do que o reconhecimento devolveu: "pt", "pt-BR" ou
    "portuguese". Vazio se não reconhecer."""
    t = (lingua or "").strip().lower()
    if not t:
        return ""
    if t in WHISPER_INGLES:
        return WHISPER_INGLES[t]
    try:
        return idioma(t).whisper or ""
    except ValueError:
        return ""
