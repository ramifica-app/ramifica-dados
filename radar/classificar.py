"""Classificador determinístico de objetos de compra educacionais.

Primeiro filtro barato (sem LLM): só o que passa aqui pode ir, depois, para revisão por IA.
Cada classificação guarda os termos que a justificaram — é a evidência textual.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

CATEGORIAS: dict[str, list[str]] = {
    "sistema_ensino": [r"sistema (estruturado )?de ensino", r"sistema apostilado", r"material didatico (estruturado|integrado|apostilado)",
                       r"solucao educacional", r"apostila[s]? (didatica|escolar|pedagogica)", r"metodologia de ensino"],
    "livro_didatico": [r"livros? didatic", r"livros? paradidatic", r"obras? literaria", r"acervo literario", r"literatura infantil"],
    "plataforma_digital": [r"plataforma (educacional|digital|de aprendizagem|adaptativa)", r"ambiente virtual de aprendizagem",
                           r"conteudos? digita(l|is) educaciona", r"licenca[s]? de (uso de )?(software|plataforma) educa"],
    "avaliacao": [r"avaliacao (externa|diagnostica|da aprendizagem|educacional|em larga escala)", r"simulados?", r"sistema de avaliacao"],
    "formacao": [r"formacao (continuada|de professores|docente)", r"capacitacao (de|dos) (professores|docentes|educadores)",
                 r"assessoria pedagogica", r"consultoria (pedagogica|educacional)"],
    "gestao_escolar": [r"(sistema|software) de gestao (escolar|educacional)", r"diario (de classe )?eletronico", r"secretaria escolar digital"],
    "alfabetizacao": [r"alfabetizacao", r"letramento"],
    "socioemocional": [r"socioemociona", r"habilidades socioemocionais", r"educacao emocional"],
    "educacao_financeira": [r"educacao financeira"],
    "robotica_steam": [r"robotica educacional", r"\bsteam\b", r"kits? de robotica"],
    "ensino_religioso": [r"ensino religioso"],
    "preparatorio_avaliacoes": [r"preparatorio", r"prova brasil", r"\bsaeb\b"],
}

# Contexto educacional obrigatório para termos genéricos e vetos de falsos positivos
CONTEXTO = [r"ensino", r"escola", r"educa", r"aluno", r"estudante", r"professor", r"pedagog", r"rede municipal", r"fundamental", r"infantil"]
VETOS = [r"merenda", r"alimentacao escolar", r"transporte escolar", r"uniforme", r"material de expediente", r"material de limpeza",
         r"kit(s)? (de )?material escolar", r"mobiliario", r"reforma", r"construcao", r"combustivel", r"generos alimenticios"]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


@dataclass
class Classificacao:
    educacional: bool
    categorias: list[str] = field(default_factory=list)
    termos: list[str] = field(default_factory=list)
    vetado_por: str | None = None
    confianca: float = 0.0


def classificar(objeto: str) -> Classificacao:
    t = normalizar(objeto)
    for v in VETOS:
        if re.search(v, t):
            return Classificacao(False, vetado_por=v)
    cats, termos = [], []
    for cat, padroes in CATEGORIAS.items():
        for p in padroes:
            m = re.search(p, t)
            if m:
                cats.append(cat)
                termos.append(m.group(0))
                break
    if not cats:
        return Classificacao(False)
    tem_contexto = any(re.search(c, t) for c in CONTEXTO)
    especificos = {"sistema_ensino", "livro_didatico", "plataforma_digital", "avaliacao", "formacao", "gestao_escolar", "ensino_religioso"}
    if not tem_contexto and not (set(cats) & especificos):
        return Classificacao(False, termos=termos)
    conf = min(1.0, 0.5 + 0.2 * len(cats) + (0.2 if tem_contexto else 0))
    return Classificacao(True, cats, termos, None, round(conf, 2))
