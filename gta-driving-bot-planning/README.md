# GTA Driving Bot

Bot autônomo em Python para **GTA V / FiveM**: seguir rota no minimapa, parar em checkpoints e evitar colisões básicas.

> Projeto separado do [gta-fishing-bot](https://github.com/daniielsantos/gta-fishing-bot).  
> Este repositório começa como **planejamento e documentação**; o código será implementado em fases.

> **Aviso:** automação em servidores de RP pode violar regras do servidor e resultar em ban. Use por sua conta e risco, preferencialmente para aprendizado local.

---

## Visão geral

O objetivo não é um “Tesla FSD” no GTA, e sim um bot **útil e iterável**:

1. Seguir a **linha do GPS** no minimapa (A → B)
2. **Parar** em checkpoints definidos
3. **Não bater** na medida do possível (freio + correção de faixa)
4. Evoluir depois para manobras mais complexas (estacionar, ré, reboque…)

### Por que não só minimapa?

Seguir apenas a linha roxa/laranja do GPS **não garante** que o carro está na pista correta. A rota pode mandar virar à esquerda enquanto à esquerda há calçada, muro ou contramão.

Por isso o design é **híbrido** desde o início:

| Camada | Função |
|--------|--------|
| **Minimapa** | Navegação macro — para onde ir, curvas, checkpoints |
| **Visão da pista** | Navegação micro — asfalto válido, centro da faixa |
| **Obstáculos** | Frear / desviar leve quando algo bloqueia à frente |
| **Fusão** | Combina GPS + faixa + obstáculo na decisão final |

```
┌─────────────────────────────────────────┐
│  CAMADA 1 — Minimapa (onde ir)          │
│  • posição e ângulo da seta do jogador  │
│  • linha roxa/laranja do GPS            │
│  • distância até checkpoint             │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│  CAMADA 2 — Pista (onde posso ir)       │
│  • seta sobre pixel de "rua" no mapa?   │
│  • asfalto à frente na câmera           │
│  • centro da faixa (bordas / cor)       │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│  CAMADA 3 — Obstáculos                  │
│  • área livre à frente encolhe? → frear │
│  • (futuro) detecção de objetos (YOLO)  │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│  FUSÃO — decisão (W/A/S/D)              │
│  volante = w_gps·erro_gps + w_faixa·erro_faixa │
│  velocidade = curva + obstáculo + checkpoint   │
└─────────────────────────────────────────┘
```

---

## Stack técnica (planejada)

Reaproveita conceitos do fishing bot:

| Componente | Tecnologia |
|------------|------------|
| Captura de tela | `mss` |
| Visão | `OpenCV` (cor, contorno, template) |
| Controle | `SendInput` (W/A/S/D, freio, Space) |
| Hotkeys / loop | `pynput` |
| Config | `config.json` + calibração visual |
| (futuro) Objetos | YOLO / Ultralytics |

**Requisitos iniciais:**

- Windows (SendInput)
- Python 3.10+
- GTA/FiveM em **borderless** ou **janela**
- Resolução de referência: **2560×1440** (recalibrável)
- Jogo em **foco** (janela ativa)

---

## Fases de desenvolvimento

### Fase 0 — Fundação (atual)

- [x] Repositório e documentação de planejamento
- [ ] Estrutura de pastas e `config.json` base
- [ ] `requirements.txt`
- [ ] Calibração da ROI do minimapa

**Entregável:** projeto clonável com README e calibração do minimapa funcionando.

---

### Fase 1 — Navegação no minimapa

**Objetivo:** carro segue a linha do GPS em estrada reta e curvas suaves.

| Tarefa | Detalhe |
|--------|---------|
| ROI do minimapa | Recorte fixo calibrado (canto inferior esquerdo) |
| Detectar seta do jogador | Posição (x, y) e ângulo no minimapa |
| Detectar linha do GPS | Cor roxa/laranja, polyline ou ponto-alvo à frente |
| Controlador PID | Erro angular → A/D (pulsos curtos); distância → W/S |
| Estados | `IDLE`, `NAVIGATING`, `STOPPED` |

**Entregável:** bot segue rota marcada no GPS por 30–60 s sem sair da estrada em trecho simples.

**Limitação conhecida:** pode ir para calçada se só usar minimapa.

---

### Fase 2 — Noção de posição na pista

**Objetivo:** bot sabe se está na **rua** e não só na linha do GPS.

| Tarefa | Detalhe |
|--------|---------|
| Rua no minimapa | Seta deve ficar sobre pixels “cinza” (via), não verde/calçada |
| Visão frontal | ROI na frente do carro — detectar asfalto vs não-asfalto |
| Fusão | `volante = 0.6·erro_gps + 0.4·erro_faixa` (pesos ajustáveis) |
| Correção | Se seta saiu da via no mapa → empurrar de volta |

**Entregável:** menos casos de “seguiu GPS e foi parar na calçada”.

---

### Fase 3 — Checkpoints

**Objetivo:** parar automaticamente em pontos da rota.

| Abordagem | Descrição |
|-----------|-----------|
| **Waypoints no minimapa** | Lista de (x%, y%) no mapa; parar quando distância < limiar |
| **Blip de missão** | Template do ícone no minimapa |
| **HUD (opcional)** | OCR da distância (“150m” → “0m”) |

**Estados adicionais:** `APPROACHING_CHECKPOINT` → `STOPPING` → `WAIT_AT_CHECKPOINT` → `NAVIGATING`

**Entregável:** rota com 3 checkpoints; para em cada um e continua.

---

### Fase 4 — Anti-colisão básica

**Objetivo:** frear antes de bater; não dirigir perfeito em cidade lotada.

| Nível | Comportamento |
|-------|----------------|
| Básico | Centro da tela “fecha” (menos pixels de estrada longe) → frear |
| Médio | Obstáculo deslocado no centro → frear + leve A/D |
| Avançado (futuro) | YOLO para carros / pedestres |

**Entregável:** reduz batidas em trânsito leve e obstáculos estáticos.

---

### Fase 5 — Recuperação de erros

**Objetivo:** sair de atoleiro sem intervenção manual.

- Saiu da rota → realinhar no minimapa
- Parou em muro/obstáculo → ré curta + correção de ângulo
- Perdeu linha GPS → buscar último ponto conhecido da rota

**Entregável:** bot se recupera de erros comuns sem reset.

---

### Fase 6+ — Expansões (fora do MVP)

| Feature | Dificuldade | Notas |
|---------|-------------|-------|
| Estacionar em vaga | Média | Ré + alinhamento |
| Cidade densa 24/7 | Alta | Muito tuning |
| Noite / chuva | Alta | Recalibrar HSV |
| Engate de reboque | Muito alta | Câmera traseira + FSM de ré |
| ML / imitation learning | Alta | Dataset + GPU |

---

## Estrutura de pastas (planejada)

```
gta-driving-bot/
├── README.md                 # este arquivo
├── PLANNING.md               # notas técnicas detalhadas (opcional)
├── requirements.txt
├── config.json               # ROIs, cores, waypoints, PID
├── calibrate_minimap.py      # calibra ROI e cores do minimapa
├── calibrate_road.py         # calibra ROI da visão frontal (fase 2)
├── drive_bot.py              # loop principal + hotkeys
├── minimap/
│   ├── detector.py           # seta, linha GPS, pixels de rua
│   └── navigator.py          # erro angular, distância, waypoints
├── vision/
│   ├── lane.py               # asfalto / centro da faixa
│   └── obstacle.py           # freio por área livre
├── control/
│   ├── vehicle.py            # W/A/S/D via SendInput
│   └── fusion.py             # combina camadas
├── debug/
│   └── recorder.py           # grava frames (como no fishing bot)
└── captures/                 # screenshots de debug (gitignored)
```

---

## Controle do veículo

| Tecla | Função |
|-------|--------|
| W | Acelerar |
| S | Ré / freio motor |
| A / D | Volante (pulsos curtos = mais preciso que segurar fixo) |
| Space | Freio de mão (parar no checkpoint) |
| (futuro) E | Interações (portas, missões) |

**Hotkeys do bot (proposta):**

| Tecla | Ação |
|-------|------|
| F6 | Liga / desliga |
| F7 | Pausa navegação (mantém captura) |
| F9 | Encerra |

---

## Configuração (`config.json` — rascunho)

```json
{
  "resolution": { "width": 2560, "height": 1440 },
  "minimap": {
    "roi": { "left": 20, "top": 900, "width": 280, "height": 280 },
    "gps_color_hsv": { "lower": [140, 100, 100], "upper": [170, 255, 255] },
    "road_gray_range": [80, 140],
    "player_arrow_template": "assets/arrow.png"
  },
  "road_view": {
    "roi": { "left": 800, "top": 600, "width": 960, "height": 400 },
    "lane_center_weight": 0.4
  },
  "control": {
    "gps_weight": 0.6,
    "steer_deadband_deg": 3,
    "max_steer_pulse_ms": 80,
    "cruise_throttle": true,
    "brake_distance_threshold": 0.35
  },
  "waypoints": [
    { "name": "checkpoint_1", "minimap_x": 0.45, "minimap_y": 0.62, "stop_radius_px": 18 },
    { "name": "checkpoint_2", "minimap_x": 0.51, "minimap_y": 0.55, "stop_radius_px": 18 }
  ],
  "hotkeys": { "toggle": "f6", "pause": "f7", "quit": "f9" }
}
```

---

## Expectativas realistas

| Cenário | MVP (fases 1–4) | Futuro |
|---------|-----------------|--------|
| Estrada longa com GPS | Bom | Muito bom |
| Checkpoints em sequência | Bom | Muito bom |
| Trânsito leve | Razoável | Bom |
| Cidade lotada | Fraco | Médio |
| Noite / chuva | Fraco | Médio com retuning |
| Contramão | Raro (GPS costuma acertar sentido) | Heurísticas extras |
| Engate de reboque | Fora do escopo | Fase 6+ |

---

## Relação com o fishing bot

O [gta-fishing-bot](https://github.com/daniielsantos/gta-fishing-bot) validou o stack:

- captura com `mss`
- detecção com OpenCV
- controle com `SendInput`
- calibração visual + `config.json`
- debug overlay e gravação de frames

Este projeto **reutiliza o mesmo padrão**, mudando o domínio (minimapa + pista em vez de anzol + zona azul).

---

## Próximos passos (implementação)

1. Criar `requirements.txt` e `config.json` mínimo
2. `calibrate_minimap.py` — ROI + preview ao vivo
3. Detectar seta e linha GPS no minimapa
4. PID simples (W + A/D) em estrada vazia
5. Fase 2: fusão com “seta na rua”
6. Fase 3: waypoints e parada
7. Fase 4: freio por obstáculo à frente

---

## Licença

Projeto educacional. Sem garantias. Use com responsabilidade.

---

## Referências internas

- Repositório irmão: [daniielsantos/gta-fishing-bot](https://github.com/daniielsantos/gta-fishing-bot)
- Discussão de arquitetura: minimapa híbrido + checkpoints + anti-colisão (planejamento inicial, jul/2026)
