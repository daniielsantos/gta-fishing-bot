# Stash Route — Pier → Carro → Voltar a Pescar

Planejamento da feature que **automatiza o deslocamento a pé** quando o inventário de peixes enche: andar até o carro fixo no pier, guardar os peixes no porta-malas e voltar ao ponto de pesca.

Este documento é o guia para desenvolvimento e testes **locais** no [gta-fishing-bot](https://github.com/daniielsantos/gta-fishing-bot). Nada aqui está implementado ainda — é o blueprint completo.

> **Aviso:** automação em servidores de RP pode violar regras do servidor e resultar em ban. Use por sua conta e risco, preferencialmente para aprendizado local.

---

## Índice

1. [Problema e objetivo](#problema-e-objetivo)
2. [Contexto no jogo](#contexto-no-jogo)
3. [Por que o minimapa não resolve](#por-que-o-minimapa-não-resolve)
4. [Estratégia escolhida](#estratégia-escolhida)
5. [Máquina de estados](#máquina-de-estados)
6. [Gravação e replay de rota](#gravação-e-replay-de-rota)
7. [Detecção visual complementar](#detecção-visual-complementar)
8. [Inventário cheio](#inventário-cheio)
9. [Stash no porta-malas](#stash-no-porta-malas)
10. [Arquitetura de arquivos](#arquitetura-de-arquivos)
11. [Configuração (`config.json`)](#configuração-configjson)
12. [Fases de implementação](#fases-de-implementação)
13. [Checklist de testes locais](#checklist-de-testes-locais)
14. [Integração com `fishing_bot.py`](#integração-com-fishing_botpy)
15. [Riscos e limitações](#riscos-e-limitações)

---

## Problema e objetivo

### Situação atual

O fishing bot controla o minigame da barra horizontal e reinicia a pesca automaticamente. O único passo **manual** restante é quando o **inventário enche**: o jogador precisa parar de pescar, ir até o carro, guardar os peixes e voltar.

### Regras de negócio

| Regra | Detalhe |
|-------|---------|
| Não dropar peixe | Dropar = perder dinheiro |
| Carro fixo no pier | SUV branco estacionado no mesmo local sempre |
| Porta-malas sem limite de peso | Tecla **G** para interagir |
| Voltar ao mesmo ponto | Grade azul de pesca no pier (Del Perro) |

### Objetivo da feature

Automatizar o ciclo:

```
Pescar → inventário cheio → andar até o carro → guardar peixes → andar de volta → pescar
```

Sem depender de GPS, waypoint no mapa ou blip do carro.

---

## Contexto no jogo

### Local

- **Área:** Del Perro Pier / Pacific Ocean / Red Desert Ave
- **Ponto de pesca:** grade azul no pier (referência visual fixa)
- **Carro:** SUV branco no mesmo pier, porta-malas aberto quando próximo
- **Interação:** prompt **G** para abrir inventário / guardar no porta-malas

### Resolução de referência

- **2560×1440** (2K), borderless ou janela
- Mesma configuração do fishing bot (`config.json` → `resolution`)

### Caminho típico (ida)

```
Ponto de pesca (grade azul)
    → andar pelo pier
    → subir escada
    → continuar até o carro
    → prompt G + UI de inventário
```

A volta é o **mesmo caminho invertido** (replay da rota com A↔D trocados).

---

## Por que o minimapa não resolve

Várias abordagens foram descartadas após análise do cenário real:

| Abordagem | Por que falha |
|-----------|---------------|
| **Waypoint único no minimapa** | Escada não aparece no mapa 2D; o personagem sobe/descende fora do plano do minimapa |
| **Pixel fixo no minimapa** | O minimapa **gira** com o personagem/câmera — coordenadas fixas não correspondem ao mesmo lugar no mundo |
| **Blip do carro** | O carro **não aparece no minimapa** neste servidor/cenário |
| **Navegação só por visão** | Pier tem poucos landmarks únicos; escada e curvas exigem timing preciso |

### Conclusão

A navegação principal deve ser **replay de rota gravada** (teclas + duração), com **visão** apenas para confirmar chegada (grade, carro, prompt G) e detectar inventário cheio.

---

## Estratégia escolhida

### Camada 1 — Macro de movimento (principal)

Gravar uma sequência de segmentos:

```json
{
  "name": "pier_to_car",
  "segments": [
    { "keys": ["w"], "duration_ms": 3200 },
    { "keys": ["w", "d"], "duration_ms": 800 },
    { "keys": ["w"], "duration_ms": 1500, "note": "escada — ajustar na gravação" },
    { "keys": ["w", "a"], "duration_ms": 600 },
    { "keys": ["w"], "duration_ms": 4100 }
  ]
}
```

- Cada segmento = uma ou mais teclas pressionadas por **N milissegundos**
- A escada é tratada como segmento **W puro** com duração calibrada manualmente
- O replay usa `SendInput` (mesmo `keyboard_input.py` do fishing bot)

### Camada 2 — Visão (confirmação e correção leve)

| Alvo | Uso |
|------|-----|
| Grade azul de pesca | Confirmar que voltou ao ponto certo |
| SUV branco / porta-malas | Confirmar proximidade do carro |
| Prompt **G** na tela | Disparar interação de stash |
| UI de inventário | Arrastar peixes para o porta-malas (fase posterior) |

### Camada 3 — OCR / leitura de peso

Detectar **inventário cheio** antes de sair do modo pesca (texto de peso na UI do servidor).

---

## Máquina de estados

```
                    inventário cheio
    ┌─────────┐ ──────────────────► ┌──────────────┐
    │ FISHING │                       │ WALK_TO_CAR  │
    └─────────┘ ◄────────────────── └──────┬───────┘
          ▲                                │ rota ida completa
          │                                │ + visão: carro / G
          │                                ▼
          │                         ┌──────────────┐
          │                         │  STASH_FISH  │
          │                         └──────┬───────┘
          │                                │ inventário vazio
          │                                ▼
          │                         ┌──────────────┐
          └──────────────────────── │ WALK_TO_SPOT │
             rota volta + grade     └──────────────┘
```

### Transições

| De | Para | Condição |
|----|------|----------|
| `FISHING` | `WALK_TO_CAR` | Peso do inventário ≥ limite (ou UI “cheio”) |
| `WALK_TO_CAR` | `STASH_FISH` | Rota `pier_to_car` terminou **e** prompt G ou carro detectado |
| `STASH_FISH` | `WALK_TO_SPOT` | Peixes transferidos; peso abaixo do limite |
| `WALK_TO_SPOT` | `FISHING` | Rota `car_to_pier` terminou **e** grade azul visível |
| Qualquer | `FISHING` (pausa) | Usuário pressiona F6 ou erro irrecuperável |

### Estados de erro (fase 2+)

- Timeout na rota (segmento demorou além de `max_duration_ms * factor`)
- Personagem preso (posição visual não muda por X segundos)
- Prompt G não aparece após rota completa → retry ou alerta no log

---

## Gravação e replay de rota

### Formato do arquivo de rota

Salvar em `stash-route/routes/pier_to_car.json`:

```json
{
  "version": 1,
  "resolution": { "width": 2560, "height": 1440 },
  "name": "pier_to_car",
  "description": "Grade azul → escada → SUV branco no pier",
  "segments": [
    { "keys": ["w"], "duration_ms": 3000 },
    { "keys": ["w", "d"], "duration_ms": 750 }
  ],
  "metadata": {
    "recorded_at": "2026-07-09T22:00:00",
    "notes": "Recalibrar escada se mudar personagem ou lag"
  }
}
```

### `record_route.py` (a implementar)

**Fluxo:**

1. Jogo em foco, personagem no ponto inicial (grade azul)
2. Script escuta teclas **W A S D** via `pynput` (só grava, não envia)
3. Cada combinação ativa vira um segmento; ao soltar todas as teclas ou trocar combinação, fecha segmento com `duration_ms`
4. **F10** = salvar rota em JSON
5. **F11** = descartar último segmento
6. **ESC** = sair sem salvar

**Dicas de gravação:**

- Grave em **passos curtos** (1–3 s) — mais fácil de ajustar depois
- A escada: um segmento só `W` enquanto sobe; teste várias durações
- Não use mouse durante a gravação
- Mantenha a câmera na mesma posição que usará no bot

### `walk_route.py` (a implementar)

**Fluxo:**

1. Carrega JSON da rota
2. Para cada segmento: `hold_keys(keys, duration_ms)` via `keyboard_input.py`
3. Opcional: pequena pausa entre segmentos (`gap_ms`, ex. 50 ms)
4. Log de cada segmento no console e em `stash-route.log`

### Rota reversa (`car_to_pier`)

Gerar automaticamente a partir de `pier_to_car`:

| Tecla na ida | Tecla na volta |
|--------------|----------------|
| `a` | `d` |
| `d` | `a` |
| `w` | `w` |
| `s` | `s` |

- Inverter a **ordem** dos segmentos
- Manter as mesmas `duration_ms` (ajuste fino pode ser necessário na escada)

```python
# Pseudocódigo
def reverse_route(route: dict) -> dict:
    swap = {"a": "d", "d": "a", "w": "w", "s": "s"}
    reversed_segments = []
    for seg in reversed(route["segments"]):
        reversed_segments.append({
            "keys": [swap.get(k, k) for k in seg["keys"]],
            "duration_ms": seg["duration_ms"],
        })
    return {**route, "name": "car_to_pier", "segments": reversed_segments}
```

---

## Detecção visual complementar

A visão **não guia** o caminho inteiro — só valida marcos.

### Templates (`stash-route/templates/`)

| Arquivo | O que detectar |
|---------|----------------|
| `fishing_grid.png` | Recorte da grade azul no pier |
| `car_trunk.png` | SUV branco / porta-malas aberto |
| `prompt_g.png` | Ícone ou texto do prompt G |
| `inventory_full.png` | (opcional) ícone de inventário cheio |

### ROIs sugeridas (2560×1440 — calibrar com `calibrate_stash.py`)

```json
{
  "stash_vision": {
    "fishing_grid_roi": { "left": 0, "top": 0, "width": 400, "height": 300 },
    "interaction_prompt_roi": { "left": 1100, "top": 700, "width": 360, "height": 120 },
    "inventory_weight_roi": { "left": 0, "top": 0, "width": 280, "height": 80 }
  }
}
```

> Os valores acima são **placeholder**. Calibre capturando screenshots no seu setup.

### `stash_vision.py` (a implementar)

Funções mínimas:

- `see_fishing_grid(frame) -> bool` — `matchTemplate` ou cor HSV da grade
- `see_car_nearby(frame) -> bool`
- `see_prompt_g(frame) -> bool`
- `read_inventory_weight(frame) -> float | None` — OCR (pytesseract ou easyocr)

---

## Inventário cheio

### Opções de detecção

| Método | Prós | Contras |
|--------|------|---------|
| **OCR no texto de peso** | Preciso se a UI for estável | Precisa calibrar ROI e fonte |
| **Template “cheio”** | Simples | Pode falhar com skins de UI |
| **Contador de minigames × peso médio** | Sem visão extra | Impreciso; peixes têm pesos diferentes |

**Recomendação:** OCR na ROI do peso (`45.2 / 50.0 kg` ou similar no Grand RP).

### Lógica

```python
if weight_current >= weight_max * 0.98:  # margem 2%
    transition_to(WALK_TO_CAR)
```

Enquanto `WALK_TO_CAR` / `STASH_FISH` / `WALK_TO_SPOT`, o fishing bot deve estar **pausado** (não alternar varas nem iniciar minigame).

---

## Stash no porta-malas

### Sequência manual observada

1. Chegar perto do carro (porta-malas aberto)
2. Aparece prompt **G**
3. Pressionar **G** → abre UI de inventário + porta-malas
4. Transferir peixes (drag ou clique — depende da UI do servidor)
5. Fechar UI (ESC ou botão)
6. Inventário com espaço livre

### `stash_vehicle.py` (a implementar)

**Fase 1 — semi-manual:**

- Bot chega com `walk_route`
- Detecta prompt G
- Pressiona G
- **Pausa** e pede confirmação no log (“complete o stash manualmente”) — útil para testes

**Fase 2 — automático:**

- Após G: detectar slots de peixe na UI
- Clicar/arrastar para área do porta-malas (coordenadas fixas ou detecção de ícone)
- Repetir até peso < limite
- ESC para fechar

### Tecla G no `keyboard_input.py`

Hoje o mapa VK só tem `0-9`, `e`, `w`, `a`, `s`, `d`. Será necessário adicionar:

```python
"g": 0x47,
```

---

## Arquitetura de arquivos

Estrutura proposta dentro do repositório:

```
gta-fishing-bot/
├── fishing_bot.py              # integração final (estado STASH_*)
├── keyboard_input.py           # estender com g, shift, etc.
├── config.json                 # seção stash_route
└── stash-route/
    ├── README.md               # este arquivo
    ├── record_route.py         # gravar rota (WASD + tempo)
    ├── walk_route.py           # replay ida/volta
    ├── route_utils.py          # reverse_route, load/save JSON
    ├── stash_vision.py         # templates, OCR peso
    ├── stash_vehicle.py        # sequência G + transferência
    ├── calibrate_stash.py      # calibrar ROIs e templates
    ├── routes/
    │   ├── pier_to_car.json    # rota gravada (não versionar se for específica)
    │   └── car_to_pier.json    # gerada ou gravada separadamente
    ├── templates/
    │   ├── fishing_grid.png
    │   ├── car_trunk.png
    │   └── prompt_g.png
    └── stash-route.log
```

### Dependências extras (fase OCR)

```
# requirements-stash.txt (ou adicionar ao requirements.txt)
pytesseract   # requer Tesseract instalado no Windows
# ou
easyocr
```

---

## Configuração (`config.json`)

Seção nova proposta:

```json
{
  "stash_route": {
    "enabled": false,
    "weight_max_kg": 50.0,
    "weight_trigger_ratio": 0.98,
    "route_to_car": "stash-route/routes/pier_to_car.json",
    "route_to_spot": "stash-route/routes/car_to_pier.json",
    "segment_gap_ms": 50,
    "route_timeout_factor": 1.5,
    "vision": {
      "fishing_grid_threshold": 0.75,
      "prompt_g_threshold": 0.80,
      "car_threshold": 0.70
    },
    "stash": {
      "auto_transfer": false,
      "g_key": "g",
      "wait_for_ui_ms": 800
    }
  }
}
```

| Campo | Descrição |
|-------|-----------|
| `enabled` | `false` até todas as fases estarem testadas |
| `weight_max_kg` | Limite do servidor (ajustar ao Grand RP) |
| `route_to_car` | JSON da ida |
| `segment_gap_ms` | Pausa entre segmentos no replay |
| `auto_transfer` | `false` na fase 1 (stash manual após G) |

---

## Fases de implementação

### Fase 0 — Preparação (você, local)

- [ ] Screenshots do pier, grade, carro, prompt G, UI de peso
- [ ] Criar pasta `stash-route/templates/` com recortes
- [ ] Anotar peso máximo do inventário no servidor

### Fase 1 — Gravação e replay seco

- [ ] Implementar `record_route.py`
- [ ] Gravar `pier_to_car.json` (várias tentativas; refine a escada)
- [ ] Implementar `walk_route.py` + `route_utils.py`
- [ ] Testar ida **sem** fishing bot — personagem chega no carro?
- [ ] Gerar e testar `car_to_pier` (volta)

**Critério de sucesso:** 5 replays seguidos com chegada consistente no carro e na grade.

### Fase 2 — Visão mínima

- [ ] `calibrate_stash.py` para ROIs
- [ ] `stash_vision.py`: `see_prompt_g`, `see_fishing_grid`
- [ ] No fim da rota, **confirmar** marco visual antes de mudar de estado

### Fase 3 — Inventário cheio

- [ ] OCR ou template de peso
- [ ] Hook no loop do `fishing_bot.py`: se cheio → pausar pesca → `WALK_TO_CAR`

### Fase 4 — Stash

- [ ] Adicionar tecla G em `keyboard_input.py`
- [ ] `stash_vehicle.py` fase 1: G + pausa manual
- [ ] Fase 2: transferência automática na UI

### Fase 5 — Integração completa

- [ ] Máquina de estados no `fishing_bot.py`
- [ ] `stash_route.enabled: true`
- [ ] Sessão longa: pescar até encher → stash → voltar → pescar (loop)

---

## Checklist de testes locais

### Replay de rota

- [ ] Ida: personagem para em frente ao carro (± 1 m)
- [ ] Volta: personagem para na grade azul
- [ ] Escada: não cai / não fica preso no corrimão
- [ ] Com lag leve (servidor lotado): ainda funciona? (ajuste `duration_ms`)

### Visão

- [ ] `see_fishing_grid` = true só no ponto de pesca
- [ ] `see_prompt_g` = true só perto do carro
- [ ] OCR de peso bate com o valor na tela

### Integração

- [ ] F6 ainda liga/desliga tudo
- [ ] Bot não inicia minigame durante `WALK_*`
- [ ] Após stash, reinicia pesca com `start_keys` 1/2/3
- [ ] Log em `stash-route.log` + `fishing_bot.log.txt` é legível

### Regressão fishing

- [ ] Minigame da barra continua “perfeito” após merge
- [ ] Anti-AFK não dispara no meio da caminhada

---

## Integração com `fishing_bot.py`

### Onde encaixar

1. **No loop principal:** antes de tentar novo minigame, checar peso se `stash_route.enabled`
2. **Novo módulo** `stash_route_runner.py` (opcional) orquestra estados e chama `walk_route` / `stash_vehicle`
3. **Pausa do controller de mouse** enquanto estado ≠ `FISHING`

### Pseudocódigo

```python
class BotPhase(Enum):
    FISHING = "fishing"
    WALK_TO_CAR = "walk_to_car"
    STASH_FISH = "stash_fish"
    WALK_TO_SPOT = "walk_to_spot"

def main_loop():
    phase = BotPhase.FISHING
    while running:
        if phase == BotPhase.FISHING:
            if stash_enabled and inventory_full():
                phase = BotPhase.WALK_TO_CAR
                walk_route("pier_to_car")
            else:
                run_fishing_minigame()
        elif phase == BotPhase.WALK_TO_CAR:
            if walk_finished and see_prompt_g():
                phase = BotPhase.STASH_FISH
                stash_vehicle()
        elif phase == BotPhase.STASH_FISH:
            if inventory_has_space():
                phase = BotPhase.WALK_TO_SPOT
                walk_route("car_to_pier")
        elif phase == BotPhase.WALK_TO_SPOT:
            if walk_finished and see_fishing_grid():
                phase = BotPhase.FISHING
```

### Hotkeys

| Tecla | Ação sugerida |
|-------|----------------|
| **F6** | Liga/desliga (inclui stash route quando integrado) |
| **F7** | (opcional) Só testar replay da rota ida |
| **F8** | (opcional) Só testar replay da volta |
| **F9** | Encerra |

---

## Riscos e limitações

| Risco | Mitigação |
|-------|-----------|
| Lag do servidor altera distância percorrida | Segmentos curtos; fator `route_timeout_factor`; recalibrar `duration_ms` |
| Outro jogador bloqueia o caminho | Detecção de “preso”; timeout; log + pausa |
| UI do servidor muda | Templates e ROIs versionados; `calibrate_stash.py` |
| Câmera diferente da gravação | Gravar e rodar com mesma câmera (terceira pessoa, mesmo zoom) |
| Ban por automação | Feature desligada por padrão; usar com consciência das regras do servidor |

### O que **não** fazer nesta feature

- Não usar minimapa / GPS para este trecho
- Não depender de blip do carro
- Não dropar peixe como fallback
- Não misturar com gta-driving-bot (projeto separado — carro autônomo é outro escopo)

---

## Referências no repositório

| Recurso | Caminho |
|---------|---------|
| Envio de teclas | `keyboard_input.py` |
| Config global | `config.json` |
| Loop principal | `fishing_bot.py` |
| Driving bot (outro projeto) | `gta-driving-bot-planning/` |

---

## Ordem sugerida para começar hoje

1. Ler este README inteiro
2. Tirar screenshots e preencher `templates/`
3. Implementar `record_route.py` e gravar `pier_to_car.json`
4. Implementar `walk_route.py` e testar ida/volta **isoladamente**
5. Só depois conectar ao `fishing_bot.py`

Boa pesca e bons testes.
