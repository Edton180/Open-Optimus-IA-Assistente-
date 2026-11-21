# Problemas e dúvidas

Comece sempre por `optimus doutor`: ele mostra o que está funcionando e o que falta.

| Sintoma | Causa provável | Solução |
|---|---|---|
| "Não consegui falar com o Ollama" | Ollama fechado | Abra o Ollama (Windows: menu Iniciar; Linux: `ollama serve` ou `sudo systemctl start ollama`) |
| "model not found" | Modelo não baixado | `optimus instalar-modelo` |
| Respostas muito lentas | Modelo grande para o PC | `optimus config recursos.uso economico` ou um modelo menor (`optimus instalar-modelo qwen3.5:2b`) |
| "O modelo ficou 120 s sem responder e eu parei" | O modelo travou, ou é grande demais para o PC | Tente de novo; use um modelo menor; em PC muito fraco aumente a espera: `optimus config motor.tempo_sem_resposta 300` |
| "Perdi a conexão com o Optimus durante a resposta" | O Optimus foi fechado ou reiniciado no meio | Abra de novo e reenvie o pedido; a tela não fica mais presa em "Pensando…" |
| PC travando | Pouca RAM livre | Feche programas, use o modo econômico, baixe `recursos.ram_minima_gb` para trocar antes para o modelo rápido |
| O modelo não usa as ferramentas | Modelo muito pequeno ou sem suporte | Use `qwen3.5` ou `qwen3`, que lidam bem com ferramentas; em PCs mínimos, prefira pedidos diretos |
| Não fala nada | Sem vozes ou sem áudio | `optimus vozes`; `optimus vozes --baixar`; confira o alto-falante |
| Microfone não funciona | Permissão ou PortAudio | Veja [voz.md](voz.md#problemas-com-microfone) |
| Pesquisa na internet falha | Sem internet ou buscador bloqueado | Tente de novo; confira firewall/proxy |
| "Ação bloqueada pelo Optimus" | Comando destrutivo demais | De propósito. Faça manualmente se tiver certeza |
| Celular não abre a interface | Interface só no PC | `optimus config web.senha ...` e `optimus gui --rede`; libere a porta 8765 no firewall |
| Casa: "Configure [casa] url e token" | Home Assistant não configurado | Veja [casa.md](casa.md) |
| Kasa: "Não consegui falar com o aparelho" | IP errado, outra rede, ou Tapo/firmware novo | Rode "procure tomadas Kasa" de novo; veja os limites em [casa.md](casa.md#tomadas-e-lâmpadas-tp-link-kasa-sem-home-assistant) |
| Webcam: "instale o OpenCV ... ou o ffmpeg" | Falta quem leia a câmera | `pip install opencv-python` ou instale o ffmpeg |
| Webcam: "outro programa está usando?" | Zoom, Teams, OBS ou o navegador com a câmera aberta | Feche o outro programa (ou desligue os ✋ Gestos) e tente de novo |
| Gestos: "não consegui baixar o reconhecedor" | Sem internet na primeira vez | Conecte e aperte ✋ Gestos de novo; depois o navegador guarda os arquivos |
| Gestos: "libere a câmera para este site" | Permissão negada | Clique no cadeado ao lado do endereço > Câmera > Permitir |
| Mac: volume/mídia não respondem | Permissão de Automação | Ajustes do Sistema > Privacidade e Segurança > Automação: libere o Terminal |
| Windows: `optimus` não é reconhecido | PATH antigo | Abra um terminal novo ou use o atalho da área de trabalho |

## Apagar tudo e começar do zero

Feche o Optimus e apague a pasta de dados (`~/.config/optimus` ou `%APPDATA%\Optimus`). As conversas,
memórias e configurações serão perdidas.
