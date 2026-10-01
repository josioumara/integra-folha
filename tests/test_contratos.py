"""Contratos: layout v1, catálogo de tipos, tipo de carga e aprovações humanas."""
import pytest
from pydantic import ValidationError

from models.contratos import (
    OPERACOES_COM_APROVACAO_HUMANA,
    CampoLayout,
    TipoCarga,
    carregar_layout,
    definir_tipo_carga,
)

# Quantos campos cada grupo do layout v1 tem
GRUPOS_ESPERADOS = {
    "Titular": 12,
    "Documento": 5,
    "Endereço residencial": 7,
    "Telefones": 2,
    "E-mails": 2,
    "Cadastro empresarial": 7,  # com o cnpj_grupo (ADR-77)
    "Renda": 3,
    "Endereço comercial": 7,
}


def _layout_por_nome() -> dict:
    """Campo -> definição do campo no layout v1."""
    layout = {}
    for campo in carregar_layout():
        layout[campo.campo] = campo
    return layout


def test_layout_v1_tem_45_campos_nos_grupos_certos():
    """O layout v1 tem 45 campos (o cnpj_grupo entrou no ADR-77), distribuídos nos grupos do arquivo real."""
    layout = carregar_layout()
    assert len(layout) == 45
    campos_por_grupo = {}
    for campo in layout:
        campos_por_grupo[campo.grupo] = campos_por_grupo.get(campo.grupo, 0) + 1
    assert campos_por_grupo == GRUPOS_ESPERADOS


def test_nomes_de_campo_sao_unicos():
    """Nenhum nome de campo se repete."""
    nomes = []
    for campo in carregar_layout():
        nomes.append(campo.campo)
    assert len(nomes) == len(set(nomes))


def test_tipo_fora_do_catalogo_e_recusado():
    """O tipo de um campo só pode vir do catálogo fechado."""
    with pytest.raises(ValidationError):
        CampoLayout(campo="x", grupo="g", tipo="MOEDA_ESTRANGEIRA",
                    obrigatorio="S", sensivel="N", uso_comercial_permitido="N")


def test_atributos_sensiveis_proibidos_para_uso_comercial():
    """ADR-29: sexo, estado civil, nacionalidade e nascimento nunca chegam ao motor comercial."""
    layout = _layout_por_nome()
    for campo in ("sexo", "estado_civil", "nacionalidade", "data_nascimento"):
        assert layout[campo].uso_comercial_permitido is False


def test_regiao_do_motor_vem_do_endereco_comercial():
    """ADR-27: região = endereço comercial; o residencial não é lido pelo motor."""
    layout = _layout_por_nome()
    assert layout["municipio_comercial"].uso_comercial_permitido is True
    assert layout["municipio_residencial"].uso_comercial_permitido is False


def test_tipo_de_carga_e_definido_por_regra():
    """Empresa sem funcionários homologados → carga inicial; com → inclusão."""
    assert definir_tipo_carga(empresa_tem_funcionarios_homologados=False) == TipoCarga.INICIAL
    assert definir_tipo_carga(empresa_tem_funcionarios_homologados=True) == TipoCarga.INCLUSAO


def test_homologacao_exige_aprovacao_humana():
    """Homologar é sempre uma decisão de pessoa."""
    assert "homologar_arquivo" in OPERACOES_COM_APROVACAO_HUMANA
