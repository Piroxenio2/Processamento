"""
ERT Studio — Processamento de Eletrorresistividade (ERT) e SEV
Versão 2.0

Interface PySide6 para processamento de caminhamento elétrico (dipolo-dipolo,
formato RES2DINV/SIGNAL) e sondagem elétrica vertical (Schlumberger, IP2Win).
Metodologia: Loke (2003), Edwards (1977), Palacky (1987), curso SIGNAL Geofísica.

Histórico de versões: ver CHANGELOG.md.

Requisitos:  pip install -r requirements.txt
Executar:    ./bin/python3.14 geofisica.py
"""

import time
import os
import sys
import glob
import itertools
import hashlib          # v1.6: seed estável e reprodutível para a SEV
import warnings
# v2.0 (§3): filtros restritos — ignorar só ruído conhecido (matplotlib/pygimli),
# sem mascarar erros novos do nosso próprio código
warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pygimli")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pygimli")

# ══════════════════════════════════════════════════════════════════════
# NÚCLEO DO PROCESSAMENTO
# ══════════════════════════════════════════════════════════════════════

try:
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import matplotlib.colors as mcolors
    import matplotlib.tri as mtri
    from scipy.interpolate import interp1d
    from scipy.optimize import least_squares
    from scipy.special import j1            # v1.6: Bessel J1 para o operador SEV correto
    LIBS_OK = True
except ImportError as e:
    LIBS_OK = False
    LIBS_ERR = str(e)

# ──────────────────────────────────────────────────────────────────────
# v1.6: numpy 2.x renomeou np.trapz -> np.trapezoid. Resolve uma única vez
# de forma compatível com numpy 1.x e 2.x (evita AttributeError em runtime).
# ──────────────────────────────────────────────────────────────────────
if LIBS_OK:
    _trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz")

try:
    import pygimli as pg
    import pygimli.physics.ert as ert
    GIMLI_OK = True
except ImportError:
    GIMLI_OK = False

# v2.0: PySide6 substitui Tkinter (decisão de design §2 — acabamento Qt)
try:
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
        QVBoxLayout, QHBoxLayout, QStackedWidget, QGroupBox,
        QListWidget, QListWidgetItem, QAbstractItemView, QLineEdit, QSpinBox,
        QDoubleSpinBox, QComboBox, QCheckBox, QRadioButton, QButtonGroup,
        QTextEdit, QPlainTextEdit, QProgressBar, QFileDialog, QMessageBox,
        QMenu, QDialog, QDialogButtonBox, QFormLayout)
    QT_OK = True
except ImportError:
    QT_OK = False

# ══════════════════════════════════════════════════════════════════════
# PALETA E ESTILO  (fontes multiplataforma para Linux/macOS/Windows)
# ══════════════════════════════════════════════════════════════════════
# v2.0: constantes COR_*/FONTE_* do Tkinter removidas — a UI agora é Qt (QSS).

# ══════════════════════════════════════════════════════════════════════
# v2.0 — TEMA QT (claro + sidebar escura, design §4.1)
# ══════════════════════════════════════════════════════════════════════
#
# ──────────────────────────────────────────────────────────────────────
# REGISTRO DE ALTERAÇÕES PONTUAIS
# Formato: ALTER_NNN — data — descrição resumida
# O número é sequencial e independente do nome do arquivo, permitindo
# rastrear a ordem das modificações em qualquer versão do código.
# ──────────────────────────────────────────────────────────────────────
# ALTER_001 — 2026-06-12
#   Problema : QCheckBox e QRadioButton não tinham cor de texto explícita
#              no QSS_TEMA. Em sistemas Linux com tema escuro do SO, o Qt
#              herda a cor "WindowText" do tema nativo — que pode ser
#              branco ou quase transparente sobre o fundo branco dos
#              QGroupBox, tornando os rótulos invisíveis.
#   Correção : Adicionadas regras QCheckBox e QRadioButton ao QSS_TEMA
#              com color: #1e293b (mesma cor usada nos campos de entrada).
#              Também explicitado background: transparent para garantir
#              que o fundo do GroupBox não vaze sobre o indicador.
# ──────────────────────────────────────────────────────────────────────

QSS_TEMA = """
* { font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 10pt; }
QMainWindow, QStackedWidget > QWidget { background: #f8fafc; }
#sidebar { background: #1f2937; min-width: 205px; max-width: 205px; }
#logo { color: white; font-size: 13pt; font-weight: bold; padding: 16px 14px; }
QPushButton[nav="true"] { color: #cbd5e1; background: transparent; border: none;
  text-align: left; padding: 10px 14px; border-radius: 6px; margin: 2px 8px; }
QPushButton[nav="true"]:checked { background: #374151; color: white;
  border-left: 3px solid #3b82f6; }
QPushButton#btn_processar { background: #10b981; color: white; font-weight: bold;
  border-radius: 7px; margin: 10px; padding: 11px; }
QPushButton#btn_processar:disabled { background: #6b7280; }
QPushButton#btn_parar { background: #ef4444; color: white; font-weight: bold;
  border-radius: 7px; padding: 8px 16px; }
QGroupBox { background: white; border: 1px solid #e2e8f0; border-radius: 8px;
  margin-top: 14px; padding: 12px 10px 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px;
  color: #334155; font-weight: bold; }
QPushButton { background: #3b82f6; color: white; border: none;
  border-radius: 6px; padding: 7px 14px; }
QPushButton[secundario="true"] { background: #e2e8f0; color: #334155; }
QPushButton[perigo="true"] { background: #fee2e2; color: #b91c1c; }
QListWidget, QTextEdit, QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox,
QComboBox { background: white; border: 1px solid #d0d5dd; border-radius: 6px;
  padding: 3px 6px; color: #1e293b; }
QLabel { color: #334155; }
QLabel[mutado="true"] { color: #64748b; font-size: 9pt; }
QProgressBar { border: 1px solid #d0d5dd; border-radius: 5px; background: #e9edf3;
  text-align: center; }
QProgressBar::chunk { background: #3b82f6; border-radius: 4px; }
QPlainTextEdit#caixa_log { background: #0f172a; color: #6ee7b7;
  font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt; }
QPlainTextEdit#caixa_resumo { background: #0f172a; color: #93c5fd;
  font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt; }
/* ALTER_001: cor explícita para evitar herança do tema escuro do SO */
QCheckBox { color: #1e293b; background: transparent; }
QRadioButton { color: #1e293b; background: transparent; }
QCheckBox::indicator { width: 15px; height: 15px; }
QRadioButton::indicator { width: 15px; height: 15px; }
"""

# Tabela de Edwards — profundidades pseudo para dipolo-dipolo
ZE_EDWARDS_DD = {1: 0.416, 2: 0.697, 3: 0.962, 4: 1.220,
                 5: 1.476, 6: 1.730, 7: 1.983, 8: 2.236}



# ══════════════════════════════════════════════════════════════════════
# HELPERS GERAIS
# ══════════════════════════════════════════════════════════════════════

def formatar_eta(s):
    if s < 60:   return f"{s:.0f}s"
    if s < 3600: return f"{s//60:.0f}m {s%60:.0f}s"
    return f"{s//3600:.0f}h {(s%3600)//60:.0f}m"



# ══════════════════════════════════════════════════════════════════════
# AUXILIARES GEOMÉTRICOS  (nível de módulo — boas práticas Python)
# Anteriormente definidas como funções aninhadas dentro de
# processar_arquivo. Elevadas porque não fazem closure sobre nenhuma
# variável local da função-pai: recebem tudo por parâmetro.
# ══════════════════════════════════════════════════════════════════════

def _calcular_envelope_trapezio(df_l, ex_eletrodos, ze_edwards_dd, espacamento,
                                x_min_ext=None, x_max_ext=None):
    """
    Calcula o envelope trapezoidal que delimita a região de cobertura de dados
    em profundidade para um perfil dipolo-dipolo.

    Para cada nível n, a profundidade pseudo ze_n = ZE_EDWARDS_DD[n] * a
    corresponde a uma janela lateral [x_esq, x_dir]. O conjunto de pares
    (ze_n, x_esq_n, x_dir_n) define as bordas do trapézio; interpolação
    linear entre os pares produz funções f_esq(z) e f_dir(z) usadas para:
      - mascarar células de inversão fora da cobertura de dados;
      - traçar o polígono trapezoidal nas figuras de resultado.

    Parâmetros
    ----------
    df_l : DataFrame com colunas 'n' (nível) e 'a' (espaçamento).
    ex_eletrodos : array de posições de eletrodos.
    ze_edwards_dd : dict {n: fator_Edwards}.
    espacamento : espaçamento base do arranjo (m).
    x_min_ext, x_max_ext : se fornecidos, ativa modo Extended Model.

    Retorna
    -------
    f_esq, f_dir : interpoladores (z→x) para as bordas esquerda e direita.
    ze_pts[0], ze_pts[-1] : profundidades mínima e máxima do trapézio.
    """
    x_el_min = float(ex_eletrodos.min())
    x_el_max = float(ex_eletrodos.max())
    is_extended = (x_min_ext is not None)
    niveis_u = sorted(df_l["n"].unique().astype(int))
    zes, xesqs, xdirs = [], [], []
    for nv in niveis_u:
        sub = df_l[df_l["n"] == nv]
        if sub.empty:
            continue
        ze_n = ze_edwards_dd.get(nv, nv * 0.25) * espacamento
        if is_extended:
            a_metros = float(np.median(sub["a"].values.astype(float)))
            recuo    = nv * a_metros
            x_esq    = max(x_el_min + recuo, x_el_min)
            x_dir    = min(x_el_max - recuo, x_el_max)
        else:
            x_esq = x_el_min
            x_dir = x_el_max
        zes.append(ze_n); xesqs.append(x_esq); xdirs.append(x_dir)
    ze_max_local = max(zes) if zes else 0.0
    if len(zes) < 2:
        return (lambda z: x_el_min), (lambda z: x_el_max), 0.0, float(ze_max_local)
    ordem = np.argsort(zes)
    zes   = np.array(zes)[ordem]
    xesqs = np.array(xesqs)[ordem]
    xdirs = np.array(xdirs)[ordem]
    ze_pts  = np.concatenate([[0.0], zes])
    esq_pts = np.concatenate([[x_el_min], xesqs])
    dir_pts = np.concatenate([[x_el_max], xdirs])
    for i in range(1, len(esq_pts)):
        esq_pts[i] = max(esq_pts[i], esq_pts[i-1])
    for i in range(1, len(dir_pts)):
        dir_pts[i] = min(dir_pts[i], dir_pts[i-1])
    f_esq = interp1d(ze_pts, esq_pts, kind="linear",
                     bounds_error=False, fill_value=(esq_pts[0], esq_pts[-1]))
    f_dir = interp1d(ze_pts, dir_pts, kind="linear",
                     bounds_error=False, fill_value=(dir_pts[0], dir_pts[-1]))
    return f_esq, f_dir, ze_pts[0], ze_pts[-1]


# Nota v1.6: a antiga _mascara_celulas_trapezio (mascaramento célula a célula
# da malha PyGIMLi) foi REMOVIDA — o recorte na profundidade de investigação
# agora é feito de forma robusta pelo envelope suave em _gerar_resultados_ert.


# ══════════════════════════════════════════════════════════════════════
# FIGURAS ERT (v1.6) — renderização desacoplada do PyGIMLi
# ══════════════════════════════════════════════════════════════════════
# Motivação: usar pg.show() impunha o próprio layout (eixos, aspecto, barra
# de cores), o que gerava a FAIXA BRANCA e as figuras "esticadas" reclamadas.
# Aqui extraímos a triangulação da malha e desenhamos com matplotlib puro,
# com controle total dos eixos — a região abaixo da profundidade de
# investigação é recortada por um envelope SUAVE (sem serrilha, sem deformar).
# Validado com seções sintéticas (ver memória do projeto).
# ══════════════════════════════════════════════════════════════════════

def _paradomain_triangulacao(mesh):
    """
    Converte a malha de inversão do PyGIMLi (paraDomain) em uma
    matplotlib.tri.Triangulation + índice das células triangulares.

    Robustez de convenção: o PyGIMLi pode guardar a profundidade em y OU z
    dependendo da versão/configuração. Detectamos o eixo vertical como aquele
    de MAIOR amplitude entre y e z (o horizontal é sempre x).

    Retorna (tri, idx_cels) onde idx_cels mapeia cada triângulo da
    triangulação para o índice da célula correspondente em mod_arr.
    """
    n_nodes = mesh.nodeCount()
    nx = np.array([mesh.node(i).x() for i in range(n_nodes)], dtype=float)
    ny = np.array([mesh.node(i).y() for i in range(n_nodes)], dtype=float)
    nz = np.array([mesh.node(i).z() for i in range(n_nodes)], dtype=float)
    vy = ny if (ny.max() - ny.min()) >= (nz.max() - nz.min()) else nz

    tris, idx_cels = [], []
    for ci in range(mesh.cellCount()):
        cel = mesh.cell(ci)
        ids = [cel.node(k).id() for k in range(cel.nodeCount())]
        if len(ids) == 3:                      # triângulo (caso usual do paraMesh)
            tris.append(ids); idx_cels.append(ci)
        elif len(ids) >= 4:                    # polígono: leque de triângulos
            for k in range(1, len(ids) - 1):
                tris.append([ids[0], ids[k], ids[k + 1]]); idx_cels.append(ci)
    tri = mtri.Triangulation(nx, vy, np.array(tris))
    return tri, np.array(idx_cels)


def _pseudosecao_ert(saida, x_m, ze_a, rh_v, x_el_min, x_el_max, espacamento,
                     titulo, log):
    """
    Pseudo-seção de resistividade aparente (diagnóstico de qualidade).

    v1.6 — CORRIGIDO o corte do lado esquerdo: usa margem lateral explícita,
    margem esquerda da figura suficiente para o rótulo do eixo Y, e NÃO
    depende só de bbox_inches='tight' (que cortava os pontos da borda).
    """
    fig, ax = plt.subplots(figsize=(14, 5))
    sc = ax.scatter(x_m, ze_a, c=np.log10(rh_v), cmap="Spectral_r",
                    s=55, edgecolors="none")
    cb = fig.colorbar(sc, ax=ax, pad=0.01)
    tlog = np.arange(np.floor(np.log10(rh_v.min())), np.ceil(np.log10(rh_v.max())) + 1)
    cb.set_ticks(tlog); cb.set_ticklabels([f"$10^{{{int(t)}}}$" for t in tlog])
    cb.set_label("ρa (Ω·m)")
    pad = max((x_el_max - x_el_min) * 0.03, espacamento)   # margem lateral
    ax.set_xlim(x_el_min - pad, x_el_max + pad)
    ax.set_ylim(ze_a.max() * 1.10, 0)
    ax.set_title(titulo)
    ax.set_xlabel("Distância (m)")
    ax.set_ylabel("Profundidade pseudo (m) — Edwards (z para baixo)")
    fig.subplots_adjust(left=0.07, right=1.0)              # garante rótulo Y visível
    fig.savefig(saida + "_pseudosecao.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    log(f"  Pseudo-seção → {saida}_pseudosecao.png")


def _faixas_resistividade(vals, n_faixas=15):
    """
    Faixas (níveis) log-espaçadas para a escala de cores de resistividade.

    Recortadas pelos percentis 3–97 para descartar outliers. Quando vários
    perfis ERT são processados juntos, `vals` é a CONCATENAÇÃO dos modelos de
    todos eles → uma escala de cores ÚNICA e comparável entre as seções
    (v1.8). Para um único perfil, equivale ao comportamento anterior.
    """
    vals = np.asarray(vals, dtype=float).ravel()
    vmin = max(np.percentile(vals, 3), 1.0)
    vmax = np.percentile(vals, 97)
    if vmax <= vmin:
        vmax = vmin * 10
    return np.logspace(np.log10(vmin), np.log10(vmax), n_faixas + 1)


def _montar_triangulacao_render(mesh, mod_arr):
    """v2.0: monta a geometria de render compartilhada pela figura de RESULTADO
    e pela figura de INTERPRETAÇÃO, garantindo que as duas usem a MESMA
    triangulação/valores (mesma geometria de pixel). Devolve
    (tri, idx_cels, val_cel, val_node):
      tri      — matplotlib.tri.Triangulation da paraDomain;
      idx_cels — célula de mod_arr por triângulo;
      val_cel  — ρ por triângulo;
      val_node — ρ nodal (média das células incidentes) p/ tricontourf suave.
    Extraído de _gerar_resultados_ert SEM alterar seu resultado (bit-compatível).
    """
    tri, idx_cels = _paradomain_triangulacao(mesh)
    val_cel = np.asarray(mod_arr, dtype=float)[idx_cels]      # ρ por triângulo
    # valores NODAIS (média das células incidentes) → sombreamento Gouraud suave
    n_nodes = len(tri.x)
    soma = np.zeros(n_nodes); cont = np.zeros(n_nodes)
    for k, (a, b, c) in enumerate(tri.triangles):
        for nd in (a, b, c):
            soma[nd] += val_cel[k]; cont[nd] += 1
    val_node = np.maximum(soma / np.maximum(cont, 1), 1e-6)
    return tri, idx_cels, val_cel, val_node


def _gerar_resultados_ert(saida, mesh, mod_arr, ex, ez, topo, espacamento,
                          ze_mask_max, z_surf, info_txt, rodape_txt,
                          extended_xy, nome_base, log, ve="auto",
                          direcao="Nenhuma", lev_fixo=None, interpretacao=None):
    """
    Figura de resultado do ERT — Layout 2 (modelo + barra de cores vertical à
    direita), com FAIXAS DISCRETAS de resistividade (contornos preenchidos,
    estilo RES2DINV) e linhas nos limites das bandas.

    `ve` = exagero vertical: "auto" (adapta-se à razão comprimento/profundidade
    da linha) ou um número (1 = escala real; 2, 3, 4, 6 = vezes). Linhas longas
    e rasas pedem MENOS exagero; linhas curtas, mais — daí o modo automático.

    v1.6: escolhido o Layout 2 (entre os 5 prototipados). A renderização usa
    faixas discretas (tricontourf) em vez de gradiente contínuo, porque as
    faixas facilitam DELIMITAR as camadas (o gradiente suave borrava os
    limites). Mantém o controle total dos eixos: sem faixa branca (recorte por
    envelope na profundidade de investigação) e sem deformar (aspect='auto').
    """
    # ── Triangulação + valores por célula ─────────────────────────────
    # v2.0: geometria extraída p/ helper compartilhado com a interpretação.
    tri, idx_cels, val_cel, val_node = _montar_triangulacao_render(mesh, mod_arr)

    # ── Faixas DISCRETAS de resistividade (estilo RES2DINV) ───────────
    # v1.6: o gradiente contínuo (Gouraud) ficava bonito mas BORRAVA os limites
    # entre camadas. Voltamos a FAIXAS discretas (contornos preenchidos) — como
    # no RES2DINV e no processamento antigo — para facilitar a DELIMITAÇÃO das
    # camadas, com linhas finas nos limites das bandas. N_FAIXAS log-espaçadas.
    # lev_fixo (v1.8): faixas COMPARTILHADAS entre vários perfis processados
    # juntos → mesma paleta para comparação. Se None, calcula a partir deste perfil.
    if lev_fixo is not None:
        lev = np.asarray(lev_fixo, dtype=float)
        N_FAIXAS = len(lev) - 1
    else:
        N_FAIXAS = 15
        lev = _faixas_resistividade(val_cel, N_FAIXAS)
    cmap = plt.get_cmap("Spectral_r", N_FAIXAS)            # discreto (faixas nítidas)
    norm = mcolors.BoundaryNorm(lev, N_FAIXAS)

    x0, x1 = float(ex.min()), float(ex.max())
    if len(topo) >= 2:
        surf = interp1d(topo["x"], topo["z"], kind="linear", fill_value="extrapolate")
    else:
        surf = lambda xx: np.full_like(np.asarray(xx, float), z_surf)
    xf = np.linspace(x0, x1, 400)
    yb  = np.asarray(surf(xf), float) - ze_mask_max          # base de investigação
    ylo = float(yb.min() - 1.0)
    yhi = float(np.asarray(surf(xf), float).max() + 3.0)

    # ── Exagero vertical (VE) → controla a ALTURA da figura ───────────
    # Em vez de set_aspect (que encolhe o eixo e desalinha a barra de cores),
    # dimensionamos a ALTURA do painel para obter o VE desejado mantendo
    # aspect='auto' — assim a barra de cores (mesma célula do gridspec)
    # acompanha a altura. VE=1 ≈ escala real; VE>1 estica a vertical.
    x_range = x1 - x0
    y_range = max(yhi - ylo, 1e-6)
    if isinstance(ve, str):   # "auto": mira um painel ~7:1 (largura:altura)
        VE = float(np.clip((x_range / y_range) / 7.0, 1.0, 6.0))
        ve_txt = f"VE≈{VE:.1f}× (auto)"
    else:
        VE = max(float(ve), 0.1)
        ve_txt = f"VE={VE:.0f}×"

    figW = 13.0; L, R = 0.06, 0.93
    # bot_abs maior (v1.7): a legenda e a caixa de infos saíram de DENTRO do
    # painel para a margem inferior — precisam de espaço próprio, sem sobrepor.
    top_abs, bot_abs = 0.45, 1.55          # polegadas p/ título e rótulos/rodapé
    panel_W = figW * (R - L) * 0.93        # largura útil do painel (desconta barra)
    panel_H = float(np.clip(VE * panel_W * y_range / x_range, 1.2, 7.5))
    figH = panel_H + top_abs + bot_abs
    top_frac = 1.0 - top_abs / figH
    bot_frac = bot_abs / figH

    # ── Figura (Layout 2) ─────────────────────────────────────────────
    fig = plt.figure(figsize=(figW, figH))
    gs = gridspec.GridSpec(1, 2, width_ratios=[44, 1], wspace=0.02,
                           left=L, right=R, top=top_frac, bottom=bot_frac)
    ax  = fig.add_subplot(gs[0])
    cax = fig.add_subplot(gs[1])

    # modelo em FAIXAS preenchidas + linhas de contorno nos limites das bandas
    tcf = ax.tricontourf(tri, val_node, levels=lev, cmap=cmap, norm=norm, extend="both")
    ax.tricontour(tri, val_node, levels=lev, colors="#333333",
                  linewidths=0.25, alpha=0.35, zorder=4)   # delimita as faixas
    # recorte da região abaixo da profundidade de investigação
    ax.fill_between(xf, yb, ylo, color="white", zorder=5, lw=0)
    ax.plot(xf, yb, color="#666", ls="--", lw=0.8, zorder=6,
            label=f"Limite Edwards ({ze_mask_max:.0f} m)")
    if extended_xy is not None:
        ax.plot(extended_xy[0], extended_xy[1], color="#555", lw=1.0,
                alpha=0.8, zorder=6)
    if len(topo) >= 2:
        ax.plot(topo["x"], topo["z"], "k-", lw=1.3, zorder=8, label="Superfície topográfica")
    ax.plot(ex, ez, "v", color="black", markersize=6, markeredgecolor="white",
            markeredgewidth=0.5, zorder=9, label="Eletrodos")
    ax.set_xlim(x0, x1); ax.set_ylim(ylo, yhi); ax.set_aspect("auto")
    ax.set_xlabel("Distância (m)", fontsize=10)
    ax.set_ylabel("Cota / Profundidade (m)", fontsize=10)
    ax.set_title(f"{nome_base}", loc="left", fontsize=11)

    # ── Rótulos de direção nos cantos superiores (v1.7) ───────────────
    # O início da linha fica à ESQUERDA e progride para a DIREITA; a opção
    # escolhida na aba de configurações define o par de letras dos cantos.
    _DIR_MAP = {"W → E": ("W", "E"), "E → W": ("E", "W"),
                "N → S": ("N", "S"), "S → N": ("S", "N")}
    if direcao in _DIR_MAP:
        _esq, _dir = _DIR_MAP[direcao]
        _badge = dict(boxstyle="circle,pad=0.3", fc="white", ec="#333",
                      lw=1.0, alpha=0.92)
        ax.text(0.010, 0.96, _esq, transform=ax.transAxes, fontsize=12,
                fontweight="bold", ha="left", va="top", color="#111",
                zorder=12, bbox=_badge)
        ax.text(0.990, 0.96, _dir, transform=ax.transAxes, fontsize=12,
                fontweight="bold", ha="right", va="top", color="#111",
                zorder=12, bbox=_badge)

    # ── Legenda e caixa de infos ABAIXO do painel (v1.7) ──────────────
    # Antes ficavam DENTRO do painel (lower-left / lower-right) e sobrepunham
    # a seção. Agora vão para a margem inferior (coords da FIGURA), logo
    # abaixo do rótulo do eixo X, sem sobreposição.
    y_band = (bot_abs - 0.45) / figH       # logo abaixo de "Distância (m)"
    ax.legend(loc="upper left", bbox_to_anchor=(L, y_band),
              bbox_transform=fig.transFigure, fontsize=7, framealpha=0.0,
              ncol=3, handlelength=1.4, columnspacing=1.2, borderaxespad=0.0)
    fig.text(R, y_band, info_txt + f"\n{ve_txt}", fontsize=7,
             ha="right", va="top", zorder=10,
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#bbb", alpha=0.92))

    # barra de cores DISCRETA (mesma altura do painel) — estilo RES2DINV
    cb = fig.colorbar(tcf, cax=cax, boundaries=lev, ticks=lev, spacing="uniform")
    cb.set_ticklabels([f"{v:.0f}" for v in lev])
    cb.ax.tick_params(labelsize=6.5)
    cb.set_label("Resistividade (Ω·m)", fontsize=9)

    fig.text(L, 0.14 / figH, rodape_txt, fontsize=7, color="#444", va="bottom")
    fig.savefig(saida + "_resultado.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    log(f"  Resultado → {saida}_resultado.png  ({ve_txt})")

    # ── v2.0 (§7): gancho TEMPORÁRIO da figura de interpretação ─────────
    # NASCE DESLIGADA — só é gerada quando o chamador passa `interpretacao`
    # explicitamente (dict {"geo":..., "deriv":...}); a UI NÃO expõe isso até
    # o usuário aprovar o exemplo. Reusa tri/máscara/valores já montados.
    if interpretacao is not None:
        try:
            mod_arr_tri = np.asarray(mod_arr, dtype=float)[idx_cels]
            cam = _gerar_figura_interpretacao(
                saida, tri, val_cel, val_node, mod_arr_tri,
                surf, xf, yb, ylo, yhi, x0, x1,
                figW, figH, L, R, top_frac, bot_frac,
                interpretacao.get("geo", {}), interpretacao.get("deriv", {}),
                ve_txt, nome_base, log=log)
            if cam:
                log(f"  Interpretação → {cam}")
        except Exception as _e:
            import traceback
            log(f"  ERRO ao gerar figura de interpretação: {_e}")
            log(traceback.format_exc())


def _gerar_figura_interpretacao(saida, tri, val_cel, val_node, mod_arr_tri,
                                surf, xf, yb, ylo, yhi, x0, x1,
                                figW, figH, L, R, top_frac, bot_frac,
                                geo, deriv, ve_txt, nome_base, log=print):
    """v2.0 (§7): seção interpretada — zonas litológicas pelo cruzamento das
    faixas de Palacky (1987) com os litotipos selecionados pelo usuário.
    NASCE DESLIGADA: gerada só por chamada explícita (gancho `interpretacao`
    em _gerar_resultados_ert) até o usuário aprovar o exemplo concreto.

    Reusa a MESMA triangulação/máscara/geometria da figura de RESULTADO
    (parâmetros vindos prontos de _gerar_resultados_ert) → casamento de pixel.
    `val_cel`/`mod_arr_tri` = ρ por triângulo; `val_node` = ρ nodal (contatos).
    """
    # v2.0 (§7, rev.2): zoneamento por PERFIL DE INTEMPERISMO ancorado em
    # Palacky. Classificação absoluta pura colapsa em 1 classe quando o
    # modelo inteiro cabe na faixa (larga) de um litotipo — sem utilidade.
    # Zonas geológicas reais de uma seção: cobertura/zona saturada → rocha
    # alterada/fraturada → rocha sã, com limites na faixa do litotipo.
    lits = [l for l in geo.get("litotipos", []) if l in FAIXAS_RHO_PALACKY]
    if not lits:
        return None
    vals_pos = mod_arr_tri[mod_arr_tri > 0]
    if vals_pos.size == 0:
        return None
    classes_geo = geo.get("classe", "")
    # litotipo dominante = o de faixa mais alta (rocha-alvo do perfil)
    lito_dom = max(lits, key=lambda l: FAIXAS_RHO_PALACKY[l][1])
    lo_dom, hi_dom = FAIXAS_RHO_PALACKY[lito_dom]
    gm_dom = float(np.sqrt(lo_dom * hi_dom))   # média geométrica da faixa

    if classes_geo in ("Metamórfica", "Ígnea"):
        # Perfil de intemperismo cristalino (contextos do app: solo residual
        # → saprolito → rocha alterada → rocha sã)
        bordas_def = [
            (lo_dom,  "Solo / saprolito argiloso (zona condutiva)"),
            (gm_dom,  f"{lito_dom} alterado/fraturado" +
                      (" — possível zona saturada" if geo.get("agua_rasa") else "")),
            (None,    f"{lito_dom} são (topo rochoso)"),
        ]
    elif classes_geo == "Sedimentar":
        # Sedimentar: classes de Palacky funcionam (faixas distintas por
        # litotipo) — mantém o zoneamento absoluto entre litotipos
        cls = sorted(lits, key=lambda l: np.sqrt(
            FAIXAS_RHO_PALACKY[l][0] * FAIXAS_RHO_PALACKY[l][1]))
        limites = [float(np.sqrt(FAIXAS_RHO_PALACKY[a][1] *
                                 FAIXAS_RHO_PALACKY[b][0]))
                   for a, b in zip(cls[:-1], cls[1:])]
        bordas_def = [(lim, f"{c}") for c, lim in zip(cls[:-1], limites)]
        bordas_def.append((None, cls[-1]))
    else:
        # Classe desconhecida/mista: 3 zonas em quantis log do próprio modelo
        q1, q2 = np.quantile(np.log10(vals_pos), [0.33, 0.66])
        bordas_def = [(10**q1, "Zona condutiva (argila/saturação)"),
                      (10**q2, "Zona intermediária"),
                      (None,   "Zona resistiva (rocha sã?)")]

    # salinidade: classe de fluido no piso
    rotulos  = [r for _, r in bordas_def]
    limites  = [b for b, _ in bordas_def if b is not None]
    if geo.get("salina"):
        limites = [1.0] + limites
        rotulos = ["Água salina/salobra (fluido)"] + rotulos
    vmin_m = max(float(np.min(mod_arr_tri)), 0.01)
    vmax_m = float(np.max(mod_arr_tri)) * 1.01
    bordas = np.array([min(vmin_m, (limites[0] if limites else vmin_m) / 10)]
                      + limites + [max(vmax_m, (limites[-1] if limites else vmax_m) * 10)])
    bordas = np.maximum.accumulate(bordas)   # monotônico (digitize exige)
    n = len(rotulos)

    # classe por triângulo (digitize sobre as bordas monotônicas)
    idx = np.clip(np.digitize(mod_arr_tri, bordas) - 1, 0, n - 1)

    # ── Figura: MESMA geometria/altura da figura de resultado ─────────
    fig = plt.figure(figsize=(figW, figH))
    gs = gridspec.GridSpec(1, 2, width_ratios=[44, 1], wspace=0.02,
                           left=L, right=R, top=top_frac, bottom=bot_frac)
    ax  = fig.add_subplot(gs[0])
    cax = fig.add_subplot(gs[1])

    # mapa discreto de classes (cores qualitativas, não escala de ρ)
    base = plt.get_cmap("tab10")
    cores = [base(i % 10) for i in range(n)]
    cmap = mcolors.ListedColormap(cores)
    tcf = ax.tripcolor(tri, facecolors=idx.astype(float), cmap=cmap,
                       vmin=-0.5, vmax=n - 0.5, shading="flat")
    # contatos litológicos nos limites internos (try/except defensivo)
    try:
        niveis = [np.log10(b) for b in bordas[1:-1] if b > 0]
        if niveis:
            ax.tricontour(tri, np.log10(np.maximum(val_node, 1e-6)),
                          levels=niveis, colors="k", linestyles="--",
                          linewidths=0.8, zorder=4)
    except Exception:
        pass
    # EXTRA: contato do TOPO ROCHOSO realçado (objetivo explícito + cristalino).
    # gm_dom já é um dos contatos internos; redesenha mais grosso e anota.
    cristalino = classes_geo in ("Metamórfica", "Ígnea")
    if cristalino and "topo_rochoso" in geo.get("objetivos", []):
        try:
            ax.tricontour(tri, np.log10(np.maximum(val_node, 1e-6)),
                          levels=[np.log10(gm_dom)], colors="k",
                          linestyles="--", linewidths=1.6, zorder=7)
            ax.annotate("topo rochoso provável",
                        xy=(x1 - (x1 - x0) * 0.02, (ylo + yhi) / 2),
                        ha="right", va="center", fontsize=8, color="k",
                        bbox=dict(boxstyle="round,pad=0.2", fc="white",
                                  ec="#666", alpha=0.8), zorder=9)
        except Exception:
            pass
    # MÁSCARA: mesmo mecanismo da figura de resultado — pinta de branco a
    # região abaixo da profundidade de investigação (envelope de Edwards).
    ax.fill_between(xf, yb, ylo, color="white", zorder=5, lw=0)
    ax.plot(xf, yb, color="#666", ls="--", lw=0.8, zorder=6)
    # superfície topográfica — mesma da figura de resultado
    try:
        ax.plot(xf, np.asarray(surf(xf), float), "k-", lw=1.0, zorder=8)
    except Exception:
        pass
    ax.set_xlim(x0, x1); ax.set_ylim(ylo, yhi); ax.set_aspect("auto")
    ax.set_xlabel("Distância (m)", fontsize=10)
    ax.set_ylabel("Cota / Profundidade (m)", fontsize=10)
    ax.set_title(
        f"{nome_base} — INTERPRETAÇÃO GEOLÓGICA PRELIMINAR\n"
        f"(faixas de Palacky 1987 × litotipos informados — conferir em campo)",
        loc="left", fontsize=10)

    # barra de cores discreta: ticks centrados, rótulo + INTERVALO de bordas
    # da zona (não a faixa Palacky cheia) em Ωm (fonte 7)
    def _fmt(v):
        return f"{v:g}" if v < 10 else f"{v:.0f}"
    cb = fig.colorbar(tcf, cax=cax, ticks=range(n))
    labels = [f"{rotulos[i]}\n({_fmt(bordas[i])}–{_fmt(bordas[i+1])} Ωm)"
              for i in range(n)]
    cb.set_ticklabels(labels)
    cb.ax.tick_params(labelsize=7)
    cb.set_label("Zona litológica interpretada", fontsize=9)

    # nota de rodapé (precaução: figura preliminar)
    nota = ("Zoneamento automático pelo cruzamento ρ × Palacky (1987). "
            "Não substitui sondagem/mapeamento — validar em campo.")
    fig.text(L, 0.02, nota, fontsize=7, color="#444", va="bottom")

    cam = saida + "_interpretacao.png"
    fig.savefig(cam, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return cam


# ══════════════════════════════════════════════════════════════════════
# v2.0 — EXPORTAÇÃO 3D (design §9): XYZ consolidado + VTK legacy p/
# ParaView (isosuperfícies/voxel como no fluxo VOXI dos materiais).
# Sem dependência nova: o formato VTK legacy ASCII é escrito à mão.
# ══════════════════════════════════════════════════════════════════════
def _transformar_EN(x_local, origem, azimute):
    """Posição local x (m ao longo da linha) → (E, N).
    `azimute` em graus a partir do Norte, sentido horário (0°=N, 90°=E)."""
    az = np.radians(azimute)
    E = origem[0] + np.asarray(x_local, float) * np.sin(az)
    N = origem[1] + np.asarray(x_local, float) * np.cos(az)
    return E, N


def _escrever_vtk_pontos(caminho, pontos, valores, nome_escalar="resistividade"):
    """Nuvem de pontos em VTK legacy ASCII (POLYDATA). Abre no ParaView;
    aplicar 'Delaunay 3D' ou 'Point Volume Interpolator' p/ voxel."""
    pontos  = np.asarray(pontos, float)
    valores = np.asarray(valores, float)
    with open(caminho, "w") as f:
        f.write("# vtk DataFile Version 3.0\n")
        f.write("ERT Studio v2.0 - modelo de resistividade invertida\n")
        f.write("ASCII\nDATASET POLYDATA\n")
        f.write(f"POINTS {len(pontos)} float\n")
        for p in pontos:
            f.write(f"{p[0]:.3f} {p[1]:.3f} {p[2]:.3f}\n")
        f.write(f"POINT_DATA {len(pontos)}\n")
        f.write(f"SCALARS {nome_escalar} float 1\nLOOKUP_TABLE default\n")
        for v in valores:
            f.write(f"{v:.4f}\n")


def _exportar_xyz_consolidado(pasta_saida, linhas_3d):
    """CSV consolidado E,N,cota,resistividade de todas as linhas + .vtk.
    `linhas_3d`: lista de dicts {nome, E, N, z, rho} (arrays por célula)."""
    import csv
    csv_path = os.path.join(pasta_saida, "modelo_3d_consolidado.csv")
    vtk_path = os.path.join(pasta_saida, "modelo_3d_consolidado.vtk")
    pts, vals = [], []
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["linha", "E_m", "N_m", "cota_m", "rho_ohm_m"])
        for l in linhas_3d:
            for e, n, z, r in zip(l["E"], l["N"], l["z"], l["rho"]):
                w.writerow([l["nome"], f"{e:.3f}", f"{n:.3f}",
                            f"{z:.3f}", f"{r:.4f}"])
                pts.append([e, n, z]); vals.append(r)
    _escrever_vtk_pontos(vtk_path, np.array(pts), np.array(vals))
    return csv_path, vtk_path


def _gerar_mapa_niveis(pasta_saida, linhas_3d, profundidades=None, meia_banda=None):
    """v2.0 (§9, curso SIGNAL 'Mapa de Níveis'): vista em planta da
    resistividade interpolada em profundidades fixas, a partir de ≥2 linhas
    com coordenadas. Devolve a lista de PNGs gerados."""
    from scipy.interpolate import griddata
    if len(linhas_3d) < 2:
        return []
    # profundidade abaixo da superfície de cada célula
    pontos_E, pontos_N, prof_cel, rho_cel = [], [], [], []
    for l in linhas_3d:
        prof = np.asarray(l["z_superficie"]) - np.asarray(l["z"])
        pontos_E.append(l["E"]); pontos_N.append(l["N"])
        prof_cel.append(prof);   rho_cel.append(l["rho"])
    E = np.concatenate(pontos_E); N = np.concatenate(pontos_N)
    P = np.concatenate(prof_cel); R = np.concatenate(rho_cel)

    if profundidades is None:   # 3 níveis automáticos na zona investigada
        pmax = np.percentile(P, 90)
        profundidades = [round(pmax * f, 1) for f in (0.2, 0.5, 0.8)]
    if meia_banda is None:
        meia_banda = max(1.0, float(np.percentile(P, 90)) * 0.12)

    figs = []
    lev = _faixas_resistividade(R[R > 0])
    norm = mcolors.BoundaryNorm(lev, 256)
    for prof_alvo in profundidades:
        m = np.abs(P - prof_alvo) <= meia_banda
        if m.sum() < 8:
            continue
        gE, gN = np.meshgrid(np.linspace(E.min(), E.max(), 200),
                             np.linspace(N.min(), N.max(), 200))
        gR = griddata((E[m], N[m]), R[m], (gE, gN), method="linear")
        fig, ax = plt.subplots(figsize=(9, 7))
        im = ax.contourf(gE, gN, gR, levels=lev, cmap=plt.get_cmap("jet"),
                         norm=norm, extend="both")
        for l in linhas_3d:   # traço das linhas em planta
            ax.plot(l["E"], l["N"], "k-", lw=0.6, alpha=0.6)
            ax.annotate(l["nome"], (l["E"][0], l["N"][0]), fontsize=7)
        ax.scatter(E[m], N[m], s=2, c="k", alpha=0.25)
        ax.set_xlabel("E (m)"); ax.set_ylabel("N (m)")
        ax.set_title(f"Mapa de níveis — profundidade {prof_alvo:g} m "
                     f"(±{meia_banda:g} m)")
        ax.set_aspect("equal")
        cb = fig.colorbar(im, ax=ax, shrink=0.85)
        cb.set_label("Resistividade (Ω·m)")
        out = os.path.join(pasta_saida, f"mapa_nivel_{prof_alvo:g}m.png")
        fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)
        figs.append(out)
    return figs


def _consolidar_exportacao_3d(dados3d, coordenadas, pasta_saida, log):
    """v2.0.1 (§9): consolida e exporta o 3D do lote (CSV+VTK+mapas de níveis).

    Extraída do worker para ser testável e — correção pós-entrega — para
    AVISAR no log quando o 3D é pulado por falta de coordenadas (antes a
    exportação falhava em silêncio e o usuário não sabia o porquê).

    `dados3d`: lista de tuplas (nome, ex, ez, rho_por_célula, extra3d).
    `coordenadas`: {arquivo: (E0, N0, azimute)}. `log`: callable(str).
    Devolve True se exportou algo.
    """
    if not dados3d:
        return False
    linhas_3d, sem_coord = [], []
    for nome_b, ex_l, ez_l, rho_l, extra in dados3d:
        coord = coordenadas.get(extra["arquivo_origem"])
        if coord is None:
            sem_coord.append(nome_b)
            continue
        E, N = _transformar_EN(extra["celulas_x"], coord[:2], coord[2])
        linhas_3d.append({
            "nome": nome_b, "E": E, "N": N,
            "z": extra["celulas_z"],
            "z_superficie": np.interp(extra["celulas_x"], ex_l, ez_l),
            "rho": rho_l})
    if not linhas_3d:
        log("\n  ℹ 3D/mapa de níveis NÃO gerados: nenhuma linha tem coordenadas.")
        log("    Defina-as com o botão direito no arquivo (etapa 1 · Dados) →")
        log("    'Definir coordenadas da linha…' (E, N da origem e azimute) e reprocesse.")
        return False
    if sem_coord:
        log(f"\n  ℹ Linhas SEM coordenadas (fora do 3D): {', '.join(sem_coord)} —")
        log("    botão direito no arquivo → 'Definir coordenadas da linha…'.")
    csv_p, vtk_p = _exportar_xyz_consolidado(pasta_saida, linhas_3d)
    log(f"\n  3D consolidado: {os.path.basename(csv_p)} "
        f"e {os.path.basename(vtk_p)} (abrir no ParaView).")
    for fp in _gerar_mapa_niveis(pasta_saida, linhas_3d):
        log(f"  Mapa de nível: {os.path.basename(fp)}")
    return True


# ══════════════════════════════════════════════════════════════════════
# PIPELINE ERT (Caminhamento Elétrico)
# ══════════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────────────
# v2.0: leitura RES2DINV extraída de processar_arquivo para função própria
# (testável sem PyGIMLi). Comportamento idêntico ao v1.x nesta etapa.
# ──────────────────────────────────────────────────────────────────────
def _ler_ert_res2dinv(arquivo_txt):
    """Lê arquivo ERT formato RES2DINV/SIGNAL.

    Retorna dict: nome, espacamento, arranjo, n_declarado, n_topo_declarado,
    posicao_tipo, df_raw (x,a,n,rhoa), topo (x,z), avisos (lista p/ log).
    """
    try:
        with open(arquivo_txt, encoding="utf-8") as f:
            linhas = f.readlines()
    except UnicodeDecodeError:
        with open(arquivo_txt, encoding="latin-1") as f:
            linhas = f.readlines()

    avisos = []   # v2.0: preenchido pelas validações de robustez (contagens/arranjo/vírgula)

    # v2.0 (§8): vírgula decimal → ponto (roteiro SIGNAL manda trocar no Excel;
    # o programa agora faz sozinho e avisa)
    if any("," in ln for ln in linhas):
        linhas = [ln.replace(",", ".") for ln in linhas]
        avisos.append("Vírgulas decimais detectadas e convertidas para ponto.")

    nome         = linhas[0].strip()
    espacamento  = float(linhas[1].strip())
    arranjo      = int(float(linhas[2].strip()))
    # v2.0 (§8): código do arranjo (manual RES2DINV: 3 = dipolo-dipolo)
    if arranjo != 3:
        avisos.append(f"Arranjo código {arranjo} não suportado — tratando como "
                      f"dipolo-dipolo (3); resultados podem ser inválidos.")
    n_declarado  = int(float(linhas[3].strip()))
    posicao_tipo = int(float(linhas[4].strip()))  # 0 = primeiro eletrodo; 1 = ponto médio

    rows_ert, rows_topo = [], []
    modo_topo = False
    n_topo_declarado = None
    i = 6
    while i < len(linhas):
        p = linhas[i].strip().split()
        if len(p) == 1 and p[0] == "2" and rows_ert and not modo_topo:
            modo_topo = True
            if i + 1 < len(linhas):
                n_topo_declarado = int(float(linhas[i + 1].strip()))
            i += 2
            continue
        if modo_topo:
            if len(p) >= 2:
                try: rows_topo.append([float(x) for x in p[:2]])
                except Exception: pass
        elif len(p) == 4:
            try: rows_ert.append([float(x) for x in p])
            except Exception: pass
        i += 1

    df_raw = pd.DataFrame(rows_ert, columns=["x", "a", "n", "rhoa"])
    topo   = pd.DataFrame(rows_topo, columns=["x", "z"])

    # v2.0 (§8): valida contagens declaradas no cabeçalho (arquivo truncado?)
    if len(df_raw) != n_declarado:
        avisos.append(f"Cabeçalho declara {n_declarado} leituras; lidas "
                      f"{len(df_raw)} — arquivo truncado ou malformado?")
    if n_topo_declarado is not None and len(topo) != n_topo_declarado:
        avisos.append(f"Topografia declara {n_topo_declarado} pontos; lidos {len(topo)}.")

    return {"nome": nome, "espacamento": espacamento, "arranjo": arranjo,
            "n_declarado": n_declarado, "n_topo_declarado": n_topo_declarado,
            "posicao_tipo": posicao_tipo, "df_raw": df_raw, "topo": topo,
            "avisos": avisos}


# ──────────────────────────────────────────────────────────────────────
# v2.0: QC extraído de processar_arquivo (testável) + relatório por
# critério (§6 do design — espelha o "exterminate bad data points" do
# roteiro SIGNAL) + limites geologia-cientes (§5.2).
# ──────────────────────────────────────────────────────────────────────
def _qc_ert(df_raw, params, faixa_rho=None, salina=False):
    """Controle de qualidade do ERT. Testa combinações de fatores e devolve
    (melhor_df, relatorio). `faixa_rho`: (min, max) plausível p/ a geologia —
    SINALIZA pontos fora, não remove. `salina`: True desativa a remoção de
    valores baixos pelo IQR (água salgada < 1 Ωm é físico, não outlier)."""
    RHOA_MAX = params["rhoa_max"]
    N_RIG    = params["n_nivel_rigoroso"]
    JANELA   = 3

    combos_qc = list(itertools.product(
        params["iqr_raso"], params["iqr_prof"], params["fviz"]))
    melhor_score, melhor_df, melhor_rel = -np.inf, None, None

    for fir, fip, fvz in combos_qc:
        d = df_raw.copy(); d["valido"] = True
        rel = {"removidos_teto": 0, "removidos_iqr": 0, "removidos_vizinhanca": 0,
               "flags_geologia": 0, "fatores": (fir, fip, fvz)}
        # 1) teto absoluto
        m_teto = d["rhoa"] > RHOA_MAX
        rel["removidos_teto"] = int(m_teto.sum())
        d.loc[m_teto, "valido"] = False
        # 2) IQR por nível (v2.0: com salinidade esperada, só o lado alto remove)
        for nv in sorted(d["n"].unique()):
            mask = d["valido"] & (d["n"] == nv)
            vals = d.loc[mask, "rhoa"]
            if len(vals) < 4: continue
            fat = fip if nv >= N_RIG else fir
            Q1, Q3 = vals.quantile(0.25), vals.quantile(0.75)
            IQR = Q3 - Q1
            alto  = d["rhoa"] > Q3 + fat * IQR
            baixo = d["rhoa"] < max(Q1 - fat * IQR, 0.1)
            out = mask & (alto if salina else (alto | baixo))
            rel["removidos_iqr"] += int(out.sum())
            d.loc[out, "valido"] = False
        # 3) razão contra a mediana dos vizinhos (igual ao v1.x)
        for nv in sorted(d["n"].unique()):
            idx_l = d.index[d["valido"] & (d["n"] == nv)].tolist()
            if len(idx_l) < 3: continue
            xs = d.loc[idx_l, "x"].values; rh = d.loc[idx_l, "rhoa"].values
            ordem = np.argsort(xs); xs_s = xs[ordem]; rh_s = rh[ordem]
            idx_s = [idx_l[o] for o in ordem]
            for j in range(len(xs_s)):
                viz = [rh_s[k] for k in range(max(0, j - JANELA),
                       min(len(xs_s), j + JANELA + 1)) if k != j]
                if not viz: continue
                mv = np.median(viz)
                if mv > 0 and max(rh_s[j] / mv, mv / rh_s[j]) > fvz:
                    d.loc[idx_s[j], "valido"] = False
                    rel["removidos_vizinhanca"] += 1
        df_l = d[d["valido"]].copy().reset_index(drop=True)
        if len(df_l) < 10: continue
        # 4) v2.0: faixa geológica plausível — SINALIZA, não remove (§5.2)
        if faixa_rho is not None:
            fora = (df_l["rhoa"] < faixa_rho[0]) | (df_l["rhoa"] > faixa_rho[1])
            rel["flags_geologia"] = int(fora.sum())
        rel["n_final"] = len(df_l); rel["n_inicial"] = len(df_raw)
        score = len(df_l) / len(df_raw) - 0.3 * np.log10(df_l["rhoa"].std() + 1)
        if score > melhor_score:
            melhor_score, melhor_df, melhor_rel = score, df_l, rel
    return melhor_df, melhor_rel


def _verificar_niveis(df_raw, fator_alerta=10.0):
    """v2.0 (§6, roteiro SIGNAL): a mediana de ρa por nível deve variar de
    forma gradual; salto > fator_alerta entre níveis adjacentes merece aviso
    (pode ser geologia — mas o usuário deve conferir os dados de campo)."""
    med = df_raw.groupby("n")["rhoa"].median()
    niveis = sorted(med.index)
    avisos = []
    for n1, n2 in zip(niveis[:-1], niveis[1:]):
        if med[n1] <= 0 or med[n2] <= 0: continue
        razao = max(med[n2] / med[n1], med[n1] / med[n2])
        if razao > fator_alerta:
            avisos.append(f"ρa mediano salta {razao:.0f}× do nível {int(n1)} "
                          f"para o {int(n2)} — conferir dados de campo (ΔV) "
                          f"ou contraste geológico real.")
    return avisos


# ══════════════════════════════════════════════════════════════════════
# v2.0 — GEOLOGIA ESTRUTURADA → PARÂMETROS (design §5.2)
# Faixas de resistividade por litotipo (Ωm), adaptadas de Palacky (1987)
# apud Resistivity.pdf (UBC) — valores típicos saturados.
# ══════════════════════════════════════════════════════════════════════
FAIXAS_RHO_PALACKY = {
    "Sedimentos inconsolidados (areia/cascalho)": (50, 2000),
    "Argila / argilito":   (1, 100),
    "Arenito":             (50, 1000),
    "Calcário / dolomito": (100, 10000),
    "Folhelho":            (10, 200),
    "Gnaisse":             (500, 50000),
    "Xisto":               (100, 5000),
    "Quartzito":           (1000, 100000),
    "Mármore":             (500, 50000),
    "Filito / ardósia":    (50, 2000),
    "Granito":             (1000, 100000),
    "Basalto / diabásio":  (500, 50000),
    "Gabro":               (1000, 100000),
    "Riolito":             (500, 50000),
}
# Objetivos com contatos abruptos → L1 "blocky" (Loke §1);
# alvos gradacionais → L2 suave.
_OBJETIVOS_ABRUPTOS     = {"topo_rochoso", "estruturas", "espessura_solo"}
_OBJETIVOS_GRADACIONAIS = {"nivel_dagua", "intrusao_salina"}

def _derivar_params_geologia(geo):
    """Traduz a geologia estruturada (PaginaGeologia.coletar()) em parâmetros
    de inversão/QC. Sem geologia → tudo neutro (comportamento v1.x)."""
    neutro = {"norma": None, "zweight": None, "faixa_rho": None,
              "salina": False, "notas": []}
    if not geo:
        return neutro
    notas = []

    # 1) Norma L1/L2 pelo objetivo do estudo (Loke: blocky vs suave)
    objs = set(geo.get("objetivos", []))
    ab, gr = objs & _OBJETIVOS_ABRUPTOS, objs & _OBJETIVOS_GRADACIONAIS
    if ab and not gr:
        norma = "L1"; notas.append("alvo com contatos abruptos → norma L1 robusta (Loke)")
    elif gr and not ab:
        norma = "L2"; notas.append("alvo gradacional → norma L2 suave (Loke)")
    else:
        norma = None
        if ab and gr:
            notas.append("objetivos mistos → busca L1+L2 mantida")

    # 2) zWeight (filtro vertical/horizontal do RES2DINV).
    #    Precedência: estruturas verticais vencem o acamadamento (§5.2).
    if "estruturas" in objs:
        zweight = 1.0; notas.append("alvo estrutural vertical → zWeight=1.0 (isotrópico)")
    elif geo.get("classe") == "Sedimentar":
        zweight = 0.5; notas.append("geologia acamadada → zWeight=0.5 (suaviza horizontal)")
    else:
        zweight = None

    # 3) Faixa plausível de ρ: união das faixas dos litotipos, margem ÷3/×3
    faixa = None
    lits = [l for l in geo.get("litotipos", []) if l in FAIXAS_RHO_PALACKY]
    if lits:
        fmin = min(FAIXAS_RHO_PALACKY[l][0] for l in lits) / 3.0
        fmax = max(FAIXAS_RHO_PALACKY[l][1] for l in lits) * 3.0
        if geo.get("salina"):
            fmin = min(fmin, 0.3)   # água salgada < 1 Ωm é físico
        faixa = (fmin, fmax)
        notas.append(f"faixa ρ plausível (Palacky): {fmin:.2g}–{fmax:.2g} Ωm")

    salina = bool(geo.get("salina"))
    if salina:
        notas.append("salinidade esperada → QC não remove ρa baixos")
    return {"norma": norma, "zweight": zweight, "faixa_rho": faixa,
            "salina": salina, "notas": notas}


def processar_arquivo(arquivo_txt, pasta_saida, params, geo_info, fila_log, fila_prog,
                      direcao=None, coletor_render=None):
    """
    Pipeline completo para um arquivo ERT. Usa filas para comunicar progresso.

    `direcao`: orientação da linha (W → E, N → S…) para os rótulos dos cantos;
    se None, usa params["direcao_linha"]. Escolhida POR ARQUIVO (v1.8).
    `coletor_render`: se uma lista for passada, a figura de RESULTADO não é
    gerada aqui — os argumentos de render são acumulados nela para que o
    chamador renderize todos com a MESMA paleta de cores (v1.8).
    """

    def log(msg):    fila_log.put(("log", msg))
    def prog(v, t):  fila_prog.put((v, t))

    if direcao is None:
        direcao = params.get("direcao_linha", "Nenhuma")

    nome_base = os.path.splitext(os.path.basename(arquivo_txt))[0]
    saida     = os.path.join(pasta_saida, nome_base)

    log(f"\n{'═'*60}")
    log(f"  Processando ERT: {os.path.basename(arquivo_txt)}")
    log(f"{'═'*60}")

    # ── Leitura ──────────────────────────────────────────────────────
    prog(2, "Lendo arquivo…")
    # v2.0: leitura delegada ao parser módulo-level (testável)
    leitura = _ler_ert_res2dinv(arquivo_txt)
    espacamento, posicao_tipo = leitura["espacamento"], leitura["posicao_tipo"]
    df_raw, topo = leitura["df_raw"], leitura["topo"]
    for av in leitura["avisos"]:
        log(f"  ⚠ {av}")

    # v2.0 (§5.2): transparência — registrar o que a geologia mudou
    for nota in params.get("notas_geo", []):
        log(f"  Geologia → {nota}")

    # v2.0 (§5.2): zWeight derivado da geologia (filtro vertical/horizontal,
    # manual RES2DINV). Montado UMA vez; usado nos 4 sítios de invert via
    # **kw_extra. Fallback p/ versões PyGIMLi que não aceitem o kwarg
    # (mesmo padrão do fallback de relrms()).
    kw_extra = {}
    if params.get("zweight") is not None:
        kw_extra["zWeight"] = params["zweight"]

    def _invert(mgr, dados, **kw):
        """v2.0: invoca mgr.invert com zWeight da geologia + fallback."""
        try:
            return mgr.invert(dados, **kw, **kw_extra)
        except TypeError:
            if kw_extra:
                log("  ⚠ PyGIMLi desta versão não aceita zWeight — ignorado.")
                kw_extra.clear()
                return mgr.invert(dados, **kw)
            raise

    niveis = sorted(df_raw["n"].unique().astype(int))
    ze_max = max(ZE_EDWARDS_DD.get(n, n * 0.25) * espacamento for n in niveis)

    log(f"  Medições: {len(df_raw)}  |  Topo: {len(topo)} pts  |  ze_max={ze_max:.1f}m")
    prog(8, "Controle de qualidade…")

    # v2.0: QC delegado à função módulo-level com relatório por critério
    melhor_df, rel_qc = _qc_ert(df_raw, params,
                                faixa_rho=params.get("faixa_rho_geo"),
                                salina=params.get("salina_esperada", False))
    if melhor_df is None:
        log("  ERRO: Nenhum conjunto de QC produziu dados suficientes."); return
    fir, fip, fvz = rel_qc["fatores"]
    log(f"  QC: IQR_r={fir} IQR_p={fip} viz={fvz} → "
        f"{rel_qc['n_final']}/{rel_qc['n_inicial']} pts")
    log(f"  QC detalhado: teto={rel_qc['removidos_teto']}  "
        f"IQR={rel_qc['removidos_iqr']}  vizinhança={rel_qc['removidos_vizinhanca']}"
        + (f"  | fora da faixa geológica (mantidos): {rel_qc['flags_geologia']}"
           if rel_qc["flags_geologia"] else ""))
    # v2.0 (§6): aviso de variação anômala entre níveis (roteiro SIGNAL)
    for av in _verificar_niveis(df_raw):
        log(f"  ⚠ {av}")
    prog(18, "Montando eletrodos…")

    # ── Reconstruir eletrodos ─────────────────────────────────────────
    def recon(df_l):
        av = df_l["a"].values.astype(float)
        nv = df_l["n"].values.astype(float)
        xv = df_l["x"].values.astype(float)
        df_l = df_l.copy()
        if posicao_tipo == 0:
            df_l["pos_A"] = xv
            df_l["pos_B"] = xv + av
            df_l["pos_M"] = xv + (nv + 1.0) * av
            df_l["pos_N"] = xv + (nv + 2.0) * av
        else:
            df_l["pos_A"] = xv - (nv / 2.0 + 1.0) * av
            df_l["pos_B"] = xv - (nv / 2.0)        * av
            df_l["pos_M"] = xv + (nv / 2.0)        * av
            df_l["pos_N"] = xv + (nv / 2.0 + 1.0) * av
        todas = np.concatenate([df_l["pos_A"], df_l["pos_B"],
                                df_l["pos_M"], df_l["pos_N"]])
        ex = np.unique(np.round(todas, 4))
        if len(topo) >= 2:
            ft = interp1d(topo["x"], topo["z"], kind="linear", fill_value="extrapolate")
            ez = ft(ex)
        else:
            ez = np.zeros(len(ex))
        return df_l, ex, ez

    def build_data(df_l, ex, ez):
        def idx(p): return int(np.argmin(np.abs(ex - p)))
        data = pg.DataContainerERT()
        for x, z in zip(ex, ez):
            data.createSensor(pg.RVector3(x, z))
        data.resize(len(df_l))
        data["a"] = pg.IVector([idx(v) for v in df_l["pos_A"]])
        data["b"] = pg.IVector([idx(v) for v in df_l["pos_B"]])
        data["m"] = pg.IVector([idx(v) for v in df_l["pos_M"]])
        data["n"] = pg.IVector([idx(v) for v in df_l["pos_N"]])
        data["rhoa"] = pg.Vector(df_l["rhoa"].values)
        data.markValid(data["rhoa"] > 0)
        data["k"] = pg.physics.ert.geometricFactors(data)
        data["r"] = pg.Vector(np.array(data["rhoa"]) / np.array(data["k"]))
        ra = np.array(data["rhoa"]); eb = np.full(len(ra), params["erro_rel"])
        p75 = np.percentile(ra, 75); mask_a = ra > p75
        eb[mask_a] = params["erro_rel"] * (1 + np.log10(ra[mask_a] / p75))
        data["err"] = pg.Vector(np.clip(eb, params["erro_rel"], 0.5))
        return data

    df_l, ex, ez = recon(melhor_df)
    z_surf = float(ez.mean()) if len(topo) >= 2 else 0.0
    data_p = build_data(df_l, ex, ez)

    # ── Modelo estendido ──────────────────────────────────────────────
    linha_len  = float(ex.max() - ex.min())
    ext_m      = linha_len * params["ext_factor"] if params["extended_model"] else 0.0
    x_ext_min  = float(ex.min()) - ext_m
    x_ext_max  = float(ex.max()) + ext_m
    modelo_txt = (f"Extended Model (fator={params['ext_factor']:.2f}, "
                  f"+{ext_m:.1f}m/lado)") if params["extended_model"] else "Standard Model"
    log(f"  Modelo: {modelo_txt}  →  x=[{x_ext_min:.1f}, {x_ext_max:.1f}]m")

    # ── Envelope trapezoidal ──────────────────────────────────────────
    # Nota: _calcular_envelope_trapezio e _mascara_celulas_trapezio estão
    # agora definidas em nível de módulo (antes de processar_arquivo).
    _xmin_trap = x_ext_min if params["extended_model"] else None
    _xmax_trap = x_ext_max if params["extended_model"] else None
    f_esq_trap, f_dir_trap, ze_trap_min, ze_trap_max = \
        _calcular_envelope_trapezio(df_raw, ex, ZE_EDWARDS_DD, espacamento,
                                    x_min_ext=_xmin_trap, x_max_ext=_xmax_trap)

    # ── Busca de parâmetros de inversão ───────────────────────────────
    # Tamanho de célula da malha (paraMaxCellSize): SEMPRE o espaçamento do
    # imageamento OU a sua metade — nunca outros valores. As duas opções são
    # testadas e a busca abaixo fica com a de MENOR erro (RMS).
    cell_sizes = [espacamento, espacamento / 2.0]
    log(f"  Célula da malha testada: {espacamento:.2f} m e {espacamento/2.0:.2f} m "
        f"(espaçamento e metade)")
    combos_inv = list(itertools.product(
        params["lam"], params["robust"], params["tol"],
        cell_sizes, params["margem_prof"]))
    n_total = len(combos_inv)
    log(f"\n  Testando {n_total} combinações de inversão…")
    prog(20, f"Inversão: 0/{n_total}")

    melhor_rms = np.inf; melhor_par = None
    melhor_mgr = None;   melhor_mod = None
    t0 = time.time(); tempos = []
    data_inv = data_p
    resultados = []

    for ci, (lam, rob, tol, cell, marg) in enumerate(combos_inv, 1):
        pd_depth = round(ze_max * marg, 1)
        t_it = time.time()
        try:
            mgr_i = ert.ERTManager(data_inv)
            if params["extended_model"] and ext_m > 0:
                para_mesh = pg.meshtools.createParaMesh(
                    data_inv.sensors(),
                    paraDepth=pd_depth,
                    paraBoundary=ext_m,
                    paraMaxCellSize=cell,
                    quality=34.0,
                )
                mod_i = _invert(mgr_i, data_inv, lam=lam, maxIter=params["max_iter"],
                                verbose=False, robust=rob,
                                mesh=para_mesh, tolerance=tol)
            else:
                mod_i = _invert(mgr_i, data_inv, lam=lam, maxIter=params["max_iter"],
                                verbose=False, robust=rob,
                                paraDepth=pd_depth, paraMaxCellSize=cell,
                                tolerance=tol)
            # FIX: API PyGIMLi ≥1.4 — relrms() está diretamente em mgr.inv
            # O padrão antigo mgr.inv.inv.relrms() falha nas versões novas
            try:
                rms_i = mgr_i.inv.relrms()
            except AttributeError:
                rms_i = mgr_i.inv.inv.relrms()   # fallback para versão antiga
            chi_i = mgr_i.inv.chi2()
        except Exception:
            rms_i = chi_i = 9999.; mgr_i = mod_i = None

        dur = time.time() - t_it; tempos.append(dur)
        eta = np.mean(tempos) * (n_total - ci)
        rob_s = "Rob(L1)" if rob else "Suav(L2)"
        resultados.append({"lam": lam, "robust": rob, "tol": tol,
                           "cell": cell, "depth": pd_depth,
                           "rms": round(rms_i, 3), "chi2": round(chi_i, 3)})
        log(f"  Comb {ci:3d}/{n_total}  λ={lam:4d} {rob_s} tol={tol} "
            f"cell={cell:g}m depth={pd_depth:.0f}m → "
            f"RMS={rms_i:6.2f}% χ²={chi_i:7.3f}  ETA:{formatar_eta(eta)}")
        pct = 20 + int(60 * ci / n_total)
        prog(pct, f"Combinação {ci}/{n_total}  ETA: {formatar_eta(eta)}")

        if rms_i < melhor_rms and mgr_i is not None:
            melhor_rms = rms_i
            melhor_par = {"lam": lam, "robust": rob, "tol": tol,
                          "cell": cell, "depth": pd_depth}
            melhor_mgr = mgr_i; melhor_mod = mod_i

    # log_inv.csv removido (alteração 21)

    if melhor_mgr is None:
        log("  ERRO: Nenhuma inversão convergiu."); return

    log(f"\n  ✓ Melhor 1ª inversão: λ={melhor_par['lam']} "
        f"{'Rob' if melhor_par['robust'] else 'Suav'} "
        f"tol={melhor_par['tol']} → RMS={melhor_rms:.2f}%")
    prog(82, "Pós-inversão…")

    # ── Pós-inversão ──────────────────────────────────────────────────
    resp1  = np.array(melhor_mgr.inv.response)
    meas1  = np.array(melhor_mgr.data["rhoa"])
    resid1 = np.abs((resp1 - meas1) / meas1) * 100

    melhor_rms_f  = melhor_rms
    melhor_chi2_f = melhor_mgr.inv.chi2()
    melhor_mgr_f  = melhor_mgr
    melhor_mod_f  = melhor_mod
    melhor_df_f   = df_l; melhor_lim = None; n_rem_pos = 0
    ex_f, ez_f    = ex, ez

    for lim in params["limiar_pos"]:
        ok = resid1 <= lim
        if ok.sum() < 10: continue
        df_p2 = df_l.iloc[ok].copy().reset_index(drop=True)
        df_p2, ex2, ez2 = recon(df_p2)
        try:
            d2 = build_data(df_p2, ex2, ez2)
            m2 = ert.ERTManager(d2)
            if params["extended_model"] and ext_m > 0:
                para_mesh2 = pg.meshtools.createParaMesh(
                    d2.sensors(),
                    paraDepth=melhor_par["depth"],
                    paraBoundary=ext_m,
                    paraMaxCellSize=melhor_par["cell"],
                    quality=34.0,
                )
                mo2 = _invert(m2, d2, lam=melhor_par["lam"], maxIter=params["max_iter"],
                              verbose=False, robust=melhor_par["robust"],
                              mesh=para_mesh2, tolerance=melhor_par["tol"])
            else:
                mo2 = _invert(m2, d2, lam=melhor_par["lam"], maxIter=params["max_iter"],
                              verbose=False, robust=melhor_par["robust"],
                              paraDepth=melhor_par["depth"],
                              paraMaxCellSize=melhor_par["cell"],
                              tolerance=melhor_par["tol"])
            try:
                r2 = m2.inv.relrms()
            except AttributeError:
                r2 = m2.inv.inv.relrms()
            c2 = m2.inv.chi2()
        except Exception:
            r2 = c2 = 9999.; m2 = mo2 = None

        log(f"  Pós-inv limiar={lim:.0f}%  rem={int((~ok).sum())}  RMS={r2:.2f}%")
        if r2 < melhor_rms_f and m2 is not None:
            melhor_rms_f = r2; melhor_chi2_f = c2; melhor_mgr_f = m2
            melhor_mod_f = mo2; melhor_df_f = df_p2; melhor_lim = lim
            n_rem_pos = int((~ok).sum()); ex_f, ez_f = ex2, ez2

    prog(92, "Gerando figuras…")

    # ── Figuras (v1.6: pseudo-seção + resultado Layout 2 suave) ────────
    mod_arr  = np.array(melhor_mod_f)
    n_pts_f  = len(melhor_df_f)

    x_el_min = x_ext_min; x_el_max = x_ext_max
    z_surf_f = float(ez.mean()) if len(topo) >= 2 else 0.0

    # Envelope trapezoidal — usado só para (a) profundidade máxima de
    # investigação e (b) traçar o contorno do modelo estendido (se ativo).
    f_esq_trap, f_dir_trap, _, ze_trap_max = \
        _calcular_envelope_trapezio(df_raw, ex, ZE_EDWARDS_DD, espacamento,
                                    x_min_ext=_xmin_trap, x_max_ext=_xmax_trap)
    ze_mask_max = max(ze_max, ze_trap_max)

    extended_xy = None
    if params["extended_model"]:
        # contorno (x, z) do trapézio para sobrepor no modelo
        _profs = np.linspace(0, ze_mask_max, 60)
        _xs = [float(f_esq_trap(p)) for p in _profs] + \
              [float(f_dir_trap(p)) for p in reversed(_profs)]
        _zs = [z_surf_f - p for p in _profs] + \
              [z_surf_f - p for p in reversed(_profs)]
        extended_xy = (np.array(_xs), np.array(_zs))

    # ── Pseudo-seção (corrigida: sem corte à esquerda) ─────────────────
    x_m  = melhor_df.x.values; n_a = melhor_df.n.values.astype(int)
    a_a  = melhor_df.a.values;  rh_v = melhor_df.rhoa.values
    ze_a = np.array([ZE_EDWARDS_DD.get(ni, ni*0.25)*ai for ni, ai in zip(n_a, a_a)])
    _fir, _fip, _fvz = rel_qc["fatores"]
    _titulo_ps = (f"Pseudo-seção — {nome_base}  ({len(melhor_df)}/{len(df_raw)} pts)  |  "
                  f"IQR_r={_fir}  IQR_p={_fip}  viz={_fvz}")
    _pseudosecao_ert(saida, x_m, ze_a, rh_v, x_el_min, x_el_max,
                     espacamento, _titulo_ps, log)

    # ── Resultado Layout 2 (renderização suave desacoplada do PyGIMLi) ─
    # Textos informativos (estilo RES2DINV) usados na figura.
    _rob_s = "Robust L1" if melhor_par["robust"] else "Smooth L2"
    _inv_s = f"2ª inv. lim={melhor_lim}%" if melhor_lim else "1ª inv."
    info_txt = (
        f"Erro abs = {melhor_rms_f:.1f}%   χ² = {melhor_chi2_f:.2f}   {_inv_s}\n"
        f"λ={melhor_par['lam']}  {_rob_s}  depth={melhor_par['depth']:.0f}m   "
        f"{n_pts_f}/{len(df_raw)} pts"
    )
    rodape_txt = (
        f"Seção de Resistividade Invertida   |   λ={melhor_par['lam']} {_rob_s}   "
        f"cell={melhor_par['cell']}m   depth={melhor_par['depth']:.0f}m   "
        f"{modelo_txt}   espaç. eletrodos {espacamento:.2f} m"
    )
    render_kwargs = dict(
        saida=saida, mesh=melhor_mgr_f.paraDomain, mod_arr=mod_arr,
        ex=ex_f, ez=ez_f, topo=topo, espacamento=espacamento,
        ze_mask_max=ze_mask_max, z_surf=z_surf_f, info_txt=info_txt,
        rodape_txt=rodape_txt, extended_xy=extended_xy, nome_base=nome_base,
        log=log, ve=params.get("ve_exagero", "auto"), direcao=direcao)
    # v2.0 (§9): dados por célula p/ exportação 3D e mapa de níveis.
    # Viajam sob a chave "extra3d", removida (pop) antes do render —
    # _gerar_resultados_ert recebe **kwargs estritos.
    cc = np.array(melhor_mgr_f.paraDomain.cellCenters())   # (n, 3): x, z(cota), 0
    extra3d = {"arquivo_origem": arquivo_txt,
               "celulas_x": cc[:, 0], "celulas_z": cc[:, 1]}
    if len(cc) != len(np.asarray(mod_arr)):
        log(f"  ⚠ 3D: nº de centros de célula ({len(cc)}) ≠ modelo "
            f"({len(np.asarray(mod_arr))}) — exportação 3D pulada p/ este arquivo.")
        extra3d = None
    if coletor_render is not None:
        # Render adiado: o chamador gera todas as figuras com a MESMA paleta (v1.8).
        coletor_render.append({**render_kwargs, "extra3d": extra3d})
        log("  Resultado adiado p/ paleta compartilhada do lote.")
    else:
        try:
            _gerar_resultados_ert(**render_kwargs)
        except Exception as _e:
            # Defensivo: se a extração da malha falhar em alguma versão do PyGIMLi,
            # registra o erro mas não derruba o processamento do lote.
            import traceback
            log(f"  ERRO ao gerar figuras do resultado: {_e}")
            log(traceback.format_exc())

    # modelo.npy removido (alteração 21)
    # ── Resumo para painel de Configuração ──────────────────────────────
    fila_log.put(("resumo_ert", {
        "arquivo":      nome_base,
        "rms":          melhor_rms_f,
        "chi2":         melhor_chi2_f,
        "pts_aceitos":  n_pts_f,
        "pts_total":    len(df_raw),
        "lam":          melhor_par["lam"],
        "robust":       melhor_par["robust"],
        "depth":        melhor_par["depth"],
    }))
    prog(100, "Concluído!")
    log(f"\n  ✓ {nome_base} finalizado  RMS={melhor_rms_f:.2f}%  chi²={melhor_chi2_f:.3f}")


# ══════════════════════════════════════════════════════════════════════
# PIPELINE SEV (Sondagem Elétrica Vertical — Schlumberger)
# ══════════════════════════════════════════════════════════════════════
#
# NOTA: Esta seção implementa leitura e inversão 1D para SEV Schlumberger.
# Formato de arquivo esperado (TXT simples, sem cabeçalho):
#   AB/2 (m)    MN/2 (m)    rhoa (Ωm)
# Exemplo:
#   1.5   0.5   120.5
#   2.0   0.5   98.3
#   ...
#
# Operador direto (v1.6): transformada de Hankel J1 com a recorrência de
# resistividade de Pekeris (tanh λh), avaliada com a Bessel exata e matriz
# pré-computada (ver _make_sev_forward). VALIDADO contra a série exata de
# 2 camadas (erro máx. 0,20%) e por recuperação de modelo sintético.
# Inversão por scipy.optimize.least_squares (TRF + perda robusta soft_l1),
# busca multi-start guiada por dados e seleção do nº de camadas por AIC.
#
# Formatos de entrada:
#   - ODS (Guapigeo): cada aba = uma SEV. ρa lida da planilha.
#   - TXT simples:  AB/2 (m)  MN/2 (m)  ρa (Ωm)  — 3 colunas; # = comentário.
# Saídas: curva observada + figura de resultado (curva ajustada, modelo 1D,
# tabela de camadas) — sem CSV/NPY (removidos conforme solicitado).
# ──────────────────────────────────────────────────────────────────────

def _kernel_schlumberger(lam, rho, h):
    """
    Transformada de resistividade T(λ) de Pekeris para um modelo 1D
    estratificado (recorrência da BASE para o TOPO).
    rho: array de resistividades [Ωm], comprimento N (a última é o semi-espaço)
    h:   array de espessuras [m], comprimento N-1
    lam: número(s) de onda λ [1/m] — aceita escalar, 1D ou 2D (vetorizado)
    Retorna: T(λ), com as mesmas dimensões de `lam`.

    ─ CORREÇÃO CRÍTICA v1.6 — CONVENÇÃO CORRETA: tanh(λ·h)  (FATOR 1) ─
    A v1.3 havia introduzido tanh(2·λ·h). A validação numérica contra a
    série EXATA de 2 camadas (ρa→ρ1 quando AB/2→0 e ρa→ρ2 quando AB/2→∞)
    mostrou erro de 20–200% com o fator 2 e 0,00% com o fator 1 — ou seja,
    o "fator 2" era um BUG. Recorrência: T_i = ρ_i·(T + ρ_i·th)/(ρ_i + T·th).
    Refs.: Koefoed (1979) Geosounding Principles; Ghosh (1971).
    """
    lam = np.asarray(lam, dtype=float)
    # T começa no semi-espaço (camada mais profunda). Vetorizável em λ.
    T = np.full(np.shape(lam), float(rho[-1]))
    for i in range(len(rho) - 2, -1, -1):
        r_i = rho[i]
        th  = np.tanh(np.clip(lam * h[i], 0.0, 700.0))   # FATOR 1 (corrigido v1.6)
        T   = r_i * (T + r_i * th) / (r_i + T * th)
    return T







# ──────────────────────────────────────────────────────────────────────
# OPERADOR DIRETO SCHLUMBERGER — transformada de Hankel J1 (v1.6, validado).
#
# O filtro digital caseiro de 61 coeficientes das versões 1.2–1.5 foi
# REMOVIDO: ele era inválido (só acertava o semi-espaço homogêneo por causa
# da normalização Σw=1 e errava 20–200% em qualquer modelo com camadas).
# Em seu lugar, integramos diretamente a transformada de Hankel com a Bessel
# J1 EXATA (scipy.special.j1), na forma subtraída e convergente, com a
# matriz J1 pré-computada por sondagem (ver _make_sev_forward). Erro máximo
# validado contra a série exata de 2 camadas: 0,20%.
# ──────────────────────────────────────────────────────────────────────


def _make_sev_forward(ab2, h_min):
    """
    Fábrica do operador direto Schlumberger — validado a < 0,2% contra a
    série EXATA (2–5 camadas, contrastes até 1000:1).

    Física (forma subtraída, absolutamente convergente):
        ρa(s) = ρ1 + s² ∫₀^∞ [T(λ) − ρ1] J1(λ·s) λ dλ ,   s = AB/2
    com T(λ) pela recorrência de Pekeris (tanh λh, _kernel_schlumberger) e
    J1 a função de Bessel de 1ª ordem (scipy.special.j1).

    DESEMPENHO: a matriz J1(λ·AB/2) e os pesos de integração dependem apenas
    da grade de λ e de AB/2 (fixos por sondagem), NÃO de ρ/h. São
    pré-computados UMA vez aqui; cada chamada de forward(rho, h) custa só uma
    recorrência + um produto matricial (~1,7 ms) — ~13× mais rápido que
    integrar do zero a cada avaliação da inversão.

    Grade: λ_max = 25/h_min (onde [T−ρ1] ~ e^-50 ≈ 0) e ~8 amostras por
    oscilação de J1 no maior AB/2 — suficiente para erro < 0,2%.
    """
    ab2 = np.asarray(ab2, dtype=float)
    hmin = max(float(h_min), 1e-3)
    smax = float(ab2.max())
    lam_max = 25.0 / hmin
    n_lam = int(np.clip(8.0 * lam_max * smax / (2.0 * np.pi), 3000, 30000))
    lam = np.linspace(1e-6, lam_max, n_lam)
    J = j1(lam[:, None] * ab2[None, :])          # (n_lam, n_AB2) — constante
    w = np.gradient(lam)                          # pesos ~trapezoidais
    ab2_sq = ab2 ** 2

    def forward(rho, h):
        rho = np.asarray(rho, dtype=float)
        h   = np.asarray(h,   dtype=float)
        T   = _kernel_schlumberger(lam, rho, h)
        r1  = float(rho[0])
        g   = (T - r1) * lam * w                  # integrando ponderado
        rhoa = r1 + ab2_sq * (g @ J)              # ρ1 + s²∫[T−ρ1]J1λdλ
        return np.maximum(np.abs(rhoa), 1e-3)

    return forward


def _rhoa_schlumberger_modelo(ab2, rho, h):
    """
    Conveniência: resposta Schlumberger para um modelo conhecido (uso pontual,
    p.ex. traçar a curva calculada densa). Constrói o operador na hora.
    No laço de inversão use _make_sev_forward (pré-computa e é ~13× mais rápido).

    Nota física: na aproximação de Schlumberger (MN ≪ AB) ρa depende apenas
    de AB/2 — por isso não há argumento MN/2 (removido na v1.6).
    """
    ab2 = np.asarray(ab2, dtype=float)
    h   = np.asarray(h, dtype=float)
    # semi-espaço homogêneo (sem camadas) → h vazio: h_min é irrelevante (ρa=ρ1)
    h_min = float(np.min(h)) if h.size else 1.0
    return _make_sev_forward(ab2, max(h_min, 1e-3))(rho, h)


def _residuo_sev(params_flat, forward, rhoa_obs, n_camadas):
    """
    Resíduo no espaço log (robusto a grandes contrastes) para a otimização.
    `forward` é o operador pré-computado retornado por _make_sev_forward.
    """
    n = n_camadas
    rho = np.exp(params_flat[:n])
    h   = np.exp(params_flat[n:])
    rhoa_calc = forward(rho, h)
    return np.log(rhoa_calc + 1e-6) - np.log(rhoa_obs + 1e-6)


def _is_numeric_str(s):
    """Retorna True se a string representa um número (int ou float, incluindo notação científica)."""
    try:
        float(s.replace(",", "."))  # aceita vírgula como separador decimal
        return True
    except (ValueError, AttributeError):
        return False


def _ler_sev_aba(raw, sheet, log):
    """
    Lê uma aba de planilha ODS no formato de campo SEV Schlumberger.

    Layout real do arquivo (SEV.ods):
      Linha 0  — Cabeçalho textual: AB/2 | MN/2 | I(ma) | AV(mV) | K | pa
      Linhas 1+— Dados numéricos:
        col 0 = AB/2 (m)
        col 1 = MN/2 (m)
        col 2 = I (mA)
        col 3 = AV (mV)
        col 4 = K  (fator geométrico Schlumberger)
        col 5 = pa (ρa em Ωm — calculada pela planilha como K × ΔV/I)

    Pontos de embreagem (mesmo AB/2, MN/2 diferente) são mantidos
    integralmente: o modelo de inversão usa ab2 E mn2 para cada ponto.

    Retorna dict {'ab2', 'mn2', 'rhoa', 'K', 'meta'} ou None se aba inválida.
    """
    # ── Mínimo estrutural ─────────────────────────────────────────────
    # Precisamos de ao menos 2 linhas (header + 1 dado) e 6 colunas
    if raw.shape[0] < 2 or raw.shape[1] < 6:
        log(f"  Aviso: aba '{sheet}' tem shape {raw.shape} insuficiente — ignorada.")
        return None

    # ── Detecta linha de cabeçalho ────────────────────────────────────
    # FIX v1.2: células vazias retornam NaN (float); str(NaN).strip() = "nan" → falso positivo.
    # Verificamos explicitamente se o valor é uma string não-numérica.
    first_vals = raw.iloc[0].values
    has_header = any(
        isinstance(v, str) and v.strip() and not _is_numeric_str(v.strip())
        for v in first_vals
    )
    data_start = 1 if has_header else 0

    # ── Metadados mínimos ─────────────────────────────────────────────
    meta = {"aba": sheet, "sev_numero": sheet,
            "cliente": "", "area": "", "x": "", "y": "", "elevacao": ""}

    # ── Extrai colunas de interesse ───────────────────────────────────
    # col 0 = AB/2, col 1 = MN/2, col 4 = K, col 5 = ρa
    dados = raw.iloc[data_start:, [0, 1, 4, 5]].copy()
    dados.columns = ["ab2", "mn2", "K", "rhoa"]

    for col in dados.columns:
        dados[col] = pd.to_numeric(dados[col], errors="coerce")

    valido = (dados["ab2"] > 0) & (dados["mn2"] > 0) & \
             (dados["rhoa"] > 0) & np.isfinite(dados["rhoa"])
    dados = dados[valido].reset_index(drop=True)

    if len(dados) < 3:
        log(f"  Aviso: aba '{sheet}' tem {len(dados)} pontos válidos (mínimo 3) — ignorada.")
        return None

    # Ordena por AB/2 crescente, depois por MN/2 crescente dentro de cada AB/2
    # Os pares de embreagem (ex: AB/2=3 com MN/2=0,25 e MN/2=1) são mantidos
    dados = dados.sort_values(["ab2", "mn2"]).reset_index(drop=True)

    # FIX v1.2: divisão inteira por 2 subestimava pares quando havia mais de 2
    # registros duplicados para o mesmo AB/2. Conta pares únicos corretamente.
    ab2_dup = dados.loc[dados.duplicated(subset=["ab2"], keep=False), "ab2"]
    n_embreagem = ab2_dup.nunique()

    log(f"  ODS aba '{sheet}': SEV {meta['sev_numero']} | "
        f"{len(dados)} pontos | {n_embreagem} pares de embreagem | "
        f"AB/2: {dados['ab2'].min():.1f}–{dados['ab2'].max():.1f} m | "
        f"ρa: {dados['rhoa'].min():.1f}–{dados['rhoa'].max():.1f} Ωm")

    return {
        "ab2":  dados["ab2"].values,
        "mn2":  dados["mn2"].values,
        "rhoa": dados["rhoa"].values,
        "K":    dados["K"].values,
        "meta": meta,
    }


def _ler_sev(arquivo, log):
    """
    Lê um arquivo de SEV nos formatos suportados e retorna lista de SEVs.

      Formato A — Planilha ODS (formato Guapigeo):
        Cada aba é uma SEV independente. Todas as abas válidas são processadas.
        A ρa é lida diretamente da coluna 11 (já calculada pela planilha).
        Metadados extraídos: número, cliente, área, coordenadas, elevação.

      Formato B — TXT simples (2 ou 3 colunas):
        AB/2 (m)   [MN/2 (m)]   ρa (Ωm)
        Linhas começando com # são ignoradas como comentários.

    Retorna: lista de dicts, cada um com chaves 'ab2', 'mn2', 'rhoa', 'meta'.
             Lista vazia em caso de falha total.
    """
    ext = os.path.splitext(arquivo)[1].lower()

    # ── Formato A: ODS (planilha Guapigeo) ───────────────────────────
    if ext == ".ods":
        try:
            xl = pd.ExcelFile(arquivo, engine="odf")
            sevs = []
            for sheet in xl.sheet_names:
                raw = pd.read_excel(arquivo, engine="odf",
                                    sheet_name=sheet, header=None)
                resultado = _ler_sev_aba(raw, sheet, log)
                if resultado is not None:
                    sevs.append(resultado)
            if not sevs:
                log("  ERRO: nenhuma aba com dados válidos encontrada no ODS.")
            else:
                log(f"  ODS: {len(sevs)} SEV(s) encontrada(s).")
            return sevs

        except ImportError:
            log("  ERRO: biblioteca 'odfpy' não instalada.\n"
                "  Execute:  pip install odfpy")
            return []
        except Exception as e:
            log(f"  ERRO ao ler ODS: {e}")
            return []

    # ── Formato B: TXT simples ────────────────────────────────────────
    # Compatível com exportação TXT do IP2Win (tutorial Alva Kurniawan 2009):
    #   AB/2 (m)   MN/2 (m)   ρa (Ωm)   — 3 colunas, sem cabeçalho obrigatório
    # Também aceita 2 colunas (AB/2  ρa), inferindo MN/2 = AB/10.
    else:
        try:
            try:
                df = pd.read_csv(arquivo, sep=r'\s+', header=None,
                                 comment='#', encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(arquivo, sep=r'\s+', header=None,
                                 comment='#', encoding="latin-1")

            # Remove linhas com cabeçalho textual
            df = df[pd.to_numeric(df.iloc[:, 0], errors="coerce").notna()]

            if df.shape[1] >= 3:
                ab2_col = df.iloc[:, 0].astype(float)
                mn2_col = df.iloc[:, 1].astype(float)
                rho_col = df.iloc[:, 2].astype(float)
            elif df.shape[1] == 2:
                log("  Aviso: apenas 2 colunas detectadas — assumindo MN/2 = AB/10 "
                    "(se o arquivo for do IP2Win, verifique se as 3 colunas foram exportadas)")
                ab2_col = df.iloc[:, 0].astype(float)
                mn2_col = ab2_col / 10.0
                rho_col = df.iloc[:, 1].astype(float)
            else:
                log("  ERRO: TXT inválido — precisa de 2 ou 3 colunas.")
                return []

            ab2  = ab2_col.values; mn2 = mn2_col.values; rhoa = rho_col.values
            ok   = (ab2 > 0) & (mn2 > 0) & (rhoa > 0) & np.isfinite(rhoa)
            ab2, mn2, rhoa = ab2[ok], mn2[ok], rhoa[ok]
            nome_sev = os.path.splitext(os.path.basename(arquivo))[0]
            log(f"  TXT: {len(ab2)} pontos | AB/2: {ab2.min():.1f}–{ab2.max():.1f} m")
            return [{"ab2": ab2, "mn2": mn2, "rhoa": rhoa,
                     "meta": {"sev_numero": nome_sev}}]

        except Exception as e:
            log(f"  ERRO ao ler TXT: {e}")
            return []


def _alinhar_embreagem(ab2, mn2, rhoa):
    """
    Alinhamento (emenda) dos segmentos de MN/2 da SEV Schlumberger — v1.6.

    Na operação de "embreagem", um mesmo AB/2 é medido com dois MN/2 (um menor
    e um maior) para manter o ΔV legível ao aprofundar o ensaio. Isso gera
    SALTOS ESTÁTICOS entre os segmentos: a curva deveria ser contínua, mas
    aparece em degraus paralelos (cf. Braga / metodos_geoeletricos: espera-se
    PARALELISMO entre os segmentos). O operador 1D de Schlumberger não modela
    esses degraus, então eles inflam o RMS e distorcem o modelo.

    Correção clássica: tomar o segmento de MENOR MN/2 como referência e deslocar
    multiplicativamente cada segmento seguinte para casar com o anterior nos
    pontos de superposição (mesmo AB/2). O fator é a média geométrica das razões
    ρa_ref/ρa_seg nesses pontos — um deslocamento vertical na escala log-log.

    Retorna rhoa_alinhada (mesma ordem do vetor de entrada) e a lista de fatores.
    """
    ab2 = np.asarray(ab2, float); mn2 = np.asarray(mn2, float)
    rhoa_al = np.asarray(rhoa, float).copy()
    mn_vals = sorted(np.unique(mn2))
    fatores = {}
    if len(mn_vals) <= 1:
        return rhoa_al, fatores
    # segmento de referência: menor MN/2
    ref = mn2 == mn_vals[0]
    ab2_ac = list(ab2[ref]); rho_ac = list(rhoa_al[ref])
    for mv in mn_vals[1:]:
        cur = mn2 == mv
        razoes = []
        for a, r in zip(ab2[cur], rhoa_al[cur]):
            close = np.isclose(np.array(ab2_ac), a, rtol=1e-3)   # mesmo AB/2 já alinhado
            if close.any() and r > 0:
                razoes.append(np.array(rho_ac)[close].mean() / r)
        fator = float(np.exp(np.mean(np.log(razoes)))) if razoes else 1.0
        rhoa_al[cur] *= fator
        fatores[mv] = fator
        ab2_ac += list(ab2[cur]); rho_ac += list(rhoa_al[cur])
    return rhoa_al, fatores


def _inverter_sev_n(ab2, mn2, rhoa, n_camadas, rng, n_tentativas=5):
    """
    Tenta inverter uma SEV com exatamente n_camadas camadas.

    Limites fisicos:
    - Profundidade maxima de investigacao ~ AB/2_max / 4  (regra empirica SEV)
    - h_max por camada limitado a AB/2_max / 2 para evitar solucoes fisicamente
      absurdas (e.g. h=25m para AB/2_max=100m, nao h=300m).
    - Espessura minima ~ MN/2_min / 2 (resolucao do arranjo).
    - Resistividades: 0.1 a 10x o maximo observado (com margem de 10x).

    v1.6: `rng` é um numpy.random.Generator local (reprodutível, sem poluir o
    RNG global). O operador direto é pré-computado UMA vez por sondagem
    (_make_sev_forward) e reutilizado em todas as tentativas — grande ganho
    de velocidade na busca multi-start.
    """
    rho_min   = max(rhoa.min() * 0.1, 0.1)
    rho_max   = rhoa.max() * 10.0
    # Profundidade máxima de investigação: AB/2 / 3 (Schlumberger, regra empírica
    # conservadora — alguns autores usam /3 a /5; /3 é mais generoso e permite
    # que o otimizador explore soluções mais profundas sem excluir a verdade)
    prof_max  = ab2.max() / 3.0
    # Espessura mínima resolúvel (v1.6): uma SEV não resolve camadas mais finas
    # que ~a menor abertura AB/2 (limite físico de resolução). O piso anterior
    # (MN/2_min/2 ≈ 0,12 m) permitia "fatias" de 0,15 m sem significado, gerando
    # sobreajuste de muitas camadas finas na superfície. Usamos AB/2_min/3.
    h_min     = max(ab2.min() / 3.0, mn2.min() / 2.0, 0.1)
    h_max     = prof_max  # limite físico razoável por camada

    # Operador direto pré-computado (matriz de Bessel J1 fixa para este AB/2).
    fwd = _make_sev_forward(ab2, h_min)

    lb = np.concatenate([np.full(n_camadas, np.log(rho_min)),
                         np.full(n_camadas - 1, np.log(h_min))])
    ub = np.concatenate([np.full(n_camadas, np.log(min(rho_max, 1e7))),
                         np.full(n_camadas - 1, np.log(h_max))])

    melhor_rms = 9999.
    melhor_res = None

    # ── Semente guiada pelos dados (1ª tentativa) ─────────────────────
    # Um bom ponto de partida acelera a convergência e evita mínimos locais:
    # a 1ª camada herda a ρa em AB/2 pequeno e a última a ρa em AB/2 grande;
    # camadas intermediárias interpolam a curva ordenada por AB/2; espessuras
    # log-espaçadas cobrindo a profundidade de investigação.
    ordem   = np.argsort(ab2)
    rhoa_s  = rhoa[ordem]
    rho_seed = np.clip(np.geomspace(rhoa_s[0], rhoa_s[-1], n_camadas)
                       if rhoa_s[0] > 0 and rhoa_s[-1] > 0
                       else np.full(n_camadas, np.median(rhoa)),
                       rho_min, min(rho_max, 1e7))
    if n_camadas > 1:
        h_seed = np.geomspace(max(h_min * 2, prof_max * 0.05),
                              prof_max * 0.6, n_camadas - 1)
        h_seed = np.clip(h_seed, h_min, h_max)
    else:
        h_seed = np.array([])

    for tent in range(n_tentativas):
        if tent == 0:
            rho_init, h_init = rho_seed.copy(), h_seed.copy()
        else:
            # Multi-start: perturba a semente (não puro aleatório), o que
            # explora o espaço sem desperdiçar tentativas em regiões absurdas.
            rho_init = rho_seed * np.exp(rng.uniform(-1.0, 1.0, n_camadas))
            rho_init = np.clip(rho_init, rho_min, min(rho_max, 1e7))
            if n_camadas > 1:
                h_init = h_seed * np.exp(rng.uniform(-0.6, 0.6, n_camadas - 1))
                h_init = np.clip(h_init, h_min, h_max)
            else:
                h_init = np.array([])
        x0 = np.concatenate([np.log(rho_init), np.log(h_init)]) if n_camadas > 1 \
             else np.log(rho_init)
        x0 = np.clip(x0, lb, ub)
        try:
            res = least_squares(
                _residuo_sev, x0, bounds=(lb, ub),
                args=(fwd, rhoa, n_camadas),          # v1.6: passa o operador pré-computado
                method="trf", loss="soft_l1", f_scale=0.1,  # robusto a outliers
                max_nfev=4000, ftol=1e-10, xtol=1e-10, gtol=1e-10
            )
            rho_t = np.exp(res.x[:n_camadas])
            h_t   = np.exp(res.x[n_camadas:])
            rc    = fwd(rho_t, h_t)
            rms_t = 100.0 * np.sqrt(np.mean(((rc - rhoa) / (rhoa + 1e-6))**2))
            if rms_t < melhor_rms:
                melhor_rms = rms_t
                melhor_res = (rho_t, h_t, rc)
                if rms_t < 1.5:   # ajuste já excelente: encerra cedo (mais ágil)
                    break
        except Exception:
            pass

    if melhor_res is None:
        return None, None, None, 9999.
    return melhor_res[0], melhor_res[1], melhor_res[2], melhor_rms


def _processar_uma_sev(dados, pasta_saida, n_camadas_hint, nome_base_arq, log, prog, fila_log, n_tentativas_sev, idx, n_total):
    """
    Processa uma SEV individual (dados já lidos). Chamada por processar_sev.
    n_camadas_hint é ignorado — o programa testa de 2 a 8 camadas automaticamente
    e escolhe o modelo com menor RMS log10.
    """
    ab2  = dados["ab2"]
    mn2  = dados["mn2"]
    rhoa = dados["rhoa"]
    meta = dados["meta"]

    sev_id      = meta.get("sev_numero", nome_base_arq)

    # Reprodutibilidade por arquivo (v1.6): hash() de str é aleatorizado por
    # processo (PYTHONHASHSEED), então o método antigo NÃO era reprodutível
    # entre execuções. Usa hashlib.md5 (estável) + Generator local (não
    # polui o RNG global do numpy). Cada SEV tem semente própria e estável.
    _seed = int.from_bytes(hashlib.md5(str(sev_id).encode("utf-8")).digest()[:4], "big")
    rng = np.random.default_rng(_seed)
    titulo_base = f"SEV {sev_id}"
    if meta.get("cliente"): titulo_base += f"  —  {meta['cliente']}"
    if meta.get("area"):    titulo_base += f"  |  {meta['area']}"
    coords_txt = ""
    if meta.get("x") or meta.get("y"):
        coords_txt = f"X={meta.get('x','?')}  Y={meta.get('y','?')}"
        if meta.get("elevacao"): coords_txt += f"  Elev.={meta['elevacao']}m"

    # Nome de saída limpo (v1.6): evita espaços e duplicação "SEV_SEVSEV 01".
    # Higieniza o id (espaços→_) e só prefixa "SEV" se ainda não começar por ele.
    _sid = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(sev_id)).strip("_")
    _rotulo = _sid if _sid.lower().startswith("sev") else f"SEV{_sid}"
    saida = os.path.join(pasta_saida, f"{nome_base_arq}_{_rotulo}")

    prog(10 + int(70 * (idx / n_total)), f"SEV {sev_id} — curva observada…")

    # ── Curva observada ───────────────────────────────────────────────
    CORES_MN   = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                  "#9467bd", "#8c564b", "#e377c2"]
    MARCADORES = ["o", "s", "^", "D", "v", "P", "*"]

    mn2_unicos = sorted(np.unique(mn2))

    fig_obs, ax_obs = plt.subplots(figsize=(9, 5.5))
    for i, mn_val in enumerate(mn2_unicos):
        mask = mn2 == mn_val
        cor = CORES_MN[i % len(CORES_MN)]
        mk  = MARCADORES[i % len(MARCADORES)]
        ax_obs.loglog(ab2[mask], rhoa[mask],
                      marker=mk, color=cor, linestyle="-",
                      markersize=7, lw=1.4,
                      label=f"MN/2 = {mn_val} m")
    # Grade de décadas (padrão IP2Win)
    ax_obs.grid(True, which="major", ls="-",  lw=0.5, alpha=0.5, color="#999")
    ax_obs.grid(True, which="minor", ls="--", lw=0.3, alpha=0.3, color="#bbb")
    ax_obs.set_xlabel("AB/2 (m)", fontsize=11)
    ax_obs.set_ylabel("ρa (Ωm)", fontsize=11)
    ax_obs.set_title(
        f"{titulo_base}\nCurva ρa vs AB/2  —  {len(ab2)} pontos  |  "
        f"{len(mn2_unicos)} segmento(s) MN/2  |  Arranjo Schlumberger", fontsize=10)
    if coords_txt:
        ax_obs.text(0.01, 0.01, coords_txt, transform=ax_obs.transAxes,
                    fontsize=7.5, va="bottom", color="#444")
    ax_obs.legend(fontsize=9, loc="best", framealpha=0.9)
    plt.tight_layout()
    plt.savefig(saida + "_curva_obs.png", dpi=150, bbox_inches="tight")
    plt.close()

    # ── Alinhamento de embreagem (emenda dos segmentos de MN/2) — v1.6 ──
    # A curva observada acima preserva os segmentos crus (mostra o degrau).
    # A partir daqui a inversão e o ajuste usam a curva ALINHADA (contínua):
    # cada segmento de MN/2 é deslocado p/ casar com o anterior na superposição.
    rhoa_crua = rhoa
    rhoa, _fat_emb = _alinhar_embreagem(ab2, mn2, rhoa)
    if _fat_emb:
        _fs = "  ".join(f"MN/2={k:g}m→×{v:.3f}" for k, v in _fat_emb.items())
        log(f"  SEV {sev_id} — embreagem alinhada: {_fs}")

    # ── Busca automática do número de camadas ─────────────────────────
    # Critério: menor RMS no espaço log10.
    # Testa n=2..8; limita ao máximo de n_pts//3 camadas para evitar
    # sobredeterminação (pelo menos 3 pontos por camada em média).
    n_pts     = len(ab2)
    n_max     = min(8, max(2, n_pts // 3))
    candidatos = range(2, n_max + 1)

    log(f"  SEV {sev_id} — buscando número ótimo de camadas (2–{n_max})…")

    melhor_n     = 2
    melhor_score = np.inf   # menor AIC = melhor
    melhor_rms   = 9999.
    melhor_rho   = None
    melhor_h     = None
    melhor_calc  = None
    rms_por_n    = {}

    n_cand = len(list(candidatos))
    for ci, nc in enumerate(candidatos):
        prog_val = 15 + int(70 * (idx / n_total)) + int(60 * ci / n_cand)
        prog(min(prog_val, 85), f"SEV {sev_id} — testando {nc} camadas ({ci+1}/{n_cand})…")
        rho_t, h_t, rc_t, rms_t = _inverter_sev_n(ab2, mn2, rhoa, nc, rng, n_tentativas=n_tentativas_sev)
        rms_por_n[nc] = rms_t
        # Critério AIC (Akaike) em escala log: penaliza modelos com mais parâmetros
        # n_params = nc (resistividades) + (nc-1) (espessuras) = 2*nc - 1
        # AIC ≈ n_pts * ln(rms²) + 2 * n_params
        n_params = 2 * nc - 1
        if rms_t < 9000. and rc_t is not None:
            sse = np.sum((np.log(rc_t + 1e-6) - np.log(rhoa + 1e-6))**2)
            aic = n_pts * np.log(sse / n_pts + 1e-30) + 2.0 * n_params
        else:
            aic = np.inf
        log(f"    n={nc}: RMS={rms_t:.2f}%  AIC={aic:.1f}")
        if aic < melhor_score:
            melhor_score = aic
            melhor_rms   = rms_t
            melhor_n     = nc
            melhor_rho   = rho_t
            melhor_h     = h_t
            melhor_calc  = rc_t

    log(f"  SEV {sev_id} — modelo selecionado: {melhor_n} camadas  "
        f"(RMS={melhor_rms:.2f}%)")
    log(f"  Tabela de RMS: " +
        "  ".join(f"n={k}→{v:.2f}%" for k, v in rms_por_n.items()))

    n_camadas = melhor_n
    rho_inv   = melhor_rho
    h_inv     = melhor_h
    rhoa_calc = melhor_calc
    rms_sev   = melhor_rms
    ok_inv    = (rho_inv is not None)

    if not ok_inv:
        log(f"  ✓ SEV {sev_id} — apenas curva observada salva."); return

    # Elevação do topo (usada na tabela/figura). v1.6: a montagem do CSV do
    # modelo foi REMOVIDA (loop camadas_out morto) — não geramos mais CSV.
    elevacao = float(meta.get("elevacao") or 0.0)

    # ── Figura: curva ajustada + modelo em escada (estilo IPI2Win) ──────
    CORES_MN2   = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    MARCADORES2 = ["o", "s", "^", "D", "v"]

    # ── Layout: 2 gráficos em cima + tabela embaixo ──────────────────
    fig_res = plt.figure(figsize=(14, 9.5))
    fig_res.patch.set_facecolor("white")

    gs_r = gridspec.GridSpec(
        2, 2,
        height_ratios=[3.2, 1.1],
        hspace=0.50, wspace=0.33,
        left=0.06, right=0.97,
        top=0.92, bottom=0.04,
    )
    ax_c = fig_res.add_subplot(gs_r[0, 0])
    ax_m = fig_res.add_subplot(gs_r[0, 1])
    ax_t = fig_res.add_subplot(gs_r[1, :])
    ax_t.axis("off")

    # ── Curva calculada densa (vermelha) ───────────────────────────────
    # Como o operador Schlumberger não depende de MN/2, uma única curva densa
    # cobre todo o intervalo de AB/2 — contínua e sem artefatos de emenda
    # entre segmentos (a versão anterior calculava trechos por MN/2, o que era
    # redundante agora que o operador direto está fisicamente correto).
    ab2_dense  = np.geomspace(ab2.min() * 0.9, ab2.max() * 1.1, 400)
    rhoa_dense = _rhoa_schlumberger_modelo(ab2_dense, rho_inv, h_inv)  # v1.6: sem MN/2
    ax_c.loglog(ab2_dense, rhoa_dense, "r-", lw=2.0, zorder=4,
                label=f"Calculado  (RMS={rms_sev:.1f}%)")

    # ── Pontos observados coloridos por MN/2 ──────────────────────────
    for i, mn_val in enumerate(sorted(np.unique(mn2))):
        mask = mn2 == mn_val
        cor = CORES_MN2[i % len(CORES_MN2)]
        mk  = MARCADORES2[i % len(MARCADORES2)]
        ax_c.loglog(ab2[mask], rhoa[mask],
                    marker=mk, color=cor, linestyle="none",
                    markersize=7, zorder=5,
                    markeredgecolor="white", markeredgewidth=0.4,
                    label=f"MN/2={mn_val}m")

    ax_c.set_xlabel("AB/2 (m)", fontsize=11)
    ax_c.set_ylabel("ρa (Ωm)", fontsize=11)
    ax_c.set_title("Ajuste da curva SEV", fontsize=11, pad=6)
    ax_c.grid(True, which="major", ls="-",  lw=0.5, alpha=0.4, color="#888")
    ax_c.grid(True, which="minor", ls="--", lw=0.3, alpha=0.25, color="#bbb")
    ax_c.legend(fontsize=8.5, framealpha=0.9, loc="best")
    ax_c.tick_params(axis="both", which="both", labelsize=9)

    # ── Modelo em escada (painel direito) ─────────────────────────────
    prof_max_plot = sum(h_inv) + ab2.max() * 0.25
    rho_esc = []; z_esc = []; z = 0.0
    for i in range(n_camadas):
        if i < len(h_inv):
            esp_i = h_inv[i]
            rho_esc += [rho_inv[i], rho_inv[i]]
            z_esc   += [z, z + esp_i]
            z += esp_i
        else:
            rho_esc += [rho_inv[i], rho_inv[i]]
            z_esc   += [z, prof_max_plot]
    ax_m.semilogx(rho_esc, z_esc, "b-", lw=2.5, solid_capstyle="butt")

    z_bounds = [0.0] + list(np.cumsum(h_inv))
    for zb in z_bounds[1:]:
        ax_m.axhline(zb, color="#bbbbcc", lw=0.7, ls="--", zorder=1)

    rho_min_p = min(rho_inv) * 0.4
    rho_max_p = max(rho_inv) * 4.0
    ax_m.set_xlim(rho_min_p, rho_max_p)
    ax_m.set_ylim(prof_max_plot, -prof_max_plot * 0.03)
    ax_m.set_xlabel("Resistividade (Ωm)", fontsize=11)
    if elevacao != 0.0:
        ax_m.set_ylabel(f"Profundidade (m)  [ref. {elevacao:.1f}m]", fontsize=10)
    else:
        ax_m.set_ylabel("Profundidade (m)", fontsize=11)
    ax_m.set_title("Modelo 1D invertido", fontsize=11, pad=6)
    ax_m.grid(True, which="major", ls="-",  lw=0.4, alpha=0.35, color="#888")
    ax_m.grid(True, which="minor", ls="--", lw=0.25, alpha=0.2,  color="#bbb")
    ax_m.tick_params(axis="both", which="both", labelsize=9)

    # Labels de resistividade por camada (estilo IPI2Win)
    z_labels2 = [0.0] + list(np.cumsum(h_inv))
    for i in range(n_camadas):
        z_top = z_labels2[i]
        z_bot = z_labels2[i + 1] if i < len(h_inv) else prof_max_plot
        z_mid = (z_top + z_bot) / 2.0
        ax_m.text(rho_max_p * 0.88, z_mid,
                  f"C{i+1}: {rho_inv[i]:.0f} Ωm",
                  fontsize=8.5, va="center", ha="right",
                  color="#0055aa", fontweight="bold",
                  bbox=dict(facecolor="white", edgecolor="none",
                            alpha=0.75, pad=1.5))

    # ── Tabela de resultados com bordas visíveis ───────────────────────
    col_hdrs_t = ["Camada", "ρ (Ωm)", "Espessura (m)", "Prof. topo (m)",
                  "Prof. base (m)", "Altitude (m)"]
    table_rows = []
    z_acc = 0.0
    for i in range(n_camadas):
        esp_i  = h_inv[i] if i < len(h_inv) else float("nan")
        d_base = z_acc + esp_i if not np.isnan(esp_i) else float("nan")
        alt_i  = elevacao - z_acc if elevacao != 0.0 else -z_acc
        table_rows.append([
            str(i + 1),
            f"{rho_inv[i]:.1f}",
            f"{esp_i:.3f}" if not np.isnan(esp_i) else "∞",
            f"{z_acc:.3f}",
            f"{d_base:.3f}" if not np.isnan(d_base) else "–",
            f"{alt_i:.2f}",
        ])
        if not np.isnan(esp_i):
            z_acc += esp_i

    tbl = ax_t.table(
        cellText=table_rows,
        colLabels=col_hdrs_t,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.55)

    # Estilo: cabeçalho azul escuro
    for j in range(len(col_hdrs_t)):
        cell = tbl[(0, j)]
        cell.set_facecolor("#1a4a7a")
        cell.set_edgecolor("#ffffff")
        cell.get_text().set_color("white")
        cell.get_text().set_fontweight("bold")
    # Linhas alternadas + bordas visíveis
    for row_i in range(1, len(table_rows) + 1):
        bg = "#dce8f5" if row_i % 2 == 0 else "#f4f8ff"
        for col_j in range(len(col_hdrs_t)):
            c = tbl[(row_i, col_j)]
            c.set_facecolor(bg)
            c.set_edgecolor("#8899bb")

    ax_t.set_title(
        f"Tabela do Modelo 1D Invertido   |   RMS = {rms_sev:.1f}%",
        fontsize=10, pad=6, loc="left", color="#1a4a7a", fontweight="bold",
    )

    plt.suptitle(f"{titulo_base}  ({n_camadas} camadas — seleção automática)",
                 fontsize=12, y=0.99)
    if coords_txt:
        fig_res.text(0.5, 0.005, coords_txt, ha="center",
                     fontsize=8, color="#444", transform=fig_res.transFigure)
    plt.savefig(saida + "_resultado.png", dpi=150, bbox_inches="tight")
    plt.close()

    log(f"  SEV {sev_id} → {saida}_resultado.png")
    # ── Resumo para painel de Configuração ──────────────────────────────
    fila_log.put(("resumo_sev", {
        "arquivo":    nome_base_arq,
        "sev_id":     sev_id,
        "rms":        rms_sev,
        "n_camadas":  n_camadas,
        "rho":        rho_inv.tolist() if rho_inv is not None else [],
    }))
    log(f"  ✓ SEV {sev_id} finalizada  RMS={rms_sev:.2f}%  ({n_camadas} camadas)")


def processar_sev(arquivo, pasta_saida, params, fila_log, fila_prog):
    """
    Pipeline de inversão 1D para SEV Schlumberger.
    Aceita ODS (formato Guapigeo — todas as abas) e TXT simples.
    Um ODS com N abas gera N saídas independentes.
    O número de camadas é determinado automaticamente (busca de 2 a 8).
    """
    def log(msg):   fila_log.put(("log", msg))
    def prog(v, t): fila_prog.put((v, t))

    nome_base = os.path.splitext(os.path.basename(arquivo))[0]
    log(f"\n{'═'*60}")
    log(f"  Processando SEV: {os.path.basename(arquivo)}")
    log(f"{'═'*60}")

    prog(5, "Lendo arquivo SEV…")
    lista_sevs = _ler_sev(arquivo, log)
    if not lista_sevs:
        prog(100, "SEV — leitura falhou.")
        return

    n_total = len(lista_sevs)
    log(f"  {n_total} SEV(s) a processar…")
    for idx, dados in enumerate(lista_sevs, 1):
        try:
            _processar_uma_sev(dados, pasta_saida, None, nome_base,
                               log, prog, fila_log,
                               params.get("n_tent_sev", 6), idx, n_total)
        except Exception as e:
            import traceback
            log(f"  ERRO inesperado na SEV {idx}: {e}")
            log(traceback.format_exc())

    prog(100, f"SEV concluída — {n_total} sondagem(ns).")
    log(f"  ✓ Arquivo {os.path.basename(arquivo)}: {n_total} SEV(s) processada(s).")


# ══════════════════════════════════════════════════════════════════════
# v2.0 — INTERFACE PYSIDE6 (design §4: sidebar com fluxo guiado)
# ══════════════════════════════════════════════════════════════════════

# v2.0: direções de linha disponíveis (§4.2)
DIRECOES_LINHA = ["Nenhuma", "W → E", "E → W", "N → S", "S → N"]

# v2.0 (§5.1): catálogo de litotipos por classe (faixas de ρ entram na Fase C)
LITOTIPOS_POR_CLASSE = {
    "Sedimentar":  ["Sedimentos inconsolidados (areia/cascalho)", "Argila / argilito",
                    "Arenito", "Calcário / dolomito", "Folhelho"],
    "Metamórfica": ["Gnaisse", "Xisto", "Quartzito", "Mármore", "Filito / ardósia"],
    "Ígnea":       ["Granito", "Basalto / diabásio", "Gabro", "Riolito"],
    "Não sei / mista": [],
}
OBJETIVOS_ESTUDO = [
    ("topo_rochoso",   "Topo rochoso / rocha sã"),
    ("estruturas",     "Estruturas (fraturas, diques)"),
    ("nivel_dagua",    "Nível d'água"),
    ("intrusao_salina","Intrusão salina"),
    ("espessura_solo", "Espessura de solo"),
]


# ══════════════════════════════════════════════════════════════════════
# v2.0 — ADAPTADOR FILA→SINAL E WORKER QThread (§4.2)
# ══════════════════════════════════════════════════════════════════════

class FilaSinal:
    """v2.0 (§4.2): adaptador fila→sinal Qt. O núcleo continua chamando
    .put() como no v1.x; o sinal atravessa para a thread de UI com
    conexão enfileirada (thread-safe). Nenhuma assinatura do núcleo muda."""
    def __init__(self, sinal):
        self._sinal = sinal
    def put(self, item):
        self._sinal.emit(item)


class WorkerProcessamento(QThread):
    """v2.0: substitui threading.Thread+queue+after(150) do v1.x.
    Corpo equivalente ao _thread_proc do Tkinter antigo."""
    item_log  = Signal(object)   # itens da antiga fila_log: (tipo, valor)
    item_prog = Signal(object)   # itens da antiga fila_prog: (pct, txt)

    def __init__(self, arquivos, pasta_saida, params, geo_info, direcoes,
                 modo_ert=True, coordenadas=None,
                 geo_struct=None, gerar_interpretacao=False):
        super().__init__()
        self.arquivos, self.pasta_saida = arquivos, pasta_saida
        self.params, self.geo_info, self.direcoes = params, geo_info, direcoes
        self.modo_ert = modo_ert
        self.coordenadas = coordenadas or {}   # v2.0 (§9): {arquivo: (E0, N0, az)}
        self.geo_struct = geo_struct            # v2.0 (§7): dict estruturado de geologia
        self.gerar_interpretacao = gerar_interpretacao  # v2.0 (§7): figura de interpretação
        self.rodando = True

    def run(self):
        fila_log, fila_prog = FilaSinal(self.item_log), FilaSinal(self.item_prog)
        EXT_SEV = {".ods", ".xlsx", ".xls"}
        coletor_ert = []
        t_inicio = time.time(); n = len(self.arquivos)
        for i, arq in enumerate(self.arquivos):
            if not self.rodando: break
            ext = os.path.splitext(arq)[1].lower()
            usar_sev = (ext in EXT_SEV) or (not self.modo_ert)
            fila_log.put(("arq", f"[{i+1}/{n}]  {os.path.basename(arq)}  "
                                 f"[{'SEV' if usar_sev else 'ERT'}]"))
            # v2.0: mensagem de .ods detectado emitida APÓS o cabeçalho do
            # arquivo, dentro do ramo SEV — igual ao _thread_proc do v1.x.
            try:
                if usar_sev:
                    if ext in EXT_SEV and self.modo_ert:
                        fila_log.put(("log",
                            f"  Arquivo {ext} detectado — processando como SEV automaticamente."))
                    processar_sev(arq, self.pasta_saida, self.params,
                                  fila_log, fila_prog)
                else:
                    processar_arquivo(arq, self.pasta_saida, self.params,
                                      self.geo_info, fila_log, fila_prog,
                                      direcao=self.direcoes.get(arq, "Nenhuma"),
                                      coletor_render=coletor_ert)
            except Exception as e:
                import traceback
                fila_log.put(("log", f"  ERRO em {os.path.basename(arq)}: {e}"))
                fila_log.put(("log", traceback.format_exc()))
            pct = int((i + 1) / n * 100)
            eta = (time.time() - t_inicio) / (i + 1) * (n - i - 1)
            fila_log.put(("geral", (pct, f"Arquivo {i+1}/{n} concluído  |  "
                                         f"ETA: {formatar_eta(eta)}")))
        # paleta de cores compartilhada entre os perfis do lote (igual ao v1.8)
        if self.rodando and coletor_ert:
            vals = np.concatenate([np.asarray(p["mod_arr"], float).ravel()
                                   for p in coletor_ert])
            lev = _faixas_resistividade(vals)
            if len(coletor_ert) > 1:
                fila_log.put(("log", f"\n  {len(coletor_ert)} figuras com paleta "
                                     f"compartilhada ({lev[0]:.0f}–{lev[-1]:.0f} Ωm)."))
            dados3d = []   # v2.0 (§9): (nome, ex, ez, rho_por_célula, extra)
            # v2.0 (§7): interpretação geológica opcional (aprovada; off por padrão)
            interp = None
            if self.gerar_interpretacao and self.geo_struct and \
               any(l in FAIXAS_RHO_PALACKY for l in self.geo_struct.get("litotipos", [])):
                interp = {"geo": self.geo_struct,
                          "deriv": _derivar_params_geologia(self.geo_struct)}
            for p in coletor_ert:
                extra = p.pop("extra3d", None)
                if extra is not None:
                    dados3d.append((p["nome_base"], p["ex"], p["ez"],
                                    np.asarray(p["mod_arr"], float), extra))
                try:
                    _gerar_resultados_ert(lev_fixo=lev, interpretacao=interp, **p)
                except Exception as e:
                    fila_log.put(("log", f"  ERRO na figura de "
                                         f"{p.get('nome_base', '?')}: {e}"))
            # v2.0.1 (§9): consolidação 3D extraída p/ função testável que
            # AVISA quando o 3D é pulado por falta de coordenadas
            _consolidar_exportacao_3d(dados3d, self.coordenadas, self.pasta_saida,
                                      lambda m: fila_log.put(("log", m)))
        fila_log.put(("fim", None))


class PaginaConfig(QWidget):
    """Passo 2: modo de busca, qualidade (avançado), modelo estendido,
    exagero vertical, direção padrão e SEV. Mapeamento 1:1 com o v1.x (§4.2)."""
    MODOS = [
        ("rapido",   "⚡  Rápido",   "λ=80 | L1 | 2 inversões/arquivo"),
        ("padrao",   "🔧  Padrão (recomendado)", "λ=[30,80,150] | L1+L2 | 12 inversões"),
        ("rigoroso", "🎯  Rigoroso", "λ=[10..300] | L1+L2 | tol=[0.01..0.10] | 60 inversões"),
    ]
    _GRIDS = {
        "rapido":   {"lam": [80], "robust": [True], "tol": [0.05]},
        "padrao":   {"lam": [30, 80, 150], "robust": [True, False], "tol": [0.05]},
        "rigoroso": {"lam": [10, 30, 80, 150, 300], "robust": [True, False],
                     "tol": [0.01, 0.05, 0.10]},
    }

    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 14)

        g_modo = QGroupBox("Modo de busca — ERT")
        vm = QVBoxLayout(g_modo)
        self.grupo_modo = QButtonGroup(self)
        for val, rotulo, desc in self.MODOS:
            h = QHBoxLayout()
            rb = QRadioButton(rotulo); rb.setProperty("valor", val)
            if val == "padrao": rb.setChecked(True)
            self.grupo_modo.addButton(rb)
            lab = QLabel(desc); lab.setProperty("mutado", True)
            h.addWidget(rb); h.addWidget(lab); h.addStretch()
            vm.addLayout(h)
        lay.addWidget(g_modo)

        g_av = QGroupBox("Avançado — limites de qualidade")
        g_av.setCheckable(True); g_av.setChecked(False)   # recolhido por padrão
        fa = QFormLayout(g_av)
        self.sp_rhoa_max = QSpinBox(); self.sp_rhoa_max.setRange(1000, 500000)
        self.sp_rhoa_max.setSingleStep(5000); self.sp_rhoa_max.setValue(100000)
        self.sp_nrig = QSpinBox(); self.sp_nrig.setRange(1, 8); self.sp_nrig.setValue(4)
        self.sp_iter = QSpinBox(); self.sp_iter.setRange(5, 30); self.sp_iter.setValue(15)
        self.sp_erro = QDoubleSpinBox(); self.sp_erro.setRange(0.01, 0.20)
        self.sp_erro.setSingleStep(0.01); self.sp_erro.setValue(0.05)
        fa.addRow("ρa máximo absoluto (Ωm):", self.sp_rhoa_max)
        fa.addRow("Nível n de IQR rigoroso:", self.sp_nrig)
        fa.addRow("Máx. iterações de inversão:", self.sp_iter)
        fa.addRow("Erro relativo estimado:", self.sp_erro)
        lay.addWidget(g_av)

        g_ext = QGroupBox("Modelo estendido (RES2DINV 'Extended model', Loke §3.3)")
        he = QHBoxLayout(g_ext)
        self.ck_ext = QCheckBox("Usar modelo estendido")
        self.sp_ext = QDoubleSpinBox(); self.sp_ext.setRange(0.05, 0.50)
        self.sp_ext.setSingleStep(0.05); self.sp_ext.setValue(0.20)
        self.sp_ext.setEnabled(False)
        self.ck_ext.toggled.connect(self.sp_ext.setEnabled)
        he.addWidget(self.ck_ext); he.addWidget(QLabel("Fator lateral:"))
        he.addWidget(self.sp_ext); he.addStretch()
        lay.addWidget(g_ext)

        g_fig = QGroupBox("Figura de resultado")
        hf = QHBoxLayout(g_fig)
        self.cb_ve = QComboBox(); self.cb_ve.addItems(
            ["Automático", "1×", "2×", "3×", "4×", "6×"])
        self.cb_direcao = QComboBox(); self.cb_direcao.addItems(DIRECOES_LINHA)
        hf.addWidget(QLabel("Exagero vertical:")); hf.addWidget(self.cb_ve)
        hf.addSpacing(24)
        hf.addWidget(QLabel("Direção padrão da linha:")); hf.addWidget(self.cb_direcao)
        hf.addStretch()
        lay.addWidget(g_fig)

        g_sev = QGroupBox("SEV — Sondagem Elétrica Vertical")
        hs = QHBoxLayout(g_sev)
        self.sp_tent = QSpinBox(); self.sp_tent.setRange(3, 20); self.sp_tent.setValue(6)
        hs.addWidget(QLabel("Tentativas de inversão por nº de camadas:"))
        hs.addWidget(self.sp_tent); hs.addStretch()
        lay.addWidget(g_sev)
        lay.addStretch()

    def modo_busca(self):
        for b in self.grupo_modo.buttons():
            if b.isChecked(): return b.property("valor")
        return "padrao"

    def coletar_params(self, geo=None):
        """v2.0: equivalente ao _montar_params do v1.x + derivação geológica (§5.2)."""
        modo = self.modo_busca()
        grid = dict(self._GRIDS[modo])
        deriv = _derivar_params_geologia(geo)
        if modo != "rigoroso" and deriv["norma"] == "L1":
            grid["robust"] = [True]
        elif modo != "rigoroso" and deriv["norma"] == "L2":
            grid["robust"] = [False]
        ve = self.cb_ve.currentText()
        return {
            **grid,
            "margem_prof": [1.0, 1.1], "iqr_raso": [1.5, 2.0, 2.5],
            "iqr_prof": [1.0, 1.5], "fviz": [3.0, 5.0],
            "limiar_pos": [50.0, 75.0],
            "max_iter": self.sp_iter.value(), "erro_rel": self.sp_erro.value(),
            "n_nivel_rigoroso": self.sp_nrig.value(),
            "rhoa_max": self.sp_rhoa_max.value(),
            "extended_model": self.ck_ext.isChecked(),
            "ext_factor": self.sp_ext.value(),
            "n_tent_sev": self.sp_tent.value(),
            "ve_exagero": "auto" if ve.startswith("Auto") else int(ve.rstrip("×x")),
            "direcao_linha": self.cb_direcao.currentText(),
            # v2.0 (§5.2): parâmetros derivados da geologia estruturada
            "zweight": deriv["zweight"],
            "faixa_rho_geo": deriv["faixa_rho"],
            "salina_esperada": deriv["salina"],
            "notas_geo": deriv["notas"],
        }


class PaginaGeologia(QWidget):
    """Passo 3: geologia estruturada (§5.1) + texto livre complementar."""
    def __init__(self, janela):
        super().__init__()
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 14)
        intro = QLabel("Opcional — mas se preenchido, orienta a inversão "
                       "(norma L1/L2, suavização, controle de qualidade).")
        intro.setProperty("mutado", True); lay.addWidget(intro)

        g_rocha = QGroupBox("Rochas da área")
        fr = QFormLayout(g_rocha)
        self.cb_classe = QComboBox()
        self.cb_classe.addItems(list(LITOTIPOS_POR_CLASSE.keys()))
        self.cb_classe.setCurrentText("Não sei / mista")
        self.cb_classe.currentTextChanged.connect(self._litotipos_da_classe)
        self.ls_lito = QListWidget()
        self.ls_lito.setSelectionMode(QAbstractItemView.MultiSelection)
        self.ls_lito.setMaximumHeight(110)
        fr.addRow("Classe dominante:", self.cb_classe)
        fr.addRow("Litotipos (multi):", self.ls_lito)
        lay.addWidget(g_rocha)

        g_sup = QGroupBox("Superfície e água")
        vs = QVBoxLayout(g_sup)
        hsup = QHBoxLayout()
        self.rb_solo  = QRadioButton("Predomínio de solo")
        self.rb_misto = QRadioButton("Misto"); self.rb_misto.setChecked(True)
        self.rb_rocha = QRadioButton("Muita rocha exposta")
        for rb in (self.rb_solo, self.rb_misto, self.rb_rocha): hsup.addWidget(rb)
        hsup.addStretch(); vs.addLayout(hsup)
        self.ck_agua = QCheckBox("Lençol freático raso esperado")
        self.ck_sal  = QCheckBox("Possível água salina / salobra")
        vs.addWidget(self.ck_agua); vs.addWidget(self.ck_sal)
        lay.addWidget(g_sup)

        g_obj = QGroupBox("Objetivo do estudo (multi)")
        vo = QVBoxLayout(g_obj)
        self.cks_obj = {}
        for chave, rotulo in OBJETIVOS_ESTUDO:
            ck = QCheckBox(rotulo); self.cks_obj[chave] = ck; vo.addWidget(ck)
        lay.addWidget(g_obj)

        # v2.0 (§7): figura de interpretação — APROVADA pelo usuário em
        # 2026-06-12; nasce DESLIGADA por padrão.
        self.ck_interpretacao = QCheckBox(
            "Gerar figura de interpretação geológica (zonas litológicas "
            "pelo cruzamento ρ × Palacky — requer litotipos selecionados)")
        self.ck_interpretacao.setChecked(False)
        lay.addWidget(self.ck_interpretacao)

        g_txt = QGroupBox("Descrição geológica complementar (texto livre)")
        vt = QVBoxLayout(g_txt)
        self.txt_livre = QTextEdit(); self.txt_livre.setMaximumHeight(90)
        vt.addWidget(self.txt_livre)
        lay.addWidget(g_txt)
        lay.addStretch()
        self._litotipos_da_classe(self.cb_classe.currentText())

    def _litotipos_da_classe(self, classe):
        self.ls_lito.clear()
        self.ls_lito.addItems(LITOTIPOS_POR_CLASSE.get(classe, []))

    def coletar(self):
        """Dict estruturado consumido por _derivar_params_geologia (§5.2)."""
        superficie = ("solo" if self.rb_solo.isChecked()
                      else "rocha" if self.rb_rocha.isChecked() else "misto")
        return {
            "classe": self.cb_classe.currentText(),
            "litotipos": [i.text() for i in self.ls_lito.selectedItems()],
            "superficie": superficie,
            "agua_rasa": self.ck_agua.isChecked(),
            "salina": self.ck_sal.isChecked(),
            "objetivos": [k for k, ck in self.cks_obj.items() if ck.isChecked()],
            "texto": self.txt_livre.toPlainText().strip(),
        }

    def geo_info_texto(self):
        """String p/ o pipeline (compatível com o geo_info do v1.x)."""
        g = self.coletar()
        partes = []
        if g["litotipos"]:
            partes.append(f"{g['classe']}: " + ", ".join(g["litotipos"]) + ".")
        if g["agua_rasa"]: partes.append("Lençol freático raso esperado.")
        if g["salina"]:    partes.append("Possível água salina/salobra.")
        if g["texto"]:     partes.append(g["texto"])
        return "  ".join(partes)


class PaginaDados(QWidget):
    """Passo 1: modo, arquivos de entrada (com direção POR ARQUIVO) e saída."""
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.arquivos = []          # caminhos na ordem de inclusão
        self.direcoes = {}          # {caminho: direção}
        self.coordenadas = {}       # {caminho: (E0, N0, azimute)} — preenchido na fase D
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 14)

        g_modo = QGroupBox("Modo de processamento")
        h = QHBoxLayout(g_modo)
        self.rb_ert = QRadioButton("ERT — Caminhamento Elétrico")
        self.rb_sev = QRadioButton("SEV — Sondagem Elétrica Vertical")
        self.rb_ert.setChecked(True)
        h.addWidget(self.rb_ert); h.addWidget(self.rb_sev); h.addStretch()
        lay.addWidget(g_modo)

        g_arq = QGroupBox("Arquivos de entrada (.txt / .dat / .ods / .xlsx)")
        v = QVBoxLayout(g_arq)
        hb = QHBoxLayout()
        b_add = QPushButton("Adicionar arquivos"); b_add.clicked.connect(self._add_arquivos)
        b_dir = QPushButton("Adicionar pasta"); b_dir.setProperty("secundario", True)
        b_dir.clicked.connect(self._add_pasta)
        b_clr = QPushButton("Limpar lista"); b_clr.setProperty("perigo", True)
        b_clr.clicked.connect(self._limpar)
        hb.addWidget(b_add); hb.addWidget(b_dir); hb.addWidget(b_clr); hb.addStretch()
        v.addLayout(hb)
        dica = QLabel("Clique com o botão direito (ou duplo-clique) em um arquivo para "
                      "definir a DIREÇÃO e as COORDENADAS da linha (E, N, azimute). "
                      "Com 2+ linhas com coordenadas, o programa gera o 3D (CSV/VTK) "
                      "e os mapas de níveis.")
        dica.setProperty("mutado", True); v.addWidget(dica)
        self.lista = QListWidget()
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(
            lambda pos: self._menu_arquivo(self.lista.itemAt(pos)))
        self.lista.itemDoubleClicked.connect(self._menu_arquivo)
        v.addWidget(self.lista, 1)
        lay.addWidget(g_arq, 1)

        g_out = QGroupBox("Pasta de saída dos resultados")
        ho = QHBoxLayout(g_out)
        self.ed_saida = QLineEdit(os.path.expanduser("~/ERT_Resultados"))
        b_out = QPushButton("Escolher…"); b_out.setProperty("secundario", True)
        b_out.clicked.connect(self._escolher_saida)
        ho.addWidget(self.ed_saida, 1); ho.addWidget(b_out)
        lay.addWidget(g_out)

    # ── arquivos ──────────────────────────────────────────────────────
    def _direcao_padrao(self):
        """Direção padrão definida na página Configuração (combo criado na
        task seguinte); até lá, 'Nenhuma'."""
        cb = getattr(self.janela.pag_config, "cb_direcao", None)
        return cb.currentText() if cb is not None else "Nenhuma"

    def _rotulo(self, f):
        d = self.direcoes.get(f, "Nenhuma")
        extra = "" if d == "Nenhuma" else f"   [{d}]"
        # v2.0.1: coordenadas visíveis na lista (antes ficavam invisíveis e o
        # usuário não sabia se o 3D iria sair)
        c = self.coordenadas.get(f)
        tag_c = f"   [E={c[0]:g}  N={c[1]:g}  az={c[2]:g}°]" if c else ""
        return f"{os.path.basename(f)}{extra}{tag_c}    —  {os.path.dirname(f)}"

    def _refresh(self):
        self.lista.clear()
        for f in self.arquivos:
            it = QListWidgetItem(self._rotulo(f))
            it.setData(Qt.UserRole, f)
            self.lista.addItem(it)

    def _add_arquivos(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Selecionar arquivos de entrada", "",
            "Todos suportados (*.txt *.dat *.ods *.xlsx *.xls);;"
            "TXT / DAT — RES2DINV (*.txt *.dat);;Planilhas (*.ods *.xlsx *.xls);;"
            "Todos (*)")
        for f in fs:
            if f not in self.arquivos:
                self.arquivos.append(f)
                self.direcoes[f] = self._direcao_padrao()
        self._refresh()

    def _add_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta com .txt")
        if pasta:
            for f in sorted(glob.glob(os.path.join(pasta, "*.txt"))):
                if f not in self.arquivos:
                    self.arquivos.append(f)
                    self.direcoes[f] = self._direcao_padrao()
            self._refresh()

    def _limpar(self):
        self.arquivos.clear(); self.direcoes.clear()
        self.coordenadas.clear(); self.lista.clear()

    def _menu_arquivo(self, item):
        if item is None: return
        f = item.data(Qt.UserRole)
        menu = QMenu(self)
        for opc in DIRECOES_LINHA:
            marca = "✓ " if self.direcoes.get(f) == opc else "    "
            ac = menu.addAction(marca + opc)
            ac.triggered.connect(lambda _=False, o=opc: self._set_direcao(f, o))
        menu.addSeparator()
        ac_coord = menu.addAction("Definir coordenadas da linha…")
        ac_coord.triggered.connect(lambda: self._definir_coordenadas(f))
        menu.exec(self.lista.mapToGlobal(self.lista.visualItemRect(item).center()))

    def _definir_coordenadas(self, f):
        """v2.0 (§9): origem (E,N) + azimute p/ mapa de níveis e 3D."""
        dlg = QDialog(self); dlg.setWindowTitle(f"Coordenadas — {os.path.basename(f)}")
        form = QFormLayout(dlg)
        e0, n0, az = self.coordenadas.get(f, (0.0, 0.0, 90.0))
        ed_e = QLineEdit(str(e0)); ed_n = QLineEdit(str(n0)); ed_az = QLineEdit(str(az))
        form.addRow("E da origem (m / UTM):", ed_e)
        form.addRow("N da origem (m / UTM):", ed_n)
        form.addRow("Azimute da linha (° de N, horário):", ed_az)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() == QDialog.Accepted:
            try:
                self.coordenadas[f] = (float(ed_e.text()), float(ed_n.text()),
                                       float(ed_az.text()))
                self._refresh()   # v2.0.1: mostra as coordenadas na lista
            except ValueError:
                QMessageBox.warning(self, "Valor inválido",
                                    "E, N e azimute devem ser números.")

    def _set_direcao(self, f, d):
        self.direcoes[f] = d; self._refresh()

    def _escolher_saida(self):
        d = QFileDialog.getExistingDirectory(self, "Pasta de saída")
        if d: self.ed_saida.setText(d)


class PaginaExecucao(QWidget):
    """Tela exibida durante/após o processamento: progresso, log e resumo."""
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 14)
        topo = QHBoxLayout()
        self.lbl_geral = QLabel("Aguardando…")
        self.btn_parar = QPushButton("⏹  Parar"); self.btn_parar.setObjectName("btn_parar")
        self.btn_parar.clicked.connect(self.janela._parar)
        self.btn_pasta = QPushButton("Abrir pasta de resultados")
        self.btn_pasta.setProperty("secundario", True)
        self.btn_pasta.clicked.connect(self._abrir_pasta)
        self.btn_pasta.setEnabled(False)
        topo.addWidget(self.lbl_geral, 1); topo.addWidget(self.btn_pasta)
        topo.addWidget(self.btn_parar)
        lay.addLayout(topo)
        self.bar_geral = QProgressBar(); lay.addWidget(self.bar_geral)
        self.lbl_arq = QLabel(""); lay.addWidget(self.lbl_arq)
        self.bar_arq = QProgressBar(); lay.addWidget(self.bar_arq)
        lay.addWidget(QLabel("Log de processamento:"))
        self.log = QPlainTextEdit(); self.log.setObjectName("caixa_log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(20000)   # v2.0: evita crescimento sem limite
        lay.addWidget(self.log, 3)
        lay.addWidget(QLabel("Resumo da execução:"))
        self.resumo = QPlainTextEdit(); self.resumo.setObjectName("caixa_resumo")
        self.resumo.setReadOnly(True); self.resumo.setMaximumHeight(130)
        lay.addWidget(self.resumo, 1)

    def _abrir_pasta(self):
        import subprocess
        try:
            subprocess.Popen(["xdg-open", self.janela.pag_dados.ed_saida.text()])
        except OSError:
            QMessageBox.information(self, "Pasta de resultados",
                                    self.janela.pag_dados.ed_saida.text())

    def adicionar_resumo(self, dados, tipo):
        # v2.0: mesmo formato textual do _adicionar_resumo do v1.x
        if tipo == "ERT":
            rob_s = "L1" if dados.get("robust") else "L2"
            linha = (f"[ERT]  {dados['arquivo']}\n"
                     f"       RMS={dados['rms']:.1f}%  χ²={dados['chi2']:.2f}  "
                     f"λ={dados['lam']} {rob_s}  depth={dados['depth']:.0f}m  "
                     f"pts={dados['pts_aceitos']}/{dados['pts_total']}")
        else:
            rhos = " | ".join(f"{r:.0f}" for r in dados.get("rho", []))
            linha = (f"[SEV]  {dados['arquivo']}  SEV {dados['sev_id']}\n"
                     f"       RMS={dados['rms']:.1f}%  {dados['n_camadas']} camadas  "
                     f"ρ=[{rhos}] Ωm")
        self.resumo.appendPlainText(linha)


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ERT Studio — Eletrorresistividade e SEV")
        self.resize(1150, 780)
        self.worker = None

        central = QWidget(); self.setCentralWidget(central)
        raiz = QHBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0); raiz.setSpacing(0)

        # ── 1. Sidebar ────────────────────────────────────────────────
        sb = QFrame(); sb.setObjectName("sidebar")
        slay = QVBoxLayout(sb); slay.setContentsMargins(0, 0, 0, 0)
        logo = QLabel("⚡ ERT Studio"); logo.setObjectName("logo")
        slay.addWidget(logo)

        self.paginas = QStackedWidget()
        self.botoes_nav = []
        for i, nome in enumerate(["1 · Dados", "2 · Configuração", "3 · Geologia"]):
            b = QPushButton(nome); b.setProperty("nav", True); b.setCheckable(True)
            b.clicked.connect(lambda _=False, ix=i: self._ir_para(ix))
            slay.addWidget(b); self.botoes_nav.append(b)
        slay.addStretch()
        self.btn_processar = QPushButton("▶  Processar")
        self.btn_processar.setObjectName("btn_processar")
        self.btn_processar.clicked.connect(self._iniciar)
        slay.addWidget(self.btn_processar)

        # ── 2. Páginas ────────────────────────────────────────────────
        # v2.0: pag_config/pag_geo criadas ANTES de pag_dados (que lê
        # pag_config.cb_direcao como direção padrão de novos arquivos)
        self.pag_config = PaginaConfig(self)
        self.pag_geo = PaginaGeologia(self)
        self.pag_dados = PaginaDados(self)
        self.pag_exec = PaginaExecucao(self)
        for p in (self.pag_dados, self.pag_config, self.pag_geo, self.pag_exec):
            self.paginas.addWidget(p)

        raiz.addWidget(sb); raiz.addWidget(self.paginas, 1)
        self._ir_para(0)
        self._check_libs_qt()

    def _ir_para(self, ix):
        self.paginas.setCurrentIndex(ix)
        for j, b in enumerate(self.botoes_nav):
            b.setChecked(j == ix)

    def _iniciar(self):
        pd_ = self.pag_dados
        if not pd_.arquivos:
            QMessageBox.warning(self, "Sem arquivos",
                                "Adicione ao menos um arquivo na etapa 1 · Dados.")
            return
        modo_ert = pd_.rb_ert.isChecked()
        if modo_ert and (not LIBS_OK or not GIMLI_OK):
            QMessageBox.critical(self, "Dependências",
                                 "Instale PyGIMLi para processar ERT."); return
        if not LIBS_OK:
            QMessageBox.critical(self, "Dependências",
                                 "Instale numpy/pandas/matplotlib/scipy."); return
        os.makedirs(pd_.ed_saida.text(), exist_ok=True)

        geo = self.pag_geo.coletar()
        params = self.pag_config.coletar_params(geo)
        ex = self.pag_exec
        ex.log.clear(); ex.resumo.clear()
        ex.bar_geral.setValue(0); ex.bar_arq.setValue(0)
        ex.btn_parar.setEnabled(True); ex.btn_pasta.setEnabled(False)
        # v2.0 (§5.2): transparência — o que a geologia mudou na inversão
        for nota in params["notas_geo"]:
            ex.log.appendPlainText(f"  Geologia → {nota}")

        self.worker = WorkerProcessamento(
            list(pd_.arquivos), pd_.ed_saida.text(), params,
            self.pag_geo.geo_info_texto(), dict(pd_.direcoes),
            modo_ert=modo_ert, coordenadas=dict(pd_.coordenadas),
            geo_struct=geo,
            gerar_interpretacao=self.pag_geo.ck_interpretacao.isChecked())
        self.worker.item_log.connect(self._on_item_log)
        self.worker.item_prog.connect(self._on_item_prog)
        self.btn_processar.setEnabled(False)
        self.paginas.setCurrentIndex(3)           # tela de execução
        for b in self.botoes_nav: b.setChecked(False)
        self.worker.start()

    def _parar(self):
        if self.worker is not None:
            self.worker.rodando = False
            self.pag_exec.log.appendPlainText("  ⏹ Interrompido pelo usuário.")

    def _on_item_log(self, item):
        tipo, val = item
        ex = self.pag_exec
        if tipo == "log":
            ex.log.appendPlainText(val)
        elif tipo == "arq":
            ex.lbl_arq.setText(f"Arquivo atual: {val}"); ex.bar_arq.setValue(0)
        elif tipo == "geral":
            pct, txt = val; ex.bar_geral.setValue(pct); ex.lbl_geral.setText(txt)
        elif tipo == "resumo_ert":
            ex.adicionar_resumo(val, "ERT")
        elif tipo == "resumo_sev":
            ex.adicionar_resumo(val, "SEV")
        elif tipo == "fim":
            ex.log.appendPlainText("\n✓ Todos os arquivos processados!")
            ex.btn_parar.setEnabled(False); ex.btn_pasta.setEnabled(True)
            self.btn_processar.setEnabled(True)
            if not os.environ.get("ERT_STUDIO_SEM_AVISOS"):
                QMessageBox.information(self, "Concluído",
                    f"Processamento finalizado!\nResultados em:\n"
                    f"{self.pag_dados.ed_saida.text()}")

    def _on_item_prog(self, item):
        pct, txt = item
        self.pag_exec.bar_arq.setValue(int(pct))
        self.pag_exec.lbl_geral.setText(txt)

    def closeEvent(self, ev):
        # v2.0: fechar a janela com processamento ativo derrubava o processo
        # (QThread destruída em execução). Para cooperativamente e aguarda.
        if self.worker is not None and self.worker.isRunning():
            self.worker.rodando = False     # o laço checa entre arquivos
            self.worker.wait(5000)
        super().closeEvent(ev)

    def _check_libs_qt(self):
        # v2.0: mesmos avisos de dependência do v1.x, agora em QMessageBox.
        # ERT_STUDIO_SEM_AVISOS=1 suprime (necessário p/ smoke tests offscreen).
        if os.environ.get("ERT_STUDIO_SEM_AVISOS"):
            return
        if not LIBS_OK:
            QMessageBox.critical(self, "Dependências faltando",
                f"Biblioteca não encontrada: {LIBS_ERR}\n\n"
                "Execute:\n  pip install -r requirements.txt")
        if not GIMLI_OK:
            QMessageBox.warning(self, "PyGIMLi não encontrado",
                "PyGIMLi não está instalado — apenas SEV funcionará.\n\n"
                "Instalar:  pip install pygimli")


# ══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not QT_OK:
        sys.exit("PySide6 não instalado. Execute: pip install pyside6")
    app_qt = QApplication(sys.argv)
    app_qt.setStyleSheet(QSS_TEMA)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app_qt.exec())
