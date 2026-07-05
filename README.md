# GTA Fishing Bot

Bot em Python para o minigame de pesca com barra horizontal (anzol + zona azul).
Calibrado por padrao para **2560x1440 (2K)**.

> **Aviso:** automacao em servidores de RP pode violar regras do servidor e resultar em ban. Use por sua conta e risco, preferencialmente para aprendizado local.

## Instalacao

```bash
cd C:\Users\daniel\gta-fishing-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuracao do jogo

1. Use **borderless windowed** ou **janela** (evite fullscreen exclusivo).
2. Mantenha a resolucao em **2560x1440**.
3. Nao mova a UI da barra de pesca (escala/interface padrao).

## Calibracao (obrigatorio na primeira vez)

Com o minigame de pesca aberto na tela:

```bash
python calibrate.py
```

Na janela de preview:

| Tecla | Acao |
|-------|------|
| Setas | Move a ROI |
| W/A/X/D | Ajusta largura/altura da ROI |
| `[` `]` | Matiz (H) do azul |
| `;` `'` | Saturacao (S) do azul |
| `,` `.` | Brilho (V) do azul |
| `-` `=` | Threshold do anzol branco |
| `S` | Salva em `config.json` |
| `Q` / `ESC` | Sair |

Objetivo: linha laranja na zona azul, linha branca no anzol, texto `ATIVO`.

## Uso

```bash
python fishing_bot.py
```

| Tecla | Acao |
|-------|------|
| **F6** | Liga/desliga o bot |
| **F9** | Encerra |

Fluxo sugerido:

1. Entre no jogo e comece a pescar manualmente.
2. Quando o minigame aparecer, pressione **F6**.
3. O bot segura/solta o botao esquerdo para manter o anzol na zona azul.
4. Pressione **F6** novamente para pausar.

## Arquivos

| Arquivo | Funcao |
|---------|--------|
| `fishing_bot.py` | Loop principal |
| `calibrate.py` | Calibracao visual |
| `detector.py` | Deteccao do anzol e zona azul |
| `controller.py` | Controle do mouse |
| `config.json` | ROI, cores e parametros |

## Ajuste fino (`config.json`)

```json
"control": {
  "deadzone_px": 8,      // margem antes de reagir (menor = mais agressivo)
  "smoothing": 0.35,     // suavizacao da posicao (0-1)
  "min_blue_pixels": 80, // minimo de pixels azuis para considerar ativo
  "min_white_pixels": 15,
  "capture_fps": 60
}
```

## Problemas comuns

| Problema | Solucao |
|----------|---------|
| Tela preta na captura | Mude para borderless/janela |
| Bot nao detecta minigame | Rode `calibrate.py` e ajuste ROI/HSV |
| Oscila demais | Aumente `deadzone_px` |
| Reage tarde | Diminua `deadzone_px` ou aumente `capture_fps` |
| Resolucao diferente | Recalibre a ROI ou escale `config.json` |

## Escalar para outra resolucao

Multiplique a ROI por:

- largura: `sua_largura / 2560`
- altura: `sua_altura / 1440`

Exemplo 1920x1080: fator 0.75 em todos os valores de `roi`.
