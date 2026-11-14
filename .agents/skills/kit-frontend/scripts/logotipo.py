#!/usr/bin/env python3
"""Converte um texto em curvas SVG, para o logotipo não depender de fonte instalada.

Uso: python logotipo.py <fonte.ttf|otf|woff2> "Nome" saida.svg [--peso 700] [--eixo opsz=96] [--espaco 0]
     [--ajuste "r,e:-14"] [--sem-kerning] [--cor "#14304f"] [--simbolo simbolo.svg] [--cor-simbolo "#b3261e"] [--variantes]
Requer: pip install fonttools. WOFF2 também pede: pip install brotli.
Aplica o kerning da fonte. Mesmo assim, olhe com 24px de altura e corrija pares com --ajuste, em milésimos do tamanho da fonte.
Com --simbolo, põe o desenho à esquerda do nome. Com --variantes, grava saida-positivo.svg, saida-negativo.svg e, com símbolo, saida-sobre-marca.svg.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
except ImportError:
    sys.exit("Falta o fonttools. Instale com: pip install fonttools")

p = argparse.ArgumentParser(description="Converte texto em curvas SVG")
p.add_argument("fonte")
p.add_argument("texto")
p.add_argument("saida")
p.add_argument("--peso", type=float, help="peso, em fonte variável")
p.add_argument("--eixo", action="append", default=[], help="outro eixo da fonte variável, como opsz=96; pode repetir")
p.add_argument("--espaco", type=float, default=0, help="espaço extra entre letras, em unidades da fonte")
p.add_argument("--ajuste", action="append", default=[], help='corrige um par, como "r,e:-14", em milésimos do tamanho da fonte; pode repetir')
p.add_argument("--sem-kerning", action="store_true", help="não aplica o kerning da fonte")
p.add_argument("--cor", default="currentColor")
p.add_argument("--simbolo", help="SVG com o símbolo, feito de <path>, para ficar à esquerda do nome")
p.add_argument("--cor-simbolo", help="cor do símbolo; sem ela, usa --cor")
p.add_argument("--altura-simbolo", type=float, default=1.17, help="altura do símbolo, em alturas de x")
p.add_argument("--variantes", action="store_true", help="grava as versões para fundo claro, escuro e de marca")
a = p.parse_args()

fonte = TTFont(a.fonte)
eixos = {"wght": a.peso} if a.peso is not None else {}
for e in a.eixo:
    nome, _, valor = e.partition("=")
    try:
        eixos[nome] = float(valor)
    except ValueError:
        sys.exit(f"--eixo pede nome=valor, como opsz=96. Recebi: {e}")
if "fvar" in fonte:
    existem = {x.axisTag for x in fonte["fvar"].axes}
    if set(eixos) - existem:
        sys.exit(f"A fonte não tem o eixo {', '.join(sorted(set(eixos) - existem))}. Eixos dela: {', '.join(sorted(existem))}.")
    if eixos:
        fonte = instancer.instantiateVariableFont(fonte, eixos)
elif a.eixo:
    sys.exit("--eixo só vale para fonte variável.")

glifos = fonte.getGlyphSet()
mapa = fonte.getBestCmap()
faltam = sorted({c for c in a.texto if ord(c) not in mapa})
if faltam:
    sys.exit(f"A fonte não tem: {' '.join(faltam)}")
upem = fonte["head"].unitsPerEm


def lerKerning():
    """Devolve uma função (glifo, glifo) -> ajuste, vinda da tabela GPOS ou da kern antiga."""
    subtabelas = []
    if "GPOS" in fonte and fonte["GPOS"].table.LookupList:
        gpos = fonte["GPOS"].table
        indices = sorted({i for r in gpos.FeatureList.FeatureRecord if r.FeatureTag == "kern" for i in r.Feature.LookupListIndex})
        for i in indices:
            for st in gpos.LookupList.Lookup[i].SubTable:
                st = st.ExtSubTable if st.LookupType == 9 else st
                if st.LookupType == 2:
                    subtabelas.append(st)
    antiga = {}
    if "kern" in fonte:
        for t in fonte["kern"].kernTables:
            antiga.update(getattr(t, "kernTable", {}) or {})

    def par(g1, g2):
        for st in subtabelas:
            cobertos = st.Coverage.glyphs
            if g1 not in cobertos:
                continue
            if st.Format == 1:
                for r in st.PairSet[cobertos.index(g1)].PairValueRecord:
                    if r.SecondGlyph == g2:
                        return getattr(r.Value1, "XAdvance", 0) or 0
            else:
                c1 = st.ClassDef1.classDefs.get(g1, 0)
                c2 = st.ClassDef2.classDefs.get(g2, 0)
                return getattr(st.Class1Record[c1].Class2Record[c2].Value1, "XAdvance", 0) or 0
        return antiga.get((g1, g2), 0)

    return par


kern = (lambda g1, g2: 0) if a.sem_kerning else lerKerning()
ajustes = {}
for aj in a.ajuste:
    m = re.fullmatch(r"(.),(.):(-?\d+(?:\.\d+)?)", aj)
    if not m:
        sys.exit(f'--ajuste pede o par e o valor, como "r,e:-14". Recebi: {aj}')
    ajustes[(m[1], m[2])] = float(m[3]) * upem / 1000


def desenhar(deslocamento=0):
    caneta = SVGPathPen(glifos)
    limites = BoundsPen(glifos)
    x = deslocamento
    anterior = None
    for c in a.texto:
        nome = mapa[ord(c)]
        if anterior:
            x += kern(mapa[ord(anterior)], nome) + ajustes.get((anterior, c), 0)
        transformacao = (1, 0, 0, -1, x, 0)
        glifos[nome].draw(TransformPen(caneta, transformacao))
        glifos[nome].draw(TransformPen(limites, transformacao))
        x += glifos[nome].width + a.espaco
        anterior = c
    return caneta.getCommands(), limites.bounds


rotulo = a.texto.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
_, limites = desenhar()
if not limites:
    sys.exit("O texto não tem nenhuma forma para desenhar.")


def lerSimbolo(arquivo):
    raiz = ET.parse(arquivo).getroot()
    caixa = raiz.get("viewBox")
    if not caixa:
        sys.exit(f"{arquivo} precisa de viewBox.")
    vx, vy, vl, va = (float(v) for v in re.split(r"[\s,]+", caixa.strip()))
    caminhos = [e for e in raiz.iter() if e.tag.split("}")[-1] == "path" and e.get("d")]
    if not caminhos:
        sys.exit(f"{arquivo} precisa de <path>: converta formas e texto em curvas.")
    return vx, vy, vl, va, caminhos


def montar(cor_texto, cor_simbolo):
    if not a.simbolo:
        comandos, (x0, y0, x1, y1) = desenhar()
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:g} {y0:g} {x1 - x0:g} {y1 - y0:g}" role="img" aria-label="{rotulo}">'
            f'<title>{rotulo}</title><path fill="{cor_texto}" d="{comandos}"/></svg>\n'
        ), x1 - x0, y1 - y0
    vx, vy, vl, va, caminhos = lerSimbolo(a.simbolo)
    altura_x = getattr(fonte["OS/2"], "sxHeight", 0) or upem / 2
    altura = altura_x * a.altura_simbolo
    escala = altura / va
    largura = vl * escala
    topo = -altura_x / 2 - altura / 2
    # o símbolo começa em zero; o nome vem depois de uma folga de um terço da altura do símbolo
    comandos, (x0, y0, x1, y1) = desenhar(0)
    comandos, (x0, y0, x1, y1) = desenhar(largura + altura * 0.34 - x0)
    alto = min(y0, topo)
    baixo = max(y1, topo + altura)
    traco = "".join(f'<path d="{c.get("d")}"' + (f' fill-rule="{c.get("fill-rule")}"' if c.get("fill-rule") else "") + "/>" for c in caminhos)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {alto:g} {x1:g} {baixo - alto:g}" role="img" aria-label="{rotulo}">'
        f'<title>{rotulo}</title><g fill="{cor_simbolo}" transform="translate({-vx * escala:g} {topo - vy * escala:g}) scale({escala:g})">{traco}</g>'
        f'<path fill="{cor_texto}" d="{comandos}"/></svg>\n'
    ), x1, baixo - alto


destino = Path(a.saida)
cor_simbolo = a.cor_simbolo or a.cor
if a.variantes:
    if a.cor == "currentColor":
        sys.exit('--variantes pede --cor, como --cor "#14304f".')
    versoes = {"positivo": (a.cor, cor_simbolo), "negativo": ("#ffffff", cor_simbolo)}
    if a.simbolo:
        versoes["sobre-marca"] = ("#ffffff", a.cor)
    for nome, (cor_t, cor_s) in versoes.items():
        svg, largura, altura = montar(cor_t, cor_s)
        arquivo = destino.with_name(f"{destino.stem}-{nome}.svg")
        arquivo.write_text(svg, encoding="utf-8")
        print(f"{arquivo}: {largura:g} × {altura:g} unidades.")
else:
    svg, largura, altura = montar(a.cor, cor_simbolo)
    destino.write_text(svg, encoding="utf-8")
    print(f"{a.saida}: {largura:g} × {altura:g} unidades.")
print(("Sem kerning." if a.sem_kerning else "Com o kerning da fonte.") + " Confira no olho, com 24px de altura, e corrija pares com --ajuste.")
