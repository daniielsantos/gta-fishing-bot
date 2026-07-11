# Stash por inventário (carro ao lado)

Abordagem nova — **muito melhor** que caminhar até o carro.

## Setup no jogo

1. Estacione o carro **ao lado** do ponto de pesca (como na screenshot)
2. Pescar normalmente
3. Quando inventário enche → **`I`** abre inventário + porta-malas juntos
4. Bot arrasta peixes do bolso → slot da **mesma espécie** no trunk

## Fluxo do bot

```
Pescar → peso >= 98% → pausa pesca
    → tecla I (abre UI)
    → para cada peixe nos Pockets:
         identifica espécie (Trout, Perch, Carp, Salmon...)
         acha coluna correspondente no TRUNK ALFA
         drag_mouse(bolso → trunk)
    → ESC fecha
    → volta a pescar
```

## O que precisa calibrar (2560×1440)

Da sua screenshot, a UI tem estrutura fixa:

| Área | O que calibrar |
|------|----------------|
| **Pockets** (esquerda) | Centro de cada slot 1–6 da fileira |
| **Trunk row 1** (direita) | Centro de cada slot por espécie |
| **Peso** | ROI do texto `75.6 / 80 KG` |

### Mapa de espécies (trunk linha 1)

Ordem no seu trunk:
```
Perch | Carp | Trout | Salmon | Megalodon | Sponge
```

Pockets podem ter peixes em ordem diferente — o bot precisa **ler o nome** em cada slot, não assumir posição fixa.

## Como funciona (importante)

```
Pocket slot 2: OCR le "Carp"   → arrasta para coluna Carp no trunk
Pocket slot 4: OCR le "Trout"  → arrasta para coluna Trout no trunk
Pocket slot 1: OCR le "Orange" → IGNORA (nao esta em fish_species)
Pocket slot 6: vazio           → IGNORA
```

| O que | Ordem fixa? | Como o bot sabe |
|-------|-------------|-----------------|
| **Pockets** | Nao — muda a cada pesca | **OCR** no texto (`• Trout`) embaixo de cada slot |
| **Trunk** | Sim — voce organiza por especie | Calibracao: coluna 0=Perch, 1=Carp, etc. |

A calibracao do Pocket marca só a **posicao (x,y)** de cada slot 1–6 — **nao** associa especie ao numero do slot.

## Detecção de espécie (opções)

| Método | Prós | Contras |
|--------|------|---------|
| **OCR no texto** (`• Trout`) | Funciona com UI atual | Precisa calibrar ROI por slot |
| **Template do ícone** | Robusto se ícone único | Mais trabalho inicial |
| **Mapa fixo bolso→trunk** | Só se você sempre organizar igual | Simples mas frágil |

**Recomendação:** OCR no label embaixo de cada slot do bolso + mapa de coluna do trunk por espécie.

## Arquivos a implementar

```
stash-route/
├── STASH-INVENTORY.md      ← este arquivo
├── calibrate_inventory.py  ← marcar slots com clique
├── stash_inventory.py      ← abre I, drag por espécie
└── templates/inventory/    ← recortes opcionais
```

## Config proposta (`config.json`)

```json
"stash_inventory": {
  "enabled": false,
  "open_key": "i",
  "close_key": "esc",
  "weight_max_kg": 80.0,
  "weight_trigger_ratio": 0.98,
  "fish_species": ["perch", "carp", "trout", "salmon"],
  "drag_hold_ms": 80,
  "drag_duration_ms": 250,
  "ui_open_wait_ms": 600
}
```

## Por que isso é melhor que walk_route

| Walk route | Inventário ao lado |
|------------|-------------------|
| 50s de replay frágil | Zero movimento |
| Câmera, lag, escada | UI fixa na tela |
| Difícil de ajustar | Slots = coordenadas fixas |
| G + prompt | Só tecla I |

## Passo a passo

### 1. Instalar OCR (para ler especie do peixe)

```powershell
.venv\Scripts\pip.exe install -r requirements-stash.txt
```

Instale [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) no Windows.

### 2. Calibrar slots

```powershell
# No jogo: carro ao lado, pressione I
.venv\Scripts\python.exe stash-route\calibrate_inventory.py
```

Clique no centro de cada slot (6 Pockets + 6 Trunk + ROI do peso). **S** para salvar.

### 3. Testar OCR (inventario aberto)

```powershell
.venv\Scripts\python.exe stash-route\stash_inventory.py --dry-run
```

### 4. Testar um drag

```powershell
.venv\Scripts\python.exe stash-route\stash_inventory.py --drag 1 perch
```

(pocket index 1 -> coluna perch no trunk)

### 5. Stash completo

```powershell
.venv\Scripts\python.exe stash-route\stash_inventory.py --stash
```
