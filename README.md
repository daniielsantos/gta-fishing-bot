# GTA Fishing Bot

Bot em Python para o minigame de pesca com barra horizontal (anzol branco + zona azul) no **GTA V / FiveM**.

Calibrado por padrão para **2560×1440 (2K)**. Usa captura de tela, visão computacional (OpenCV) e `SendInput` para controlar o mouse.

> **Aviso:** automação em servidores de RP pode violar regras do servidor e resultar em ban. Use por sua conta e risco, preferencialmente para aprendizado local.

## Funcionalidades

- Detecção do **anzol** e da **zona azul** em tempo real
- Controle automático do mouse (segurar = zona vai para a direita, soltar = esquerda)
- **Centro de massa** da zona (ignora setas `<-` / `->` nas pontas) para tracking mais preciso
- Automação completa: alterna varas (`1` / `2` / `3`), reinicia pesca e aplica **anti-AFK**
- Calibração visual interativa (`calibrate.py`)
- **Debug overlay** com linhas de visão (verde) e controle (ciano)
- Gravação opcional de frames de debug em `debug_frames/`
- Log em `fishing_bot.log.txt`

## Requisitos

- Windows (usa `SendInput` para mouse e teclado)
- Python 3.10+
- GTA/FiveM em **borderless** ou **janela** (evite fullscreen exclusivo)
- Resolução **2560×1440** (ou recalibre a ROI para outra resolução)
- Jogo em **foco** (janela ativa) enquanto o bot roda

## Instalação

```bash
git clone https://github.com/daniielsantos/gta-fishing-bot.git
cd gta-fishing-bot
python -m venv .venv
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS:**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

> O controle de mouse via `SendInput` só funciona no Windows. Em Linux/macOS o projeto pode rodar para calibração/testes de visão, mas o bot não envia cliques ao jogo.

## Configuração do jogo

1. Modo **borderless windowed** ou **janela**
2. Resolução **2560×1440**
3. Não altere a escala da UI da barra de pesca

## Calibração (primeira vez)

Com o minigame de pesca aberto na tela:

```bash
python calibrate.py
```

| Tecla | Ação |
|-------|------|
| Setas | Move a ROI |
| W / A / X / D | Ajusta largura e altura da ROI |
| `[` `]` | Matiz (H) do azul |
| `;` `'` | Saturação (S) do azul |
| `,` `.` | Brilho (V) do azul |
| `-` `=` | Threshold do anzol branco |
| `S` | Salva em `config.json` |
| `Q` / `ESC` | Sair |

**Objetivo:** máscara laranja cobrindo a zona azul, linha branca no anzol, status `ATIVO`.

**Overlay na calibração:**

| Cor | Significado |
|-----|-------------|
| Verde | Bordas e centro da **visão** (pixels detectados) |
| Ciano | Bordas e centro usados pelo **controle** |
| Branco | Posição do anzol |
| Vermelho | Margens da barra (cuidado nas bordas) |

## Uso

```bash
python fishing_bot.py
```

| Tecla | Ação |
|-------|------|
| **F6** | Liga / desliga o bot |
| **F9** | Encerra o programa |

### Fluxo manual (só controle do minigame)

1. Comece a pescar manualmente no jogo
2. Quando o minigame aparecer, pressione **F6**
3. O bot segura/solta o botão esquerdo para manter o anzol na zona azul
4. **F6** novamente para pausar

### Fluxo automático (`automation.enabled: true`)

1. Pressione **F6** com o jogo em foco
2. O bot alterna as teclas `1`, `2`, `3` até o minigame iniciar
3. Controla o minigame automaticamente
4. Ao terminar, aguarda e reinicia a pesca
5. A cada **N** minigames, executa um giro anti-AFK (`d → s → a → w` por padrão)

## Arquitetura

```
fishing_bot.py      → loop principal, automação, hotkeys, debug
calibrate.py        → calibração visual da ROI e cores
detector.py         → detecção do anzol, zona azul e centro de massa
controller.py       → lógica de mouse (chase / track / center)
config_loader.py    → carrega config.json e instancia o detector
keyboard_input.py   → envio de teclas via SendInput
debug_recorder.py   → grava frames do overlay em debug_frames/
bot_logger.py       → log em fishing_bot.log.txt
config.json         → ROI, HSV, controle e automação
```

## Ajuste fino (`config.json`)

### Controle

```json
"control": {
  "control_deadband_px": 12,
  "capture_fps": 30,
  "zone_smoothing": 0.65,
  "expected_zone_width_px": 220,
  "debug_overlay": false,
  "debug_record_frames": false
}
```

| Parâmetro | Descrição |
|-----------|-----------|
| `control_deadband_px` | Margem em px antes de corrigir direção (menor = mais agressivo) |
| `capture_fps` | Taxa alvo do loop de captura |
| `zone_smoothing` | Suavização da posição da zona (0–1) |
| `expected_zone_width_px` | Largura esperada da zona azul |
| `debug_overlay` | Janela OpenCV com overlay de debug |
| `debug_record_frames` | Grava PNGs em `debug_frames/<timestamp>/` |

### Automação

```json
"automation": {
  "enabled": true,
  "start_keys": ["1", "2", "3"],
  "anti_afk_enabled": true,
  "anti_afk_keys": ["d", "s", "a", "w"],
  "anti_afk_every_n_minigames": 10,
  "anti_afk_repeat_count": 3
}
```

| Parâmetro | Descrição |
|-----------|-----------|
| `start_keys` | Teclas das varas no atalho (alterna até achar o minigame) |
| `anti_afk_keys` | Sequência do giro anti-AFK |
| `anti_afk_every_n_minigames` | A cada quantos minigames o anti-AFK roda |
| `anti_afk_repeat_count` | Quantas vezes repetir a sequência |
| `anti_afk_hold_ms` | Tempo que cada tecla fica pressionada |
| `anti_afk_hold_overrides` | Override de duração por tecla (ex.: `"w": 250`) |

## Debug e gravação de frames

Com `debug_overlay: true`, o bot mostra:

- Linhas **verdes** = detecção pura (pixels azuis)
- Linhas **ciano** = limites usados pelo controle
- Linha **branca** = anzol
- Texto com ação, erro, FPS e estado do minigame

Com `debug_record_frames: true`, salva frames em `debug_frames/` com nome descritivo:

```
000042_track-right_acton_e-12_a704_z716.png
```

- `track-right` = última ação
- `e-12` = erro em pixels
- `a704` = posição do anzol
- `z716` = centro da zona

## Problemas comuns

| Problema | Solução |
|----------|---------|
| Tela preta na captura | Use borderless ou janela |
| Bot não detecta minigame | Rode `calibrate.py` e ajuste ROI/HSV |
| Anzol na borda da zona | Ajuste `control_deadband_px` (tente 8–15) |
| Linhas verde/ciano desalinhadas | Recalibre; verifique `expected_zone_width_px` |
| Oscila demais | Aumente `control_deadband_px` ou `zone_smoothing` |
| Reage tarde | Diminua `control_deadband_px` ou aumente `capture_fps` |
| Bot não clica no jogo | Jogo precisa estar em foco (janela ativa) |
| Resolução diferente | Recalibre a ROI ou escale os valores (veja abaixo) |

## Escalar para outra resolução

Multiplique a ROI por:

- largura: `sua_largura / 2560`
- altura: `sua_altura / 1440`

Exemplo **1920×1080** (fator **0,75**):

```json
"roi": {
  "left": 596,
  "top": 823,
  "width": 720,
  "height": 86
}
```

Depois rode `calibrate.py` para afinar.

## Licença

Projeto educacional. Sem garantias. Use com responsabilidade.
