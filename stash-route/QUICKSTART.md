# Stash Route — jeito fácil

## 1. Montar a rota (5–8 pedaços, não 50 segundos de uma vez)

```powershell
.venv\Scripts\python.exe stash-route\build_route.py
```

No jogo, **um trecho por vez**:

1. Segure as teclas (ex.: só `W`)
2. **SPACE** = começa a cronometrar
3. Ande esse trecho
4. **SPACE** = salva o pedaço
5. Próximo trecho (ex.: `W+D` na curva) → SPACE → SPACE
6. **F10** = salvar

**Regra:** não troque teclas no meio do segmento.

---

## 2. Testar

```powershell
.venv\Scripts\python.exe stash-route\walk_route.py --route pier_to_car
```

Servidor com lag? Tente:

```powershell
.venv\Scripts\python.exe stash-route\walk_route.py --route pier_to_car --time-scale 1.03
```

---

## 3. Ajustar sem regravar (o mais importante)

```powershell
.venv\Scripts\python.exe stash-route\edit_route.py --route pier_to_car
```

| Tecla | Ação |
|-------|------|
| `3` | Seleciona segmento 3 |
| `+` / `-` | +100ms / -100ms |
| `++` / `--` | +500ms / -500ms |
| `t` | Testa **a partir** do segmento selecionado |
| `p` | Testa rota inteira |
| `s` | Salvar |

Exemplo: bate na escada = segmento da escada → `+` algumas vezes → `t` → repetir até ficar certo.

---

## 4. Dica de segmentos

| Trecho | Teclas típicas |
|--------|----------------|
| Reta na grade | `w` |
| Curva | `w`+`d` ou `w`+`a` (segmento curto, 0.2–0.5s) |
| Escada | só `w` (ajuste duração no editor) |
| Até o carro | `w` |

---

## Scripts antigos (evite se possível)

| Script | Quando usar |
|--------|-------------|
| `record_route.py` | Gravação contínua (mais difícil de acertar) |
| `tune_route.py` | Corrigir só o final a partir de um `t_ms` |

Prefira **build_route + edit_route**.
